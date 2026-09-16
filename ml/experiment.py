# -*- coding: utf-8 -*-
"""
NCS 充电桩 ML 子系统 —— 模型调优实验（滚动前推验证）
用 walk-forward（扩展窗口）验证代替单一验证窗口，选型更稳健；最后看独立 test。

运行：
  cd ~/ncs-dashboard
  export SPARK_HOME=/opt/module/spark-3.4.1
  export PYTHONPATH=$SPARK_HOME/python:$SPARK_HOME/python/lib/py4j-0.10.9.7-src.zip
  ml/venv/bin/python ml/experiment.py

背景结论：
  · 数据含强增长趋势，树模型直接回归 kwh 无法外推，弱于 lag7 朴素基准；
  · 用“14 天滚动均值作锚点 × 模型预测比例”把趋势交给锚点，模型只管日历/节假日，
    效果最好（gbr_ratio14 系列）。
"""

import os
import sys

os.environ.setdefault("SPARK_HOME", "/opt/module/spark-3.4.1")
SPARK_HOME = os.environ["SPARK_HOME"]
for _p in (
    os.path.join(SPARK_HOME, "python"),
    os.path.join(SPARK_HOME, "python", "lib", "py4j-0.10.9.7-src.zip"),
):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error

from train import load_data
from holidays import is_holiday, is_rest

TARGET = "total_kwh"


def build_features(pdf):
    """从日粒度序列构造实验用特征表。

    特征分为三类：
      · 日历特征：星期几、法定节假日、真休息日（含调休）、周末、月份；
      · 滞后特征：1/2/3/7/14 天前的电量，刻画短期自相关；
      · 滚动均值：前 7 / 14 天均值（即后续方案中的"锚点"）。

    Args:
        pdf: 日粒度序列 DataFrame，至少包含 ``stat_date`` 与 ``total_kwh``
            （来自 dws.daily_series，一天一行）。

    Returns:
        pandas.DataFrame: 按日期升序、附加了上述特征列的 DataFrame。

    Note:
        所有 lag / rolling 均先 ``shift(1)``，即只用"当天之前"的历史信息，
        防止把当天真实值泄进特征造成数据泄露；前 max(lag)/14 行因信息不足
        产生 NaN，由调用方 dropna() 处理。
    """
    pdf = pdf.sort_values("stat_date").reset_index(drop=True)
    pdf["stat_date"] = pd.to_datetime(pdf["stat_date"])
    # t：时间序号 0,1,2,...，用于刻画充电网络扩张带来的长期增长趋势
    pdf["t"] = np.arange(len(pdf))
    # dow：星期几（0=周一 ~ 6=周日），捕捉周内周期效应
    pdf["dow"] = pdf["stat_date"].dt.dayofweek
    # is_weekend / month：备选特征，当前候选特征组未使用，保留供扩展实验
    pdf["is_weekend"] = (pdf["dow"] >= 5).astype(int)
    pdf["month"] = pdf["stat_date"].dt.month
    # 法定节假日（有节日名）与真休息日（周末+节假日，已考虑调休上班）
    pdf["is_holiday"] = pdf["stat_date"].map(is_holiday).astype(int)
    pdf["is_rest"] = pdf["stat_date"].map(is_rest).astype(int)
    # dow_0..dow_6：星期几的 one-hot 编码，专供无法自动拆分类别的线性模型使用
    for k in range(7):
        pdf[f"dow_{k}"] = (pdf["dow"] == k).astype(int)
    # lag{lag}_kwh：lag 天前的电量；shift(lag) 保证不含当天信息
    for lag in (1, 2, 3, 7, 14):
        pdf[f"lag{lag}_kwh"] = pdf["total_kwh"].shift(lag)
    # roll7/14_kwh：先 shift(1) 排除当天，再取前 7/14 天均值；
    # roll14_kwh 即最终部署方案（train.py）使用的趋势锚点
    pdf["roll7_kwh"] = pdf["total_kwh"].shift(1).rolling(7).mean()
    pdf["roll14_kwh"] = pdf["total_kwh"].shift(1).rolling(14).mean()
    return pdf


# 特征组定义：
#   F_CAL   纯日历特征（不含 t）——趋势交给锚点，模型只学"星期几/节假日"的相对高低；
#   F_CAL_T 日历 + 时间趋势，供树模型实验对比；
#   F_LIN   线性模型专用：t 可外推线性趋势，星期几需 one-hot 而非数值编码。
F_CAL = ["dow", "is_holiday", "is_rest"]
F_CAL_T = F_CAL + ["t"]
F_LIN = ["t"] + [f"dow_{k}" for k in range(7)] + ["is_holiday", "is_rest"]


