"""月度发布导出：核对页面与导出使用同一份数据集结果。"""
import csv
import hashlib
import io
import json


def monthly_bundle(state):
    out = io.StringIO(newline='')
    w = csv.writer(out)
    rid = state.get('dataset_id', 'preview')
    month = state.get('month', '')
    w.writerow(['记录类型', '月份', '数据集', '来源文件', '模板', '来源行', '业务ID', '原因码', '内容'])
    w.writerow(['月度清单', month, rid, '', '', '', '', '',
                json.dumps(state.get('ledger_manifest', {}), ensure_ascii=False, sort_keys=True)])
    w.writerow(['对账', month, rid, '', '', '', '', '',
                json.dumps(state.get('reconcile', {}), ensure_ascii=False, sort_keys=True)])
    # 每份源文件采用的解释方式
    for src in state.get('sources', []):
        w.writerow(['来源解释', month, rid, src['source'], src['profile_label'], '', '', '',
                    json.dumps(src, ensure_ascii=False, sort_keys=True)])
    for rej in state.get('rejected_sources', []):
        w.writerow(['拒收来源', month, rid, rej['source'], '', '', '', rej['code'],
                    json.dumps(rej, ensure_ascii=False, sort_keys=True)])
    # 原始打卡（归一后，保留来源、模板、原始行号）
    for r in state.get('rows', []):
        raw = {k: v for k, v in r.items() if not k.startswith('_')}
        w.writerow(['原始打卡', month, rid, r.get('_source', ''), r.get('_profile', ''),
                    r.get('_line', ''), r.get('id', ''), '',
                    json.dumps(raw, ensure_ascii=False, sort_keys=True)])
    # 班次与最终应付证据
    for row in state.get('calculations', []):
        w.writerow(['应付片段', month, rid, row.get('source', ''), row.get('profile', ''),
                    row.get('line', ''), row.get('id', ''), row.get('code', ''),
                    json.dumps(row, ensure_ascii=False, sort_keys=True)])
    for q in state.get('quarantine', []):
        w.writerow(['隔离', month, rid, q.get('source', ''), '', q.get('line', ''),
                    q.get('id', ''), q.get('code', ''),
                    json.dumps(q.get('raw', {}), ensure_ascii=False, sort_keys=True)])
    return '﻿' + out.getvalue()


def monthly_checksum(state):
    return hashlib.sha256(monthly_bundle(state).encode('utf-8')).hexdigest()
