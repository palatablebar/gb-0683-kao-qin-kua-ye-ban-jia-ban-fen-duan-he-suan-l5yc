"""月度台账存储：来源登记、数据集版本、发布指针与作废链。

- 来源按 (月份, 文件名) 登记，内容哈希变化即视为来源变动。
- 数据集按来源集指纹幂等；同指纹重算不产生新版本。
- 发布是 published 指针的条件切换；来源变动后旧发布版标记 superseded，
  但记录保留可查；新数据集完成发布前，旧版继续对外有效。
"""
import json
from datetime import datetime, timezone

from app.errors import DomainError
from app.modules.m8_ledger.pipeline import build_dataset, source_key, dataset_fingerprint
from app.store import connection


def _init(db):
    db.execute('''CREATE TABLE IF NOT EXISTS ledger_sources(
        month TEXT NOT NULL, name TEXT NOT NULL, sha TEXT NOT NULL,
        content_b64 TEXT NOT NULL, registered_at TEXT NOT NULL,
        PRIMARY KEY(month,name))''')
    db.execute('''CREATE TABLE IF NOT EXISTS ledger_datasets(
        month TEXT NOT NULL, dataset_id TEXT NOT NULL, body TEXT NOT NULL,
        source_fingerprint TEXT NOT NULL, created_at TEXT NOT NULL,
        decision TEXT NOT NULL DEFAULT '待复核', version INTEGER NOT NULL DEFAULT 1,
        superseded INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(month,dataset_id))''')
    db.execute('''CREATE TABLE IF NOT EXISTS ledger_published(
        month TEXT PRIMARY KEY, dataset_id TEXT NOT NULL,
        published_at TEXT NOT NULL)''')


def list_sources(month):
    with connection() as db:
        _init(db)
        rows = db.execute('SELECT month,name,sha,registered_at FROM ledger_sources WHERE month=? ORDER BY name', (month,)).fetchall()
    return [dict(r) for r in rows]


def register_source(month, name, content):
    if not name or '/' in name or '..' in name:
        raise DomainError('SOURCE_NAME', '来源文件名无效')
    import base64
    sha = source_key(content)
    with connection() as db:
        _init(db)
        db.execute('''INSERT INTO ledger_sources(month,name,sha,content_b64,registered_at)
            VALUES(?,?,?,?,?) ON CONFLICT(month,name) DO UPDATE SET
            sha=excluded.sha,content_b64=excluded.content_b64,registered_at=excluded.registered_at''',
            (month, name, sha, base64.b64encode(content).decode('ascii'),
             datetime.now(timezone.utc).isoformat()))
    return {'month': month, 'name': name, 'sha': sha}


def remove_source(month, name):
    with connection() as db:
        _init(db)
        cur = db.execute('DELETE FROM ledger_sources WHERE month=? AND name=?', (month, name))
        if cur.rowcount != 1:
            raise DomainError('NOT_FOUND', '来源不存在', 404)


def _load_contents(db, month):
    import base64
    rows = db.execute('SELECT name,content_b64 FROM ledger_sources WHERE month=? ORDER BY name', (month,)).fetchall()
    return [{'name': r['name'], 'content': base64.b64decode(r['content_b64'])} for r in rows]


def _mark_stale_published(db, month):
    """来源集变化后：当前已发布数据集标记作废，但不删除、不切换指针。"""
    row = db.execute('SELECT dataset_id FROM ledger_published WHERE month=?', (month,)).fetchone()
    if row:
        db.execute('UPDATE ledger_datasets SET superseded=1 WHERE month=? AND dataset_id=?',
                   (month, row['dataset_id']))


