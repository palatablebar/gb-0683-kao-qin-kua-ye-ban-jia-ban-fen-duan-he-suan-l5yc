"""按源文件整体识别字段模板（v1 旧字段 / v2 带秒与休息分钟）。

裁决：模板只按表头签名对整份文件认定一次，不逐行猜测，
因此同一班次不可能被两种解释方式拆开。
"""
from app.config import REQUIRED, V1_FIELDS, V2_FIELDS, PROFILES
from app.errors import DomainError


def detect(header):
    """header 为已去 BOM、去空白的列名列表，返回 profile 标识。"""
    if len(set(header)) != len(header):
        raise DomainError('TEMPLATE', '表头列名重复，无法认定模板')
    columns = set(header)
    if not set(REQUIRED) <= columns:
        raise DomainError('TEMPLATE', '表头缺少共用必填列，无法认定模板')
    has_v1 = all(f in columns for f in V1_FIELDS)
    has_v2 = all(f in columns for f in V2_FIELDS)
    if has_v1 and has_v2:
        raise DomainError('TEMPLATE', '新旧休息字段并存，拒绝逐行猜测模板')
    if has_v2:
        profile = 'v2'
    elif has_v1:
        profile = 'v1'
    else:
        raise DomainError('TEMPLATE', '缺少休息字段（break_start/end 或 break_minutes）')
    return profile


def profile_label(profile):
    return PROFILES[profile]['label']
