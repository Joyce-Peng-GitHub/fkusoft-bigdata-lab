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
    """是否休息日：法定节假日 + 普通周末，已考虑调休"""
    d = _as_date(d)
    try:
        return 0 if cc.is_workday(d) else 1
    except NotImplementedError:
        return int(d.weekday() >= 5)


def is_holiday(d):
    """是否法定节假日（有节日名的假期日）"""
    d = _as_date(d)
    try:
        _, name = cc.get_holiday_detail(d)
        return int((not cc.is_workday(d)) and name is not None)
    except NotImplementedError:
        return 0


def is_makeup(d):
    """是否调休上班日（周末却要上班）"""
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