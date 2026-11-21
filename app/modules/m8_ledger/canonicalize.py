"""把多份不同模板的源文件归一为同一条 m2-m6 处理链路所需的统一状态。

v1 行保留 break_start/break_end；v2 行保留 break_minutes（整数分钟），
休息窗口延迟到切段时按实际打卡区间中点居中合成，避免猜测固定钟点。
"""
from copy import deepcopy

from app.config import REQUIRED, V1_FIELDS, V2_FIELDS, NUMERIC, DATES, TIMES
from app.errors import DomainError
from app.modules.m2_mapping.coerce import number, day, instant, SENTINELS

PROFILE_FIELDS = {'v1': V1_FIELDS, 'v2': V2_FIELDS}


def _is_blank(value):
    return str(value).strip().upper() in SENTINELS


def _coerce_rows(per_file, quarantine):
    good = []
    for parsed in per_file:
        profile = parsed['profile']
        extra = PROFILE_FIELDS[profile]
        for row in parsed['rows']:
            try:
                for field in REQUIRED + extra:
                    if _is_blank(row.get(field, '')):
                        raise DomainError('MISSING', '必填值缺失')
                item = dict(row)
                for field in NUMERIC:
                    if field in item and item[field] != '':
                        item[field] = number(item[field])
                if profile == 'v2':
                    minutes = number(item['break_minutes'])
                    if minutes < 0 or minutes % 1 != 0:
                        raise DomainError('NUMBER', '休息分钟必须为非负整数')
                    item['break_minutes'] = int(minutes)
                for field in DATES:
                    if field in item and item[field] != '':
                        item[field] = day(item[field])
                for field in TIMES:
                    if field in item and item[field] != '':
                        item[field] = instant(item[field])
                good.append(item)
            except DomainError as error:
                quarantine.append({
                    'source': row.get('_source', ''), 'line': row['_line'],
                    'id': row.get('id', ''), 'code': error.code, 'raw': row['_raw'],
                })
    return good


def canonicalize(per_file, parameters=None):
    state = {
        'rows': [], 'quarantine': [], 'input_count': 0, 'blank_count': 0,
        'header_count': 0, 'duplicate_count': 0, 'encoding': 'multi',
        'parameters': parameters or {}, 'sources': [], 'rejected_sources': [],
    }
    for parsed in per_file:
        state['input_count'] += parsed['input_count']
        state['blank_count'] += parsed['blank_count']
        state['header_count'] += parsed['header_count']
        state['quarantine'].extend(deepcopy(parsed['quarantine']))
        state['sources'].append({
            'source': parsed['source'], 'profile': parsed['profile'],
            'profile_label': parsed['profile_label'], 'encoding': parsed['encoding'],
            'input_count': parsed['input_count'], 'header': parsed['header'],
        })
    rows = _coerce_rows(per_file, state['quarantine'])
    # 跨文件去重：键 (id, version)；完全相同行去重，同键冲突整组隔离
    groups = {}
    for item in rows:
        key = (item['id'], str(item.get('version', '1')))
        groups.setdefault(key, []).append(item)
    good = []
    for key, grp in groups.items():
        signature = {
            str(sorted((k, str(v)) for k, v in r.items() if not k.startswith('_')))
            for r in grp
        }
        if len(signature) > 1:
            for r in grp:
                state['quarantine'].append({
                    'source': r.get('_source', ''), 'line': r['_line'],
                    'id': r['id'], 'code': 'CONFLICT', 'raw': r['_raw'],
                })
        else:
            good.append(grp[0])
            state['duplicate_count'] += len(grp) - 1
    state['rows'] = good
    return state
