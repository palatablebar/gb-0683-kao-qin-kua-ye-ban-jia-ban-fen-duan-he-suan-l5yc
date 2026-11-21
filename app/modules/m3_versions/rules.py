from collections import defaultdict
from datetime import datetime,date,time,timedelta
from zoneinfo import ZoneInfo
from decimal import Decimal
from app.errors import DomainError
ZONE=ZoneInfo('Asia/Shanghai')

def _signature(r):
    base=('at','hourly_rate','shift_start','shift_end','paid')
    sig=tuple(str(r[k]) for k in base)
    if r.get('_profile')=='v2':return sig+('v2',str(r['break_minutes']))
    return sig+('v1',str(r['break_start']),str(r['break_end']))

def schedule(row):
    try:
        day=date.fromisoformat(row['shift_day']);start=datetime.combine(day,time.fromisoformat(row['shift_start']),ZONE);end=datetime.combine(day,time.fromisoformat(row['shift_end']),ZONE)
        if end<=start:end+=timedelta(days=1)
        if end-start>timedelta(hours=18):raise ValueError()
        if row.get('_profile')=='v2':
            from app.modules.m8_ledger.break_window import centered_break
            bs,be=centered_break(start,end,int(row['break_minutes']))
            return start,end,bs,be
        bs=datetime.combine(day,time.fromisoformat(row['break_start']),ZONE);be=datetime.combine(day,time.fromisoformat(row['break_end']),ZONE)
        if bs<start:bs+=timedelta(days=1)
        if be<=bs:be+=timedelta(days=1)
        if not start<=bs<be<=end:raise ValueError()
        return start,end,bs,be
    except DomainError:raise
    except (ValueError,TypeError):raise DomainError('RANGE','班次或休息区间无效')

def apply(state):
    groups=defaultdict(list);bad=[]
    for r in state['rows']:
        try:
            schedule(r)
            if r['punch'] not in ('IN','OUT') or Decimal(str(r['hourly_rate']))<0:raise DomainError('RANGE','打卡或时薪无效')
            groups[(r['employee'],r['shift_day'])].append(r)
        except DomainError as e:bad.append((r,e.code))
    shifts=[]
    for (employee,day),rows in sorted(groups.items()):
        selected={};conflict=False
        for kind in ('IN','OUT'):
            candidates=[r for r in rows if r['punch']==kind]
            if not candidates:continue
            version=max(Decimal(str(r['version'])) for r in candidates);high=[r for r in candidates if Decimal(str(r['version']))==version]
            signatures={tuple(_signature(r)) for r in high}
            if len(signatures)>1:conflict=True
            selected[kind]=sorted(high,key=lambda r:r['id'])[0]
        if 'IN' in selected and 'OUT' in selected:
            shared=('hourly_rate','shift_start','shift_end')
            if any(str(selected['IN'][k])!=str(selected['OUT'][k]) for k in shared):conflict=True
            a,b=selected['IN'],selected['OUT']
            if a.get('_profile')!=b.get('_profile'):conflict=True
            elif a.get('_profile')=='v2' and str(a['break_minutes'])!=str(b['break_minutes']):conflict=True
            elif a.get('_profile')!='v2' and (str(a['break_start'])!=str(b['break_start']) or str(a['break_end'])!=str(b['break_end'])):conflict=True
        if conflict:bad.extend((r,'CONFLICT') for r in rows);continue
        shifts.append({'id':employee+'/'+day,'employee':employee,'day':day,'in':selected.get('IN'),'out':selected.get('OUT'),'sources':rows})
    lines={r['_line'] for r,_ in bad};state['rows']=[r for r in state['rows'] if r['_line'] not in lines]
    for r,c in bad:state['quarantine'].append({'line':r['_line'],'id':r['id'],'code':c,'raw':r['_raw'],**({'source':r['_source']} if r.get('_source') else {})})
    state['shifts']=shifts;return state
