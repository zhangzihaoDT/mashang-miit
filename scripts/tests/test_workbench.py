"""Offline integration tests: real archived notice, isolated state, no live collection."""
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from threading import Thread
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import pytest
import requests
from miit_paths import MIIT_FORMAL_DIR, VEHICLE_PARAMETERS_DIR
from workbench_source import WorkbenchError, collect, validate_url
from workbench_store import Store
from workbench_server import Worker, handler

ARCHIVE = MIIT_FORMAL_DIR / 'batch_409'
URL = json.loads((ARCHIVE / 'raw_metadata.json').read_text())['source_url']


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError('Tests must never capture live data')
    monkeypatch.setattr(requests, 'get', fail)


def test_real_batch_roundtrip(tmp_path):
    # Full archived parser output equality, not a synthetic subset.
    watched = list(ARCHIVE.rglob('*')) + list(VEHICLE_PARAMETERS_DIR.glob('*'))
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in watched if p.is_file()}
    store = Store(tmp_path / 'db.sqlite3')
    task = store.create(URL, 'first')
    assert Worker(store, tmp_path / 'tasks', ARCHIVE).once()
    result = store.task(task['task_id'])
    assert result['status'] == 'succeeded', result['error']
    candidate = store.candidate(result['candidate_id'])
    expected = json.loads((ARCHIVE / 'product_list.json').read_text())
    assert candidate['payload']['rows'] == expected
    assert candidate['review_status'] == 'pending_review'
    assert candidate['payload']['stage'] == 'confirmed'
    assert candidate['payload']['capture_mode'] == 'archive_replay'
    assert candidate['payload']['issues']
    for evidence in candidate['evidence']:
        path = tmp_path / 'tasks' / task['task_id'] / evidence['metadata']['name']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == evidence['metadata']['sha256']
    # New Store instance sees all committed state after a simulated restart.
    assert Store(store.path).candidate(candidate['candidate_id']) == candidate
    assert all(hashlib.sha256(p.read_bytes()).hexdigest() == digest for p, digest in before.items())


def test_concurrent_idempotency_and_conflict(tmp_path):
    store = Store(tmp_path / 'db')
    with ThreadPoolExecutor(max_workers=6) as executor:
        tasks = list(executor.map(lambda _: store.create(URL, 'same'), range(12)))
    assert len({t['task_id'] for t in tasks}) == 1
    assert store.create(URL, 'another')['task_id'] != tasks[0]['task_id']
    with pytest.raises(WorkbenchError, match='幂等键'):
        store.create(URL.replace('art_4951', 'art_9999'), 'same')


def test_restart_and_retry(tmp_path):
    store = Store(tmp_path / 'db')
    original = store.create(URL, 'a')
    store.claim()
    store.recover()
    assert store.task(original['task_id'])['status'] == 'failed'
    retry = store.create(URL, 'b', original['task_id'])
    assert retry['retry_of'] == original['task_id']
    assert retry['task_id'] != original['task_id']
    assert store.claim()['task_id'] == retry['task_id']
    # Transaction rollback must remove the candidate on evidence insertion failure.
    with pytest.raises(TypeError):
        store.complete(retry['task_id'], {'rows': []}, [{'bad': object()}])
    assert store.inbox() == []
    assert store.task(retry['task_id'])['status'] == 'running'


def test_failure_preserves_error_and_no_candidate(tmp_path):
    store = Store(tmp_path / 'db')
    task = store.create(URL, 'a')
    Worker(store, tmp_path / 'tasks', tmp_path / 'missing_archive').once()
    result = store.task(task['task_id'])
    assert result['status'] == 'failed'
    assert json.loads(result['error'])['code'] == 'capture_failed'
    assert not store.inbox()


@pytest.mark.parametrize('url', [
    'http://www.miit.gov.cn/jgsj/zbys/wjfb/art/2026/art_a.html',
    'https://www.miit.gov.cn.evil.test/jgsj/zbys/wjfb/art/2026/art_a.html',
    'https://www.miit.gov.cn@127.0.0.1/jgsj/zbys/wjfb/art/2026/art_a.html',
    'file:///etc/passwd', 'https://www.miit.gov.cn/other.html',
    URL + '?redirect=x', URL + '#x', None,
])
def test_url_boundary(url):
    with pytest.raises(WorkbenchError):
        validate_url(url)


