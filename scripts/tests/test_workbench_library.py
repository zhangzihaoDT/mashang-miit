"""Read-only Library boundaries and actual historical preview acceptance, offline."""
import hashlib
import json
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.request import urlopen, Request
from urllib.error import HTTPError
from urllib.parse import quote
from unittest.mock import patch

import pytest
import workbench_library as library
from workbench_server import handler
from workbench_source import WorkbenchError


def test_real_409_preview_and_download(tmp_path):
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler(None, tmp_path))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}/api/miit/library/'
    try:
        def get(path):
            return urlopen(base + path)
        roots = json.load(get('tree'))['items']
        assert [r['path'] for r in roots] == ['data', 'reports']
        for directory in ['data/miit_formal', 'reports']:
            assert any(x['name'] == 'batch_409' for x in json.load(get('tree?path=' + directory))['items'])
        files = ['data/miit_formal/batch_409/raw_detail.html',
                 'data/miit_formal/batch_409/product_list.json',
                 'data/vehicle_parameters/product_master.csv',
                 'reports/batch_409/category_report/index.html']
        for path in files:
            original = library.file_path(path).read_bytes()
            preview = json.load(get('preview?path=' + quote(path)))
            assert preview['kind'] in {'html', 'json', 'table'}
            response = get('file/' + quote(path) + '?download=1')
            assert 'attachment' in response.headers['Content-Disposition']
            assert hashlib.sha256(response.read()).digest() == hashlib.sha256(original).digest()
            assert library.file_path(path).read_bytes() == original
        html = get('file/' + files[0])
        assert 'sandbox' in html.headers['Content-Security-Policy']
        assert "script-src 'none'" in html.headers['Content-Security-Policy']
        assert html.headers['Content-Type'].startswith('text/html')
        with patch('workbench_library.subprocess.run') as run:
            req = Request(base + 'open', data=json.dumps({'path': files[1]}).encode(), headers={'Content-Type': 'application/json'}, method='POST')
            assert json.load(urlopen(req))['ok']
            assert run.call_args.args[0] == ['/usr/bin/open', str(library.file_path(files[1]))]
        req = Request(base + 'open', data=b'{"path":"data/vehicle_parameters/product_master.csv"}', headers={'Content-Type': 'application/json', 'Origin': 'https://evil.test'}, method='POST')
        with pytest.raises(HTTPError) as exc:
            urlopen(req)
        assert exc.value.code == 403
    finally:
        server.shutdown(); server.server_close(); thread.join()


def test_path_boundary_and_live_directory_refresh(tmp_path, monkeypatch):
    data = tmp_path / 'data'; data.mkdir()
    monkeypatch.setattr(library, 'ROOTS', {'data': data})
    (data / 'fetch_status').mkdir()
    (data / 'cache').mkdir()
    (data / 'run.log').write_text('technical')
    (data / 'visible.txt').write_text('first')
    (data / 'alias').symlink_to(tmp_path)
    assert [x['name'] for x in library.listing('data')['items']] == ['visible.txt']
    (data / 'new.json').write_text('{"中文":1}')
    assert len(library.listing('data')['items']) == 2
    assert library.preview('data/new.json')['kind'] == 'json'
    for path in ['data/../outside', '/etc/passwd', 'runs/task.log', 'data/alias', 'data/fetch_status', 'data/run.log']:
        with pytest.raises(WorkbenchError):
            library.resolve(path)
    (data / 'quoted.csv').write_text('a,b\n"含,逗号","多\n行"\n')
    assert library.preview('data/quoted.csv')['rows'] == [['含,逗号', '多\n行']]
    (data / 'bad.json').write_text('{bad')
    assert library.preview('data/bad.json')['content'] == '{bad'
