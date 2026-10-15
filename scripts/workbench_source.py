"""Isolated MIIT formal source adapter; no canonical writes or batch fallback."""
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

import requests
import eidc_parser
import miit_formal_source
from eidc_source import doc_to_txt
from vehicle_record_builder import classify_source_record, normalize_model_code


class WorkbenchError(Exception):
    def __init__(self, code, message, status=400, retryable=False):
        super().__init__(message)
        self.code, self.status, self.retryable = code, status, retryable


def validate_url(url, attachment=False):
    if not isinstance(url, str) or len(url) > 2048:
        raise WorkbenchError('unsupported_url', '请提供 MIIT 正式公告 HTTPS 详情链接')
    p = urlsplit(url)
    pattern = (r'/cms_files/[A-Za-z0-9/_-]+\.doc' if attachment else
               r'/jgsj/zbys/wjfb/art/\d{4}/art_[A-Za-z0-9]+\.html')
    if (p.scheme != 'https' or p.netloc not in {'www.miit.gov.cn', 'miit.gov.cn'}
            or p.query or p.fragment or not re.fullmatch(pattern, p.path)):
        raise WorkbenchError('unsupported_url', 'V1.0 支持 MIIT 文件发布栏目的正式公告详情页，暂不支持公示或车型链接')
    return url


def fetch_bytes(url, attachment=False):
    validate_url(url, attachment)
    # Redirects are deliberately rejected, including redirects to another official path.
    with requests.get(url, timeout=(10, 60), allow_redirects=False, stream=True,
                      headers={'User-Agent': miit_formal_source.UA}) as response:
        if 300 <= response.status_code < 400:
            raise WorkbenchError('redirect_rejected', '来源发生跳转，请使用最终官方链接')
        response.raise_for_status()
        chunks, size = [], 0
        for chunk in response.iter_content(65536):
            size += len(chunk)
            if size > 40 * 1024 * 1024:
                raise WorkbenchError('source_too_large', '来源文件超过 40 MB 限制')
            chunks.append(chunk)
        return b''.join(chunks)


def collect(url, directory, archive=None):
    """archive is a trusted configured path, never a user-supplied API path."""
    validate_url(url)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    evidence = []

    def save(name, body, source_url, kind):
        (directory / name).write_bytes(body)
        evidence.append({'name': name, 'source_url': source_url, 'kind': kind,
                         'sha256': hashlib.sha256(body).hexdigest(), 'size': len(body)})

    if archive:
        archive = Path(archive)
        cached = json.loads((archive / 'raw_metadata.json').read_text())
        if cached.get('source_url') != url:
            raise WorkbenchError('archive_url_mismatch', '归档链接不匹配')
        html = (archive / 'raw_detail.html').read_bytes()
    else:
        html = fetch_bytes(url)
    save('notice.html', html, url, 'html')
    meta = miit_formal_source.parse_formal_metadata(html.decode('utf-8'), url)
    batch = str(meta.get('batch_no', ''))
    if not re.fullmatch(r'[1-9]\d{2,3}', batch):
        raise WorkbenchError('batch_not_found', '公告未解析出明确批次，已停止采集')
    road = next((a for a in meta.get('attachments', []) if '道路机动车辆' in a['title']), None)
    if not road:
        raise WorkbenchError('road_attachment_missing', '未找到道路机动车辆附件')
    validate_url(road['url'], attachment=True)
    if archive:
        doc = archive / 'attachments' / road['filename']
        if doc.is_file():
            save('road.doc', doc.read_bytes(), road['url'], 'doc')
        text = (archive / 'attachment_text_src' / road['filename'].replace('.doc', '.txt')).read_bytes()
    else:
        save('road.doc', fetch_bytes(road['url'], attachment=True), road['url'], 'doc')
        try:
            doc_to_txt(directory / 'road.doc', directory / 'converted.txt')
        except (OSError, RuntimeError):
            from eidc_doc_extract import doc_to_txt_ole
            (directory / 'converted.txt').write_text(doc_to_txt_ole(directory / 'road.doc'), encoding='utf-8')
        text = (directory / 'converted.txt').read_bytes()
    save('road.txt', text, road['url'], 'text')
    rows = eidc_parser.parse_road_products(text.decode('utf-8'), batch)
    if not rows:
        raise WorkbenchError('empty_parse', '附件解析为空，原始证据已保留')
    issues, seen = [], set()
    for index, row in enumerate(rows):
        code, valid = normalize_model_code(row.get('model_code_raw', ''))
        category, _ = classify_source_record(row)
        codes = []
        if not valid:
            codes.append('invalid_model_code')
        if category != 'passenger_vehicle':
            codes.append('outside_canonical_scope')
        if not row.get('manufacturer_raw') or not row.get('product_name_raw'):
            codes.append('missing_required_field')
        if code in seen:
            codes.append('duplicate_model_code')
        seen.add(code)
        if codes:
            issues.append({'row': index, 'model_code': code, 'codes': codes})
    return {'schema_version': 'miit_candidate.v1', 'batch_no': batch,
            'source': 'miit_gov', 'stage': 'confirmed', 'source_url': url,
            'capture_mode': 'archive_replay' if archive else 'live',
            'metadata': meta, 'rows': rows, 'issues': issues}, evidence