def test_api_and_evidence(tmp_path):
    store = Store(tmp_path / 'db')
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler(store, tmp_path / 'tasks'))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    def call(path, body=None, headers=None):
        request = Request(base + path, data=json.dumps(body).encode() if body else None,
                          headers=headers or ({'Content-Type': 'application/json'} if body else {}))
        return urlopen(request, timeout=5)
    try:
        page = call('/').read().decode()
        assert 'mashang-miit' in page and 'class="brand-icon"' in page
        for asset, mime, magic in [('brand.png', 'image/png', b'\x89PNG'), ('favicon.gif', 'image/gif', b'GIF')]:
            with call('/' + asset) as response:
                assert response.headers['Content-Type'] == mime
                assert response.read().startswith(magic)
        task = json.load(call('/api/miit/tasks', {'url': URL, 'idempotency_key': 'api'}))
        Worker(store, tmp_path / 'tasks', ARCHIVE).once()
        with patch('workbench_library.subprocess.run') as run:
            assert json.load(call('/api/miit/tasks/' + task['task_id'] + '/open-folder', {'open': True}))['ok']
            assert run.call_args.args[0] == ['/usr/bin/open', '-a', 'Finder', str(tmp_path / 'tasks' / task['task_id'])]
        inbox = json.load(call('/api/miit/inbox'))
        candidate = json.load(call('/api/miit/candidates/' + inbox['items'][0]['candidate_id']))
        evidence = next(e for e in candidate['evidence'] if e['metadata']['kind'] == 'html')
        with call('/api/miit/evidence/' + evidence['evidence_id']) as response:
            assert response.headers['Content-Type'].startswith('text/plain')
            assert response.read()
        with pytest.raises(HTTPError) as error:
            call('/api/miit/tasks', {'url': URL, 'idempotency_key': 'cross'},
                 {'Content-Type': 'application/json', 'Origin': 'https://evil.test'})
        assert error.value.code == 403
        assert json.load(call('/api/miit/tasks/' + task['task_id']))['status'] == 'succeeded'
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_live_adapter_rejects_redirect(monkeypatch):
    from workbench_source import fetch_bytes
    class Redirect:
        status_code = 302
        def __enter__(self): return self
        def __exit__(self, *args): pass
    monkeypatch.setattr(requests, 'get', lambda *args, **kwargs: Redirect())
    with pytest.raises(WorkbenchError) as error:
        fetch_bytes(URL)
    assert error.value.code == 'redirect_rejected'


def test_live_adapter_preserves_evidence_and_rejects_empty(tmp_path, monkeypatch):
    import workbench_source as src
    html = (ARCHIVE / 'raw_detail.html').read_bytes()
    monkeypatch.setattr(src, 'fetch_bytes', lambda url, attachment=False: b'fake doc' if attachment else html)
    def convert(doc, target):
        target.write_text('no vehicle rows', encoding='utf-8')
    monkeypatch.setattr(src, 'doc_to_txt', convert)
    with pytest.raises(WorkbenchError) as error:
        src.collect(URL, tmp_path / 'task')
    assert error.value.code == 'empty_parse'
    assert (tmp_path / 'task' / 'road.doc').read_bytes() == b'fake doc'
    assert (tmp_path / 'task' / 'notice.html').read_bytes() == html


def test_live_adapter_isolated_success(tmp_path, monkeypatch):
    import workbench_source as src
    meta = json.loads((ARCHIVE / 'raw_metadata.json').read_text())
    road = next(a for a in meta['attachments'] if '道路机动车辆' in a['title'])
    text = (ARCHIVE / 'attachment_text_src' / road['filename'].replace('.doc', '.txt')).read_bytes()
    monkeypatch.setattr(src, 'fetch_bytes', lambda url, attachment=False: b'fake doc' if attachment else (ARCHIVE / 'raw_detail.html').read_bytes())
    monkeypatch.setattr(src, 'doc_to_txt', lambda doc, target: target.write_bytes(text))
    payload, evidence = src.collect(URL, tmp_path / 'task')
    assert payload['capture_mode'] == 'live'
    assert payload['rows'] == json.loads((ARCHIVE / 'product_list.json').read_text())
    assert {e['name'] for e in evidence} == {'notice.html', 'road.doc', 'road.txt'}
