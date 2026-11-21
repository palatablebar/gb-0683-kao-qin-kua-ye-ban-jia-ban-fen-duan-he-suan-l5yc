"""月度数据集管线：多源文件 -> 模板归一 -> 复用 m2-m6 链路 -> 月度汇总。

每次重算都由当前来源集指纹决定 dataset_id；来源不变则结果完全一致（幂等），
来源一旦变动就产生新数据集，旧发布版由存储层标记失效并保留可查。
"""
import hashlib
import json
import time
from datetime import datetime, timezone

from app.config import RULE_VERSION
from app.errors import DomainError
from app.modules.m8_ledger.source_reader import read_source
from app.modules.m8_ledger.canonicalize import canonicalize
from app.modules.m3_versions.rules import apply as pair
from app.modules.m4_segments.rules import apply as segment
from app.modules.m5_calculate.rules import apply as calculate
from app.modules.m6_reconcile.compare import balance


def source_key(content):
    return hashlib.sha256(content).hexdigest()[:16]


def dataset_fingerprint(source_keys, parameters):
    raw = json.dumps(sorted(source_keys), ensure_ascii=False).encode()
    raw += json.dumps(parameters, sort_keys=True, ensure_ascii=False).encode()
    raw += RULE_VERSION.encode()
    return hashlib.sha256(raw).hexdigest()[:20]


def build_dataset(registered_sources, parameters=None):
    """registered_sources: [{'name','content'(bytes)}]，按名称排序保证确定性。"""
    parameters = parameters or {}
    start = time.monotonic()
    per_file, rejected = [], []
    for entry in sorted(registered_sources, key=lambda e: e['name']):
        try:
            per_file.append(read_source(entry['content'], entry['name']))
        except DomainError as error:
            rejected.append({
                'source': entry['name'], 'code': error.code, 'message': error.message,
                'sha256': hashlib.sha256(entry['content']).hexdigest(),
            })
    if not per_file:
        raise DomainError('NO_VALID_SOURCE', '没有可采信的源文件')
    state = canonicalize(per_file, parameters)
    state['rejected_sources'] = rejected
    state = pair(state)
    state = segment(state)
    state = calculate(state)
    state['reconcile'] = balance(state)

    # 每来源实发与采纳/隔离汇总
    accepted_by_source = {}
    for r in state['rows']:
        src = r.get('_source', '')
        accepted_by_source.setdefault(src, 0)
        accepted_by_source[src] += 1
    paid_by_source = {}
    for r in state['rows']:
        src = r.get('_source', '')
        paid_by_source[src] = paid_by_source.get(src, 0) + r.get('paid', 0)
    quarantined_by_source = {}
    for q in state['quarantine']:
        src = q.get('source', '')
        quarantined_by_source[src] = quarantined_by_source.get(src, 0) + 1
    for src in state['sources']:
        name = src['source']
        src['accepted_count'] = accepted_by_source.get(name, 0)
        src['quarantined_count'] = quarantined_by_source.get(name, 0)
        src['paid'] = str(paid_by_source.get(name, 0))
    # 班次附上解释方式与来源，页面可逐班看清
    for shift in state['shifts']:
        pin = shift['in'] or shift['out']
        shift['profile'] = pin.get('_profile') if pin else None
        shift['source_in'] = shift['in'].get('_source', '') if shift['in'] else ''
        shift['source_out'] = shift['out'].get('_source', '') if shift['out'] else ''

    keys = [source_key(e['content']) for e in registered_sources]
    state['month'] = parameters.get('month', '')
    state['dataset_id'] = dataset_fingerprint(keys, parameters)
    state['source_fingerprint'] = dataset_fingerprint(keys, {})
    state['ledger_manifest'] = {
        'rule_version': RULE_VERSION,
        'parameters': parameters,
        'source_count': len(registered_sources),
        'rejected_count': len(rejected),
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'elapsed_ms': round((time.monotonic() - start) * 1000),
    }
    return state
