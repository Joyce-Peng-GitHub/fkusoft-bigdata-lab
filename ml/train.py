# -*- coding: utf-8 -*-
"""
NCS 充电桩 ML 子系统 —— 日负荷预测训练
方案（经 ml/experiment.py 滚动前推验证选出）：
  预测“相对水平”而非绝对值：
      目标 = log(当日充电量 / 前14天均值)
      预测 = 前14天均值 × exp(模型输出)
  这样增长趋势由锚点(前14天均值)自动跟随，模型只负责学“星期几 / 节假日”的影响，
  避免了树模型无法外推趋势的问题。

流程：读 Hive(dws.daily_series) -> 特征 -> 按时间切分 -> 训练 -> 评估 -> 全量重训保存

运行：
  cd ~/ncs-dashboard
  export SPARK_HOME=/opt/module/spark-3.4.1
  export PYTHONPATH=$SPARK_HOME/python:$SPARK_HOME/python/lib/py4j-0.10.9.7-src.zip
  ml/venv/bin/python ml/train.py
"""

import os
import sys

os.environ.setdefault("SPARK_HOME", "/opt/module/spark-3.4.1")
SPARK_HOME = os.environ["SPARK_HOME"]
if os.path.join(SPARK_HOME, "python") not in sys.path:
    sys.path.insert(0, os.path.join(SPARK_HOME, "python"))
    sys.path.insert(
        0, os.path.join(SPARK_HOME, "python", "lib", "py4j-0.10.9.7-src.zip")
    )

import joblib
import numpy as np
import pandas as pd
from pyspark.sql import SparkSession
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

from holidays import is_holiday, is_rest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_PATH = os.path.join(ROOT, "ml", "model_forecast.pkl")

TARGET = "total_kwh"
ANCHOR = "roll14_kwh"  # 锚点：前 14 天均值（不含当天）
FEATURES = ["t", "dow", "is_holiday", "is_rest"]
LOG_TARGET = True


def load_data():
    """从 Hive 读取按日期升序排列的日粒度负荷序列。

    ``dws.daily_series`` 由流水线从 ``dwd.sessions`` 按天聚合，是训练与
    预测共同使用的数据契约。

    Returns:
        pandas.DataFrame: ``stat_date`` 已转换为时间类型的日粒度序列。
    """
    spark = (
        SparkSession.builder.appName("ncs-ml-train").enableHiveSupport().getOrCreate()
    )
    spark.sparkContext.setLogLevel("ERROR")
    pdf = spark.sql("SELECT * FROM dws.daily_series ORDER BY stat_date").toPandas()
    spark.stop()
    pdf["stat_date"] = pd.to_datetime(pdf["stat_date"])
    return pdf.sort_values("stat_date").reset_index(drop=True)


def build_features(pdf):
    """构造不泄露当天真实值的训练特征和对数比例目标。

    Args:
        pdf: 至少包含 ``stat_date`` 和 ``total_kwh`` 的日粒度数据，输入
            顺序不限。

    Returns:
        pandas.DataFrame: 按日期重排并附加时间、日历、14 日锚点和训练
            目标的新特征表。最前面的 14 行因历史不足而具有空锚点，由
            调用方决定如何处理。
    """
    pdf = pdf.sort_values("stat_date").reset_index(drop=True)
    pdf["stat_date"] = pd.to_datetime(pdf["stat_date"])
    pdf["t"] = np.arange(len(pdf))
    pdf["dow"] = pdf["stat_date"].dt.dayofweek
    pdf["is_holiday"] = pdf["stat_date"].map(is_holiday).astype(int)
    pdf["is_rest"] = pdf["stat_date"].map(is_rest).astype(int)  # 真休息日(含调休)
    pdf[ANCHOR] = pdf[TARGET].shift(1).rolling(14).mean()  # 只用历史，防泄露
    pdf["y"] = np.log((pdf[TARGET] / pdf[ANCHOR]).clip(lower=1e-3))
    return pdf


def smape(y, p):
    """计算对称平均绝对百分比误差。

    Args:
        y: 实际值数组。
        p: 与实际值形状一致的预测值数组。

    Returns:
        float: 以百分比表示的 sMAPE；极小常数用于处理实际值和预测值
            同时为零的样本。
    """
    return float(np.mean(2 * np.abs(y - p) / (np.abs(y) + np.abs(p) + 1e-9)) * 100)


def inverse(model, X, anchor_values):
    """把模型输出的对数比例还原为负荷预测值。

    Args:
        model: 已训练且实现 ``predict`` 的回归模型。
        X: 与模型特征契约一致的样本矩阵。
        anchor_values: 每个样本在预测时可获得的 14 日均值锚点。

    Returns:
        numpy.ndarray: 锚点乘以预测比例后的负荷值。比例限制在 0 到 3，
            避免指数还原后的异常值无限放大。
    """
    ratio = np.clip(np.exp(model.predict(X)), 0.0, 3.0)
    return anchor_values * ratio


def main():
    """按时间评估模型，并用全部可用样本重训部署模型。"""
    print("=" * 62)
    print("  NCS 充电负荷预测 —— 训练")
    print("=" * 62)

    raw = load_data()
    pdf = build_features(raw).dropna(subset=[ANCHOR]).reset_index(drop=True)
    print(f"时间序列 {len(raw)} 天 -> 可用 {len(pdf)} 天（前 14 天无锚点）")

    split = int(len(pdf) * 0.8)
    train, test = pdf.iloc[:split], pdf.iloc[split:]
    print(
        f"按时间切分：训练 {len(train)} 天 ({train['stat_date'].min().date()}~{train['stat_date'].max().date()}) | "
        f"测试 {len(test)} 天 ({test['stat_date'].min().date()}~{test['stat_date'].max().date()})"
    )

    model = GradientBoostingRegressor(random_state=42)
    model.fit(train[FEATURES], train["y"])
    pred = inverse(model, test[FEATURES], test[ANCHOR].values)

    mae = mean_absolute_error(test[TARGET], pred)
    rmse = np.sqrt(mean_squared_error(test[TARGET], pred))
    base = mean_absolute_error(
        test[TARGET], test["roll7_kwh"] if "roll7_kwh" in test else test[ANCHOR]
    )
    print("-" * 62)
    print("测试集评估：")
    print(f"  MAE  = {mae:8.2f} 度")
    print(f"  RMSE = {rmse:8.2f} 度")
    print(f"  sMAPE= {smape(test[TARGET].values, pred):8.2f}%")
    print(f"  （对照：直接拿14天均值当预测的 MAE = {base:.2f} 度）")
    print("-" * 62)

    cmp = pd.DataFrame(
        {
            "日期": test["stat_date"].dt.strftime("%Y-%m-%d").values,
            "实际": np.round(test[TARGET].values, 1),
            "预测": np.round(pred, 1),
        }
    )
    print("测试期末尾 10 天 实际 vs 预测：")
    print(cmp.tail(10).to_string(index=False))

    # 部署模型：用全部数据重训一次，捕捉最新水平
    model_all = GradientBoostingRegressor(random_state=42)
    model_all.fit(pdf[FEATURES], pdf["y"])
    joblib.dump(
        {
            "model": model_all,
            "features": FEATURES,
            "target": TARGET,
            "anchor": ANCHOR,
            "log_target": LOG_TARGET,
            "t_max": int(pdf["t"].max()),
        },
        MODEL_PATH,
    )
    print("-" * 62)
    print(f"部署模型已保存（用全部 {len(pdf)} 天重训）：{MODEL_PATH}")


if __name__ == "__main__":
    main()
