# -*- coding: utf-8 -*-
"""
NCS 充电桩 ML 子系统 —— 节假日 / 休息日
数据源：chinesecalendar（权威库，含国务院调休安排，支持 2004~2026）。

对外提供：
  is_rest(d)      是否休息日（法定节假日 + 普通周末，已考虑“周末调休上班”）
  is_holiday(d)   是否法定节假日（有节日名；含落在周末的假期日）
  is_makeup(d)    是否调休上班日（周末却要上班）

注意：日期超出 chinesecalendar 支持范围（>2026）时，is_rest 退回“周末即休息”，
      is_holiday / is_makeup 退回 0；长期运行需升级该库或维护节假日表。
"""
import datetime

import chinese_calendar as cc


def _as_date(d):
    """将受支持的日期表示规范化为 ``datetime.date``。

    Args:
        d: ``datetime``、``date``、ISO 日期字符串，或提供 ``date()`` 方法
            的日期对象（例如 ``pandas.Timestamp``）。

    Returns:
        datetime.date: 不含时间和时区信息的日历日期。

    Raises:
        TypeError: 输入不属于任何受支持的日期表示。
        ValueError: ISO 日期字符串格式无效。
    """
    if isinstance(d, datetime.datetime):
        return d.date()
    if isinstance(d, datetime.date):
        return d
    if isinstance(d, str):
        return datetime.date.fromisoformat(d)
    if hasattr(d, "date"):          # pandas.Timestamp
        return d.date()
    raise TypeError(f"不支持的日期类型: {type(d)}")


def is_rest(d):
    """判断日期是否为实际休息日，包含法定假日和普通周末。

    Args:
        d: ``_as_date`` 支持的日期表示。

    Returns:
        int: 休息日返回 1，工作日返回 0。超出节假日库覆盖范围时，按
        周一至周五工作、周末休息的规则回退。
    """
    d = _as_date(d)
    try:
        return 0 if cc.is_workday(d) else 1
    except NotImplementedError:
        return int(d.weekday() >= 5)


def is_holiday(d):
    """判断日期是否为有节日名称的法定假日。

    Args:
        d: ``_as_date`` 支持的日期表示。

    Returns:
        int: 法定假日返回 1，否则返回 0；超出节假日库覆盖范围时返回 0。
    """
    d = _as_date(d)
    try:
        _, name = cc.get_holiday_detail(d)
        return int((not cc.is_workday(d)) and name is not None)
    except NotImplementedError:
        return 0


def is_makeup(d):
    """判断日期是否为周末安排的调休工作日。

    Args:
        d: ``_as_date`` 支持的日期表示。

    Returns:
        int: 调休工作日返回 1，否则返回 0；超出节假日库覆盖范围时返回 0。
    """
    d = _as_date(d)
    try:
        return int(cc.is_workday(d) and d.weekday() >= 5)
    except NotImplementedError:
        return 0


if __name__ == "__main__":
    # 自检：打印数据区间内的法定节假日与调休上班日
    start, end = datetime.date(2014, 11, 18), datetime.date(2015, 10, 7)
    d = start
    while d <= end:
        if is_holiday(d):
            print("节假日", d, d.strftime("%a"))
        elif is_makeup(d):
            print("调休上班", d, d.strftime("%a"))
        d += datetime.timedelta(days=1)