def build(month, parameters=None):
    parameters = dict(parameters or {})
    parameters['month'] = month
    with connection() as db:
        _init(db)
        sources = _load_contents(db, month)
        if not sources:
            raise DomainError('NO_SOURCE', '该月份尚未登记任何源文件')
        keys = [source_key(e['content']) for e in sources]
        fp = dataset_fingerprint(keys, parameters)
        existing = db.execute('SELECT 1 FROM ledger_datasets WHERE month=? AND dataset_id=?', (month, fp)).fetchone()
        published = db.execute('SELECT dataset_id FROM ledger_published WHERE month=?', (month,)).fetchone()
        if not existing and published:
            _mark_stale_published(db, month)
    # 重算在事务外完成（纯函数），再持久化
    state = build_dataset(sources, parameters)
    body = json.loads(json.dumps(state, default=str, ensure_ascii=False))
    with connection() as db:
        _init(db)
        db.execute('''INSERT OR IGNORE INTO ledger_datasets(month,dataset_id,body,source_fingerprint,created_at)
            VALUES(?,?,?,?,?)''',
            (month, fp, json.dumps(body, ensure_ascii=False), state['source_fingerprint'],
             datetime.now(timezone.utc).isoformat()))
    return get_dataset(month, fp)


def get_dataset(month, dataset_id):
    with connection() as db:
        _init(db)
        r = db.execute('SELECT * FROM ledger_datasets WHERE month=? AND dataset_id=?', (month, dataset_id)).fetchone()
        if not r:
            raise DomainError('NOT_FOUND', '月度数据集不存在', 404)
        body = json.loads(r['body'])
        body.update(decision=r['decision'], review_version=r['version'],
                    superseded=bool(r['superseded']))
        pub = db.execute('SELECT published_at FROM ledger_published WHERE month=? AND dataset_id=?',
                         (month, dataset_id)).fetchone()
        body['published'] = bool(pub)
        body['published_at'] = pub['published_at'] if pub else None
    return body


def list_datasets(month):
    with connection() as db:
        _init(db)
        rows = db.execute('''SELECT d.dataset_id,d.decision,d.version,d.superseded,d.created_at,
                (p.dataset_id IS NOT NULL) AS published
            FROM ledger_datasets d LEFT JOIN ledger_published p
            ON p.month=d.month AND p.dataset_id=d.dataset_id
            WHERE d.month=? ORDER BY d.created_at DESC''', (month,)).fetchall()
    return [dict(r) for r in rows]


def review(month, dataset_id, version, decision):
    if decision not in ('通过', '退回'):
        raise DomainError('DECISION', '复核状态无效')
    with connection() as db:
        _init(db)
        cur = db.execute('UPDATE ledger_datasets SET version=version+1,decision=? WHERE month=? AND dataset_id=? AND version=?',
                         (decision, month, dataset_id, version))
        if cur.rowcount != 1:
            if not db.execute('SELECT 1 FROM ledger_datasets WHERE month=? AND dataset_id=?', (month, dataset_id)).fetchone():
                raise DomainError('NOT_FOUND', '月度数据集不存在', 404)
            raise DomainError('STALE', '复核版本已更新，请刷新', 409)
    return get_dataset(month, dataset_id)


def publish(month, dataset_id):
    """原子切换发布指针；失败（含中断）不影响旧发布版。"""
    with connection() as db:
        _init(db)
        r = db.execute('SELECT decision,superseded FROM ledger_datasets WHERE month=? AND dataset_id=?',
                       (month, dataset_id)).fetchone()
        if not r:
            raise DomainError('NOT_FOUND', '月度数据集不存在', 404)
        if r['superseded']:
            raise DomainError('SUPERSEDED', '来源已变动，该数据集已作废，请重新核对')
        if r['decision'] != '通过':
            raise DomainError('NOT_REVIEWED', '数据集复核通过后才能发布')
        now = datetime.now(timezone.utc).isoformat()
        db.execute('''INSERT INTO ledger_published(month,dataset_id,published_at) VALUES(?,?,?)
            ON CONFLICT(month) DO UPDATE SET dataset_id=excluded.dataset_id,published_at=excluded.published_at''',
            (month, dataset_id, now))
        db.execute('UPDATE ledger_datasets SET superseded=0 WHERE month=? AND dataset_id=?', (month, dataset_id))
        # 同月份其它数据集保持历史可查；当前发布之外不再是发布版
    return get_dataset(month, dataset_id)


def published(month):
    with connection() as db:
        _init(db)
        r = db.execute('SELECT dataset_id FROM ledger_published WHERE month=?', (month,)).fetchone()
        if not r:
            return None
    return get_dataset(month, r['dataset_id'])
