"""v2 新模板的休息窗口合成：在实际打卡区间上按中点居中扣除休息分钟。

旧样例 22:00-06:00 配 02:00-03:00 休息，休息恰位于实际区间中点；
v2 只给休息分钟数，沿用同一中点约定，不猜测固定钟点。
"""
from datetime import timedelta

from app.errors import DomainError


def centered_break(start, end, break_minutes):
    worked = end - start
    total = int(worked.total_seconds())
    if total <= 0:
        raise DomainError('RANGE', '打卡时长无效')
    if break_minutes * 60 > total:
        raise DomainError('RANGE', '休息分钟超过打卡区间')
    # 奇数秒时休息窗起点向下取整，保证整窗落在实际区间内
    offset = (total - break_minutes * 60) // 2
    bs = start + timedelta(seconds=offset)
    be = bs + timedelta(minutes=break_minutes)
    return bs, be
