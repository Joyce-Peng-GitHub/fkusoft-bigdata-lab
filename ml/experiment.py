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
    pdf = pdf.sort_values("stat_date").reset_index(drop=True)
    pdf["stat_date"] = pd.to_datetime(pdf["stat_date"])
    pdf["t"] = np.arange(len(pdf))
    pdf["dow"] = pdf["stat_date"].dt.dayofweek
    pdf["is_weekend"] = (pdf["dow"] >= 5).astype(int)
    pdf["month"] = pdf["stat_date"].dt.month
    pdf["is_holiday"] = pdf["stat_date"].map(is_holiday).astype(int)
    pdf["is_rest"] = pdf["stat_date"].map(is_rest).astype(int)
    for k in range(7):
        pdf[f"dow_{k}"] = (pdf["dow"] == k).astype(int)
    for lag in (1, 2, 3, 7, 14):
        pdf[f"lag{lag}_kwh"] = pdf["total_kwh"].shift(lag)
    pdf["roll7_kwh"] = pdf["total_kwh"].shift(1).rolling(7).mean()
    pdf["roll14_kwh"] = pdf["total_kwh"].shift(1).rolling(14).mean()
    return pdf


F_CAL = ["dow", "is_holiday", "is_rest"]
F_CAL_T = F_CAL + ["t"]
F_LIN = ["t"] + [f"dow_{k}" for k in range(7)] + ["is_holiday", "is_rest"]


def smape(y, p):
    return float(np.mean(2 * np.abs(y - p) / (np.abs(y) + np.abs(p) + 1e-9)) * 100)


def evaluate(y_true, y_pred):
    return (mean_absolute_error(y_true, y_pred),
            float(np.sqrt(mean_squared_error(y_true, y_pred))),
            smape(y_true, y_pred))


def _ratio(model, feats, train_df, test_df, anchor):
    model.fit(train_df[feats], train_df[TARGET] / train_df[anchor])
    pred = np.clip(model.predict(test_df[feats]), 0.0, 3.0)
    return test_df[anchor].values * pred


def predict(spec, train_df, test_df):
    name, feats, model, mode = spec
    if mode == "naive_lag7":
        return test_df["lag7_kwh"].values
    if mode == "raw":
        model.fit(train_df[feats], train_df[TARGET])
        return model.predict(test_df[feats])
    if mode == "ratio_roll14":
        return _ratio(model, feats, train_df, test_df, "roll14_kwh")
    if mode == "logratio_roll14":
        model.fit(train_df[feats], np.log((train_df[TARGET] / train_df["roll14_kwh"]).clip(lower=1e-3)))
        return test_df["roll14_kwh"].values * np.clip(np.exp(model.predict(test_df[feats])), 0.0, 3.0)
    if mode == "ensemble":
        a = _ratio(model, feats, train_df, test_df, "roll14_kwh")
        lin = Ridge(alpha=1.0)
        lin.fit(train_df[F_LIN], train_df[TARGET])
        return 0.5 * a + 0.5 * lin.predict(test_df[F_LIN])
    raise ValueError(mode)


CANDIDATES = [
    ("naive_lag7",       None,   None, "naive_lag7"),
    ("lin_trend",        F_LIN,  Ridge(alpha=1.0), "raw"),
    ("gbr_ratio14",      F_CAL_T, GradientBoostingRegressor(random_state=42), "ratio_roll14"),
    ("gbr_ratio14_cal",  F_CAL,   GradientBoostingRegressor(random_state=42), "ratio_roll14"),
    ("gbr_logratio14",   F_CAL_T, GradientBoostingRegressor(random_state=42), "logratio_roll14"),
    ("rf_ratio14",       F_CAL_T, RandomForestRegressor(n_estimators=400, random_state=42), "ratio_roll14"),
    ("ens_ratio14_lin",  F_CAL_T, GradientBoostingRegressor(random_state=42), "ensemble"),
]


def walk_forward(spec, pdf, start=110, step=21, horizon=21):
    """扩展窗口滚动验证：训练 [0,i]，预测 [i,i+h)，i 逐步前移"""
    maes = []
    i = start
    while i + 5 <= len(pdf):
        tr, te = pdf.iloc[:i], pdf.iloc[i:i + horizon]
        pred = predict(spec, tr, te)
        maes.append(mean_absolute_error(te[TARGET], pred))
        i += step
    return float(np.mean(maes)), float(np.std(maes)), len(maes)


def main():
    pdf = build_features(load_data()).dropna().reset_index(drop=True)
    i_test = int(len(pdf) * 0.8)
    tr, te = pdf.iloc[:i_test], pdf.iloc[i_test:]

    print("=" * 84)
    print(f"样本 {len(pdf)} 天 | 滚动验证范围 {pdf['stat_date'].iloc[110].date()}~{pdf['stat_date'].iloc[-1].date()}"
          f" | 最终 test {len(te)} 天 ({te['stat_date'].min().date()}~{te['stat_date'].max().date()}, 均值{te[TARGET].mean():.1f})")
    print("=" * 84)
    print(f"{'模型':<18}{'WF平均MAE':>11}{'WF标准差':>10}{'折数':>6}{'|':>3}{'test MAE':>10}{'test RMSE':>11}{'test sMAPE':>12}")
    print("-" * 84)
    rows = []
    for spec in CANDIDATES:
        wf_mae, wf_std, folds = walk_forward(spec, pdf)
        tp = predict(spec, tr, te)
        t_mae, t_rmse, t_sm = evaluate(te[TARGET], tp)
        rows.append((spec[0], wf_mae, t_mae, t_rmse, t_sm))
        print(f"{spec[0]:<18}{wf_mae:>11.2f}{wf_std:>10.2f}{folds:>6}{'|':>3}{t_mae:>10.2f}{t_rmse:>11.2f}{t_sm:>11.1f}%")
    print("-" * 84)
    best = min(rows, key=lambda r: r[1])
    print(f"按滚动验证平均 MAE 选优：{best[0]}  (WF MAE={best[1]:.2f}, test MAE={best[2]:.2f}, test sMAPE={best[4]:.1f}%)")


if __name__ == "__main__":
    main()