def smape(y, p):
    """对称平均绝对百分比误差（sMAPE），取值 0~200%。

    与量纲无关的相对误差指标；分母为实际值与预测值之和（再乘 2），
    对"预测远大于实际"的情形比 MAPE 更稳健。
    """
    # +1e-9 防止实际值与预测值同时为 0 时除零
    return float(np.mean(2 * np.abs(y - p) / (np.abs(y) + np.abs(p) + 1e-9)) * 100)


def evaluate(y_true, y_pred):
    """计算一组评估指标。

    Args:
        y_true: 真实电量序列。
        y_pred: 预测电量序列。

    Returns:
        tuple: (MAE 平均绝对误差[度], RMSE 均方根误差[度], sMAPE[百分比])。
    """
    return (
        mean_absolute_error(y_true, y_pred),
        float(np.sqrt(mean_squared_error(y_true, y_pred))),
        smape(y_true, y_pred),
    )


def _ratio(model, feats, train_df, test_df, anchor):
    """训练"比例回归"模型并返回预测值（锚点 × 比例）。

    不直接回归电量绝对值，而是让模型学习 ``当日电量 / 锚点`` 的相对比例，
    趋势外推完全交给锚点（前 14 天均值），规避树模型无法外推的缺陷。

    Args:
        model: 未训练的 sklearn 回归器（函数内就地 fit）。
        feats: 特征列名列表。
        train_df: 训练集 DataFrame。
        test_df: 测试集 DataFrame。
        anchor: 锚点列名（如 ``roll14_kwh``）。

    Returns:
        numpy.ndarray: 测试集电量预测值。
    """
    # 训练目标：当日电量相对锚点的倍率
    model.fit(train_df[feats], train_df[TARGET] / train_df[anchor])
    # clip(0, 3)：把倍率限制在 0~3，防止异常值把预测带偏
    pred = np.clip(model.predict(test_df[feats]), 0.0, 3.0)
    return test_df[anchor].values * pred


def predict(spec, train_df, test_df):
    """按候选方案 (name, feats, model, mode) 训练并预测。

    Args:
        spec: 四元组 (名称, 特征列, 模型实例或 None, 预测模式)。
        train_df: 训练集 DataFrame。
        test_df: 测试集 DataFrame。

    Returns:
        numpy.ndarray: 测试集上的电量预测值。

    Raises:
        ValueError: mode 不在支持的模式列表中。
    """
    name, feats, model, mode = spec
    # 朴素基准：直接拿 7 天前的实际值当预测，用于衡量其他模型是否值得
    if mode == "naive_lag7":
        return test_df["lag7_kwh"].values
    # 直接回归绝对值（对照组）：树模型会暴露无法外推趋势的问题
    if mode == "raw":
        model.fit(train_df[feats], train_df[TARGET])
        return model.predict(test_df[feats])
    # 比例回归：锚点 × 倍率
    if mode == "ratio_roll14":
        return _ratio(model, feats, train_df, test_df, "roll14_kwh")
    # 对数比例回归：目标 = log(电量/锚点)，预测时 exp 还原；
    # 最终部署方案（train.py）采用的就是该形式
    if mode == "logratio_roll14":
        model.fit(
            train_df[feats],
            np.log((train_df[TARGET] / train_df["roll14_kwh"]).clip(lower=1e-3)),
        )
        return test_df["roll14_kwh"].values * np.clip(
            np.exp(model.predict(test_df[feats])), 0.0, 3.0
        )
    # 集成：比例模型与线性趋势模型各占 0.5 权重取平均
    if mode == "ensemble":
        a = _ratio(model, feats, train_df, test_df, "roll14_kwh")
        lin = Ridge(alpha=1.0)
        lin.fit(train_df[F_LIN], train_df[TARGET])
        return 0.5 * a + 0.5 * lin.predict(test_df[F_LIN])
    raise ValueError(mode)


