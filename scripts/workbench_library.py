"""Read-only real-directory Reports browser; preview contract adapted from mashang-fetch.

No index, database, or pipeline execution. All paths are scoped to miit_paths roots.
"""
import csv
import io
import json
import subprocess
import sys
from pathlib import PurePosixPath

from miit_paths import DATA_DIR, REPORTS_DIR
from workbench_source import WorkbenchError

ROOTS = {'data': DATA_DIR, 'reports': REPORTS_DIR}
HIDDEN = {'fetch_status', 'checkpoint', 'checkpoints', 'cache', 'caches', '__pycache__', 'logs', 'runs'}
TEXT_LIMIT = 8 * 1024 * 1024
IMAGE_TYPES = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.gif': 'image/gif', '.webp': 'image/webp'}
OPENABLE = {'.md', '.csv', '.json', '.txt', '.html', '.htm', '.doc', '.docx', '.pdf', *IMAGE_TYPES}


def hidden(part):
    return (part.startswith('.') or part.lower() in HIDDEN or
            part.lower().startswith(('fetch_status_', 'checkpoint_', 'cache_')) or
            part.lower().endswith(('.log', '.lock', '.sqlite', '.sqlite3', '.pyc')))


def resolve(path):
    parts = PurePosixPath(path).parts
    if not parts or parts[0] not in ROOTS or any(p in {'.', '..'} or hidden(p) for p in parts):
        raise WorkbenchError('invalid_library_path', '资料库路径无效', 403)
    root = ROOTS[parts[0]].resolve()
    target = root.joinpath(*parts[1:])
    # Do not expose symlink aliases, even when they point back inside a root.
    current = root
    for part in parts[1:]:
        current = current / part
        if current.is_symlink():
            raise WorkbenchError('invalid_library_path', '不支持符号链接', 403)
    if not target.resolve().is_relative_to(root):
        raise WorkbenchError('invalid_library_path', '资料库路径无效', 403)
    if not target.exists():
        raise WorkbenchError('not_found', '文件或目录不存在，请刷新目录', 404)
    return target


def entry(path, file):
    stat = file.stat()
    return {'path': path, 'name': file.name, 'directory': file.is_dir(),
            'size': stat.st_size if file.is_file() else None, 'mtime': stat.st_mtime}


def listing(path=''):
    if not path:
        return {'items': [entry(name, root) for name, root in ROOTS.items() if root.is_dir()]}
    folder = resolve(path)
    if not folder.is_dir():
        raise WorkbenchError('not_directory', '请选择文件夹', 400)
    files = [p for p in folder.iterdir() if not hidden(p.name) and not p.is_symlink() and (p.is_file() or p.is_dir())]
    files.sort(key=lambda p: (not p.is_dir(), p.name.casefold()))
    return {'items': [entry(path.rstrip('/') + '/' + p.name, p) for p in files]}


def file_path(path):
    file = resolve(path)
    if not file.is_file():
        raise WorkbenchError('not_file', '请选择文件', 400)
    return file


def preview(path):
    file = file_path(path)
    result = entry(path, file)
    ext = file.suffix.lower()
    if ext in IMAGE_TYPES:
        return {**result, 'kind': 'image'}
    if ext in {'.html', '.htm'}:
        return {**result, 'kind': 'html'}
    if ext not in {'.md', '.csv', '.json', '.txt'}:
        return {**result, 'kind': 'unsupported', 'message': '此格式请下载或在本地打开。'}
    if file.stat().st_size > TEXT_LIMIT:
        return {**result, 'kind': 'unsupported', 'message': '文件超过 8 MiB，请下载或在本地打开完整内容。'}
    text = file.read_text(encoding='utf-8-sig', errors='replace')
    if ext == '.csv':
        reader = csv.reader(io.StringIO(text, newline=''))
        header = next(reader, [])
        rows = []
        for row in reader:
            if len(rows) == 500:
                return {**result, 'kind': 'table', 'header': header, 'rows': rows, 'truncated': True}
            rows.append(row)
        return {**result, 'kind': 'table', 'header': header, 'rows': rows, 'truncated': False}
    if ext == '.json':
        try:
            text = json.dumps(json.loads(text), ensure_ascii=False, indent=2)
        except ValueError:
            return {**result, 'kind': 'text', 'content': text, 'message': 'JSON 格式无效，显示原文。'}
    return {**result, 'kind': {'.md': 'markdown', '.json': 'json', '.txt': 'text'}[ext], 'content': text}


def open_local(path):
    file = file_path(path)
    if sys.platform != 'darwin' or file.suffix.lower() not in OPENABLE:
        raise WorkbenchError('open_unsupported', '此文件请下载后打开', 400)
    try:
        subprocess.run(['/usr/bin/open', str(file)], check=True, capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as exc:
        raise WorkbenchError('open_failed', '本地打开失败，请下载原文件', 400) from exc
    return {'ok': True}
