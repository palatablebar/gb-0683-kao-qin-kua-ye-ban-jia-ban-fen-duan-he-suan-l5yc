TITLE='考勤跨夜班与加班分段核算'
SHORT='shiftledger'
RULE_VERSION='2026.11.17-v1'
MODULES=[('m1_ingest', '打卡采信'), ('m2_mapping', '班次日历'), ('m3_versions', '跨夜配对'), ('m4_segments', '缺卡复核'), ('m5_calculate', '工时切段'), ('m6_reconcile', '薪资对账'), ('m7_archive', '周期归档')]
LEDGER_MODULE=('m8_ledger', '月度发布')
REQUIRED=['id', 'employee', 'shift_day', 'version', 'punch', 'at', 'shift_start', 'shift_end', 'hourly_rate', 'paid']
NUMERIC=['version', 'hourly_rate', 'paid']
DATES=['shift_day']
TIMES=['at']
# 旧模板（v1）：打卡整分钟，休息用起止时刻
V1_FIELDS=['break_start', 'break_end']
# 新模板（v2，考勤机分批升级后）：打卡带秒，休息按分钟
V2_FIELDS=['break_minutes']
PROFILES={
    'v1': {'label': '旧字段模板（整分钟/休息起止时刻）', 'break_mode': 'window'},
    'v2': {'label': '新字段模板（带秒/休息分钟居中扣除）', 'break_mode': 'minutes'},
}
MAX_FILE_BYTES=2_000_000