# 候选模型清单，每项为 (名称, 特征组, 模型实例或 None, 预测模式)。
# 其中 naive_lag7 为无参数基准；gbr_ratio14 系列为"锚点+比例"核心方案的不同变体；
# rf_ratio14 换用随机森林对照；ens_ratio14_lin 检验与线性模型集成的增益。
CANDIDATES = [
    ("naive_lag7", None, None, "naive_lag7"),
    ("lin_trend", F_LIN, Ridge(alpha=1.0), "raw"),
    (
        "gbr_ratio14",
        F_CAL_T,
        GradientBoostingRegressor(random_state=42),
        "ratio_roll14",
    ),
    (
        "gbr_ratio14_cal",
        F_CAL,
        GradientBoostingRegressor(random_state=42),
        "ratio_roll14",
    ),
    (
        "gbr_logratio14",
        F_CAL_T,
        GradientBoostingRegressor(random_state=42),
        "logratio_roll14",
    ),
    (
        "rf_ratio14",
        F_CAL_T,
        RandomForestRegressor(n_estimators=400, random_state=42),
        "ratio_roll14",
    ),
    (
        "ens_ratio14_lin",
        F_CAL_T,
        GradientBoostingRegressor(random_state=42),
        "ensemble",
    ),
]


def walk_forward(spec, pdf, start=110, step=21, horizon=21):
    """扩展窗口滚动验证（walk-forward）：训练 [0,i]，预测 [i, i+horizon)。

    每折用"从第一天到 i"的全部历史训练、预测之后 horizon 天，i 每次前移
    step 天。相比单一验证窗口，能平均掉某个时间段的偶然性，选型更稳健。

    Args:
        spec: 候选方案四元组，见 ``predict``。
        pdf: 已构造特征的完整序列 DataFrame。
        start: 首折的训练集长度（前 110 天保证有足够历史做 lag/rolling）。
        step: 相邻两折之间训练集长度的增量（约 3 周）。
        horizon: 每折预测的未来天数。

    Returns:
        tuple: (各折平均 MAE, 各折 MAE 标准差, 折数)。
    """
    maes = []
    i = start
    # 至少留 5 天做测试集，避免末尾出现无意义的超短折
    while i + 5 <= len(pdf):
        tr, te = pdf.iloc[:i], pdf.iloc[i : i + horizon]
        pred = predict(spec, tr, te)
        maes.append(mean_absolute_error(te[TARGET], pred))
        i += step
    return float(np.mean(maes)), float(np.std(maes)), len(maes)


def main():
    """实验入口：对全部候选方案跑滚动验证与独立测试，输出对比表并选优。

    选型依据：以滚动验证平均 MAE 为主（更稳健），独立 test 指标仅作参考。
    """
    # 特征构造后 dropna()：去掉前若干天因 lag/rolling 信息不足产生的 NaN 行
    pdf = build_features(load_data()).dropna().reset_index(drop=True)
    # 按时间 8/2 切分（禁止随机打乱，保证测试集是"真未来"）
    i_test = int(len(pdf) * 0.8)
    tr, te = pdf.iloc[:i_test], pdf.iloc[i_test:]

    print("=" * 84)
    print(
        f"样本 {len(pdf)} 天 | 滚动验证范围 {pdf['stat_date'].iloc[110].date()}~{pdf['stat_date'].iloc[-1].date()}"
        f" | 最终 test {len(te)} 天 ({te['stat_date'].min().date()}~{te['stat_date'].max().date()}, 均值{te[TARGET].mean():.1f})"
    )
    print("=" * 84)
    print(
        f"{'模型':<18}{'WF平均MAE':>11}{'WF标准差':>10}{'折数':>6}{'|':>3}{'test MAE':>10}{'test RMSE':>11}{'test sMAPE':>12}"
    )
    print("-" * 84)
    rows = []
    for spec in CANDIDATES:
        wf_mae, wf_std, folds = walk_forward(spec, pdf)
        tp = predict(spec, tr, te)
        t_mae, t_rmse, t_sm = evaluate(te[TARGET], tp)
        rows.append((spec[0], wf_mae, t_mae, t_rmse, t_sm))
        print(
            f"{spec[0]:<18}{wf_mae:>11.2f}{wf_std:>10.2f}{folds:>6}{'|':>3}{t_mae:>10.2f}{t_rmse:>11.2f}{t_sm:>11.1f}%"
        )
    print("-" * 84)
    best = min(rows, key=lambda r: r[1])
    print(
        f"按滚动验证平均 MAE 选优：{best[0]}  (WF MAE={best[1]:.2f}, test MAE={best[2]:.2f}, test sMAPE={best[4]:.1f}%)"
    )


if __name__ == "__main__":
    main()
