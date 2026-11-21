import base64

from flask import Blueprint, jsonify, render_template, request, Response

from app.config import TITLE, SHORT, MODULES
from app.errors import DomainError
from app.modules.m8_ledger import ledger_store
from app.modules.m8_ledger.export_monthly import monthly_bundle, monthly_checksum

bp = Blueprint('m8_ledger', __name__)
DEFAULT_MONTH = '2026-10'


def _month(data):
    month = (data.get('month') or request.args.get('month') or DEFAULT_MONTH).strip()
    if not month or len(month) > 10:
        raise DomainError('MONTH', '月份参数无效')
    return month


@bp.get('/m8_ledger')
def screen():
    month = request.args.get('month', DEFAULT_MONTH)
    sources = ledger_store.list_sources(month)
    datasets = ledger_store.list_datasets(month)
    current = ledger_store.published(month)
    if current is None and datasets:
        current = ledger_store.get_dataset(month, datasets[0]['dataset_id'])
    return render_template('m8_ledger.html', title=TITLE, short=SHORT, modules=MODULES,
                           current=8, month=month, sources=sources,
                           datasets=datasets, data=current, checksum=monthly_checksum(current) if current else '')


@bp.get('/api/m8_ledger/sources')
def get_sources():
    data = request.args or {}
    return jsonify(ledger_store.list_sources(_month(data)))


@bp.post('/api/m8_ledger/sources')
def add_source():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        raise DomainError('PAYLOAD', '请求必须是对象')
    month = _month(data)
    name = str(data.get('name', '')).strip()
    if data.get('content_b64'):
        try:
            content = base64.b64decode(data['content_b64'], validate=True)
        except ValueError:
            raise DomainError('PAYLOAD', 'content_b64 必须是 Base64')
    elif isinstance(data.get('csv'), str):
        content = data['csv'].encode('utf-8')
    else:
        raise DomainError('PAYLOAD', '需要 csv 文本或 content_b64')
    return jsonify(ledger_store.register_source(month, name, content))


@bp.delete('/api/m8_ledger/sources/<path:name>')
def delete_source(name):
    data = request.args or {}
    ledger_store.remove_source(_month(data), name)
    return jsonify({'removed': name})


@bp.post('/api/m8_ledger/datasets')
def rebuild():
    data = request.get_json(silent=True) or {}
    month = _month(data)
    return jsonify(ledger_store.build(month, data.get('parameters', {})))


@bp.get('/api/m8_ledger/datasets')
def datasets():
    data = request.args or {}
    return jsonify(ledger_store.list_datasets(_month(data)))


@bp.get('/api/m8_ledger/datasets/<dataset_id>')
def dataset_detail(dataset_id):
    data = request.args or {}
    return jsonify(ledger_store.get_dataset(_month(data), dataset_id))


@bp.post('/api/m8_ledger/datasets/<dataset_id>/review')
def review_dataset(dataset_id):
    data = request.get_json(silent=True) or {}
    if not isinstance(data.get('version'), int):
        raise DomainError('VERSION', '请提交复核版本')
    return jsonify(ledger_store.review(_month(data), dataset_id, data['version'],
                                       data.get('decision', '通过')))


@bp.post('/api/m8_ledger/datasets/<dataset_id>/publish')
def publish_dataset(dataset_id):
    data = request.get_json(silent=True) or {}
    return jsonify(ledger_store.publish(_month(data), dataset_id))


@bp.get('/api/m8_ledger/published')
def get_published():
    data = request.args or {}
    return jsonify(ledger_store.published(_month(data)))


@bp.get('/api/m8_ledger/datasets/<dataset_id>/export.csv')
def export_dataset(dataset_id):
    data = request.args or {}
    state = ledger_store.get_dataset(_month(data), dataset_id)
    if not state.get('published'):
        raise DomainError('NOT_PUBLISHED', '仅已发布数据集可导出')
    return Response(monthly_bundle(state), mimetype='text/csv; charset=utf-8',
                    headers={'Content-Disposition': f'attachment; filename=monthly_{_month(data)}.csv'})
