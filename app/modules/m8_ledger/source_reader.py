"""逐源文件读取：每份文件独立解码、独立认定模板、独立对账计数。"""
import csv
import io

from app.config import MAX_FILE_BYTES
from app.errors import DomainError
from app.modules.m1_ingest.decode import decode
from app.modules.m8_ledger.profiles import detect, profile_label


def read_source(content, source_name):
    if len(content) > MAX_FILE_BYTES:
        raise DomainError('SIZE', '文件超过2MB', 413)
    text, encoding = decode(content)
    if not text:
        raise DomainError('EMPTY_FILE', '文件为空')
    if not text.strip():
        raise DomainError('BLANK_FILE', '文件仅含空行')
    reader = csv.reader(io.StringIO(text, newline=''))
    try:
        header = [s.strip().lstrip('﻿') for s in next(reader)]
    except (StopIteration, csv.Error):
        raise DomainError('HEADER', '无法读取表头')
    # 模板签名不符：整份文件拒收，不进入月度结果，也不隔离其中任何一行
    profile = detect(header)
    out = {
        'source': source_name, 'encoding': encoding, 'profile': profile,
        'profile_label': profile_label(profile), 'header': header,
        'rows': [], 'quarantine': [], 'input_count': 0, 'blank_count': 0,
        'header_count': 0, 'duplicate_count': 0, 'accepted_count': 0,
    }
    try:
        for row in reader:
            out['input_count'] += 1
            line = reader.line_num
            if not row or not any(s.strip() for s in row):
                out['blank_count'] += 1
                continue
            if row == header:
                out['header_count'] += 1
                continue
            if len(row) != len(header):
                out['quarantine'].append(
                    {'source': source_name, 'line': line, 'id': '', 'code': 'WIDTH', 'raw': row})
                continue
            item = dict(zip(header, row))
            item['_line'] = line
            item['_source'] = source_name
            item['_profile'] = profile
            item['_raw'] = dict(item)
            out['rows'].append(item)
    except csv.Error as exc:
        raise DomainError('CSV', str(exc))
    if out['input_count'] == 0:
        raise DomainError('HEADER_ONLY', '文件仅含表头')
    return out
