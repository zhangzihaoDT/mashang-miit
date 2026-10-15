#!/usr/bin/env python3
"""Local MIIT workbench. Run from repository root; one process per data directory."""
import argparse
import json
import logging
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs, unquote, quote

from miit_paths import WORKBENCH_DIR, WORKBENCH_WEB_DIR, MIIT_FORMAL_DIR
from workbench_source import WorkbenchError, collect
from workbench_store import Store
import workbench_library as library


class Worker:
    def __init__(self, store, root, archive=None):
        self.store, self.root, self.archive = store, root, archive
        self.stop = threading.Event()

    def once(self):
        task = self.store.claim()
        if not task:
            return False
        try:
            payload, evidence = collect(task['url'], self.root / task['task_id'], self.archive)
            self.store.complete(task['task_id'], payload, evidence)
        except Exception as error:
            logging.exception('Task %s failed', task['task_id'])
            self.store.fail(task['task_id'], {'code': getattr(error, 'code', 'capture_failed'),
                            'message': str(error)[:1000], 'retryable': getattr(error, 'retryable', True)})
        return True

    def run(self):
        while not self.stop.is_set():
            if not self.once():
                self.stop.wait(.5)


def handler(store, root):
    class Handler(BaseHTTPRequestHandler):
        def send(self, data, status=200, content_type='application/json; charset=utf-8', headers=None, csp=None):
            body = json.dumps(data, ensure_ascii=False).encode() if isinstance(data, (dict, list)) else data
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Security-Policy', csp or "default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; frame-ancestors 'none'")
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self.dispatch(False)

        def do_POST(self):
            self.dispatch(True)

        def dispatch(self, post):
            try:
                # Prevent cross-origin mutation and DNS rebinding against the local service.
                host = self.headers.get('Host', '')
                if host not in {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}:
                    raise WorkbenchError('invalid_host', '只允许本机访问', 403)
                if post and self.headers.get('Origin') not in (None, f'http://{host}'):
                    raise WorkbenchError('invalid_origin', '来源不受支持', 403)
                path = urlsplit(self.path).path
                if not post and path in {'/', '/app.js', '/library.js', '/vendor/markdown.js', '/styles.css', '/favicon.gif'}:
                    name = 'index.html' if path == '/' else path[1:]
                    content_type = {'index.html': 'text/html', 'app.js': 'text/javascript', 'library.js': 'text/javascript', 'vendor/markdown.js': 'text/javascript', 'styles.css': 'text/css', 'favicon.gif': 'image/gif'}[name]
                    if name == 'favicon.gif':
                        return self.send((WORKBENCH_WEB_DIR / name).read_bytes(), content_type=content_type)
                    return self.send((WORKBENCH_WEB_DIR / name).read_bytes(), content_type=content_type + '; charset=utf-8')
                body = {}
                if post:
                    if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                        raise WorkbenchError('invalid_content_type', '需要 JSON 请求', 415)
                    size = int(self.headers.get('Content-Length', '0'))
                    if size <= 0 or size > 16384:
                        raise WorkbenchError('invalid_body', '请求大小无效')
                    body = json.loads(self.rfile.read(size))
                    if not isinstance(body, dict):
                        raise WorkbenchError('invalid_body', '需要 JSON 对象')
                query = parse_qs(urlsplit(self.path).query)
                library_path = query.get('path', [''])[0]
                if not post and path == '/api/miit/library/tree':
                    return self.send(library.listing(library_path))
                if not post and path == '/api/miit/library/preview':
                    return self.send(library.preview(library_path))
                if post and path == '/api/miit/library/open':
                    return self.send(library.open_local(body.get('path', '')))
                prefix = '/api/miit/library/file/'
                if not post and path.startswith(prefix):
                    file = library.file_path(unquote(path[len(prefix):]))
                    download = query.get('download') == ['1']
                    mime = library.IMAGE_TYPES.get(file.suffix.lower(), 'text/plain; charset=utf-8')
                    if file.suffix.lower() in {'.html', '.htm'}:
                        mime = 'text/html; charset=utf-8'
                    extra = {'Content-Disposition': "attachment; filename*=UTF-8''" + quote(file.name)} if download else {}
                    # HTML can render styles/images, but cannot execute scripts or access parent UI.
                    policy = "sandbox; default-src 'none'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'none'; frame-ancestors 'self'; base-uri 'none'; form-action 'none'"
                    return self.send(file.read_bytes(), content_type=mime, headers=extra, csp=policy)
                if path == '/api/miit/tasks':
                    if post:
                        if body.get('capture_type', 'auto') not in ('auto', 'formal_batch'):
                            raise WorkbenchError('unsupported_capture_type', '暂只支持正式公告批次')
                        return self.send(store.create(body.get('url'), body.get('idempotency_key')), 202)
                    return self.send({'items': store.tasks(), 'limit': 100})
                match = re.fullmatch(r'/api/miit/tasks/([0-9a-f]{32})(/retry)?', path)
                if match:
                    task = store.task(match[1])
                    if post and match[2]:
                        return self.send(store.create(task['url'], body.get('idempotency_key'), match[1]), 202)
                    if not post and not match[2]:
                        return self.send(task)
                if not post and path == '/api/miit/inbox':
                    return self.send({'items': store.inbox(), 'limit': 100})
                match = re.fullmatch(r'/api/miit/candidates/([0-9a-f]{32})', path)
                if not post and match:
                    return self.send(store.candidate(match[1]))
                match = re.fullmatch(r'/api/miit/evidence/([0-9a-f]{32})', path)
                if not post and match:
                    row = store.evidence(match[1])
                    meta = row['metadata']
                    file = (root / row['task_id'] / meta['name']).resolve()
                    if not file.is_relative_to(root.resolve()):
                        raise WorkbenchError('invalid_evidence_path', '证据路径无效', 403)
                    if meta['kind'] == 'doc':
                        return self.send(file.read_bytes(), content_type='application/octet-stream')
                    # HTML is always served as text: no active page execution.
                    return self.send(file.read_bytes(), content_type='text/plain; charset=utf-8')
                raise WorkbenchError('not_found', '接口不存在', 404)
            except WorkbenchError as error:
                self.send({'code': error.code, 'message': str(error), 'retryable': error.retryable}, error.status)
            except (ValueError, TypeError):
                self.send({'code': 'invalid_request', 'message': '请求格式无效', 'retryable': False}, 400)
            except Exception:
                logging.exception('Request failed')
                self.send({'code': 'internal_error', 'message': '服务处理失败，请查看本地日志', 'retryable': True}, 500)
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8787)
    parser.add_argument('--replay-batch', choices=['409'], help='只读回放本地真实归档，不访问网络')
    args = parser.parse_args()
    WORKBENCH_DIR.mkdir(parents=True, exist_ok=True)
    # Advisory lock excludes a second process before recovery changes any task state.
    import fcntl
    with (WORKBENCH_DIR / 'worker.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.error('该工作台目录已由另一个进程使用')
        store = Store(WORKBENCH_DIR / 'workbench.sqlite3')
        server = ThreadingHTTPServer(('127.0.0.1', args.port), handler(store, WORKBENCH_DIR / 'tasks'))
        store.recover()
        worker = Worker(store, WORKBENCH_DIR / 'tasks', MIIT_FORMAL_DIR / 'batch_409' if args.replay_batch else None)
        thread = threading.Thread(target=worker.run, daemon=True)
        thread.start()
        print(f'http://127.0.0.1:{args.port} — {"archive replay" if args.replay_batch else "live capture"}', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            worker.stop.set()
            server.server_close()
            thread.join(timeout=2)


if __name__ == '__main__':
    main()
