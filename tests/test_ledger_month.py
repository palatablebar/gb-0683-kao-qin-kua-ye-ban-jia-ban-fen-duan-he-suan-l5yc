import base64
import pathlib
import sys

sys.path.insert(0, '/workspace')
import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'ledger.db'))
    from app.main import create_app
    app = create_app()
    app.config['TESTING'] = True
    return app.test_client()


MONTH = '2026-10'
SAMPLE_DIR = pathlib.Path('/workspace/sample_data/month_2026_10')


def _register(client, name):
    content = (SAMPLE_DIR / name).read_bytes()
    return client.post('/api/m8_ledger/sources', json={
        'month': MONTH, 'name': name,
        'content_b64': base64.b64encode(content).decode('ascii')})


def _register_all(client):
    for p in sorted(SAMPLE_DIR.glob('*.csv')):
        _register(client, p.name)


def test_full_lifecycle(client):
    _register_all(client)
    # 模板签名不符的文件整份拒收
    r = client.post('/api/m8_ledger/datasets', json={'month': MONTH})
    assert r.status_code == 200
    ds = r.get_json()
    rejected = [x['source'] for x in ds['rejected_sources']]
    assert '05_bad_mixed_header.csv' in rejected
    profiles = {s['source']: s['profile'] for s in ds['sources']}
    assert profiles['01_old_machines_E001_E003.csv'] == 'v1'
    assert profiles['02_new_machines_E101_E102.csv'] == 'v2'
    # 混合模板共同形成班次，且同班次不拆分
    employees = {s['employee'] for s in ds['shifts']}
    assert {'E001', 'E101', 'E201'} <= employees
    assert all(s['profile'] in ('v1', 'v2') for s in ds['shifts'])
    assert ds['reconcile']['balanced'] is True
    dataset_id = ds['dataset_id']

    # 未复核不能发布
    r = client.post(f'/api/m8_ledger/datasets/{dataset_id}/publish', json={'month': MONTH})
    assert r.status_code == 422 and r.get_json()['code'] == 'NOT_REVIEWED'
    # 复核通过后发布
    r = client.post(f'/api/m8_ledger/datasets/{dataset_id}/review',
                    json={'month': MONTH, 'version': 1, 'decision': '通过'})
    assert r.status_code == 200 and r.get_json()['review_version'] == 2
    r = client.post(f'/api/m8_ledger/datasets/{dataset_id}/publish', json={'month': MONTH})
    assert r.status_code == 200 and r.get_json()['published'] is True
    # 已发布才能导出，且导出含来源解释与原始打卡
    r = client.get(f'/api/m8_ledger/datasets/{dataset_id}/export.csv?month={MONTH}')
    assert r.status_code == 200
    text = r.data.decode('utf-8-sig')
    assert '来源解释' in text and '原始打卡' in text and '应付片段' in text


def test_idempotent_retry_no_record_change(client):
    _register_all(client)
    a = client.post('/api/m8_ledger/datasets', json={'month': MONTH}).get_json()
    b = client.post('/api/m8_ledger/datasets', json={'month': MONTH}).get_json()
    assert a['dataset_id'] == b['dataset_id']
    assert len(client.get(f'/api/m8_ledger/datasets?month={MONTH}').get_json()) == 1
    assert a['reconcile'] == b['reconcile']


def test_source_change_invalidates_published_and_keeps_old(client):
    _register_all(client)
    ds = client.post('/api/m8_ledger/datasets', json={'month': MONTH}).get_json()
    did = ds['dataset_id']
    client.post(f'/api/m8_ledger/datasets/{did}/review',
                json={'month': MONTH, 'version': 1, 'decision': '通过'})
    client.post(f'/api/m8_ledger/datasets/{did}/publish', json={'month': MONTH})
    # 旧发布版仍可查
    old = client.get(f'/api/m8_ledger/datasets/{did}?month={MONTH}').get_json()
    assert old['published'] is True

    # 同名来源内容变动 -> 重算产生新数据集，旧版作废但保留
    client.post('/api/m8_ledger/sources', json={
        'month': MONTH, 'name': '03_late_arrival_E201.csv',
        'csv': '﻿id,employee,shift_day,version,punch,at,shift_start,shift_end,break_minutes,hourly_rate,paid,note\n'
               'C001,E201,2026-10-01,1,IN,2026-10-01T22:00:09+08:00,22:00,06:00,60,20,220,变动\n'
               'C002,E201,2026-10-01,1,OUT,2026-10-02T06:00:39+08:00,22:00,06:00,60,20,0,变动\n'})
    new = client.post('/api/m8_ledger/datasets', json={'month': MONTH}).get_json()
    assert new['dataset_id'] != did
    old2 = client.get(f'/api/m8_ledger/datasets/{did}?month={MONTH}').get_json()
    assert old2['superseded'] is True and old2['published'] is True
    # 已作废数据集禁止发布
    r = client.post(f'/api/m8_ledger/datasets/{did}/publish', json={'month': MONTH})
    assert r.status_code == 422 and r.get_json()['code'] == 'SUPERSEDED'
    # 发布指针仍指向旧版（发布中断/未发布新版期间系统保留旧版）
    pub = client.get(f'/api/m8_ledger/published?month={MONTH}').get_json()
    assert pub['dataset_id'] == did


def test_page_renders(client):
    _register_all(client)
    client.post('/api/m8_ledger/datasets', json={'month': MONTH})
    r = client.get('/m8_ledger')
    assert r.status_code == 200 and '月度来源与解释方式'.encode() in r.data


def test_bad_template_rejected_whole_file(client):
    # 独立月份只登记一份表头签名不符的文件：整份拒收，无有效来源可构建
    r = client.post('/api/m8_ledger/sources', json={
        'month': '2026-09', 'name': 'bad.csv',
        'csv': 'id,employee\n1,E\n'})
    assert r.status_code == 200
    r2 = client.post('/api/m8_ledger/datasets', json={'month': '2026-09'})
    assert r2.status_code == 422 and r2.get_json()['code'] == 'NO_VALID_SOURCE'


def test_no_source_month(client):
    r = client.post('/api/m8_ledger/datasets', json={'month': '2026-08'})
    assert r.status_code == 422 and r.get_json()['code'] == 'NO_SOURCE'
