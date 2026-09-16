# -*- coding: utf-8 -*-
"""
NCS 充电桩 ML 子系统 —— 未来 N 天负荷预测（递归多步）
与 train.py 的方案配套：预测 = 前14天均值(锚点) × exp(模型输出)

运行：
  cd ~/ncs-dashboard
  export SPARK_HOME=/opt/module/spark-3.4.1
  export PYTHONPATH=$SPARK_HOME/python:$SPARK_HOME/python/lib/py4j-0.10.9.7-src.zip
  ml/venv/bin/python ml/predict.py [天数，默认 7]

说明：
  · 递归预测：第 i 天的锚点(前14天均值)里，早于“今天”的取真实值，之后取前面的预测值；
  · 订单数(pred_sessions)为辅助输出，用历史 kwh->sessions 线性关系估计，非主目标。
"""
import os
import sys
from datetime import datetime, timezone

from export import publish_forecast

os.environ.setdefault("SPARK_HOME", "/opt/module/spark-3.4.1")
SPARK_HOME = os.environ["SPARK_HOME"]
for _p in (
    os.path.join(SPARK_HOME, "python"),
    os.path.join(SPARK_HOME, "python", "lib", "py4j-0.10.9.7-src.zip"),
):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import joblib
import numpy as np
import pandas as pd
from pyspark.sql import SparkSession
from sklearn.linear_model import LinearRegression

from holidays import is_holiday, is_rest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_PATH = os.path.join(ROOT, "ml", "model_forecast.pkl")
OUT_CSV = os.path.join(ROOT, "ml", "forecast_result.csv")
N_FUTURE = int(sys.argv[1]) if len(sys.argv) > 1 else 7


def load_history():
    """读取历史日序列（dws.daily_series，由 dwd.sessions 按天聚合；最近的在最后）"""
    spark = (
        SparkSession.builder.appName("ncs-ml-predict")
        .enableHiveSupport()
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("ERROR")
    pdf = spark.sql(
        "SELECT * FROM dws.daily_series ORDER BY stat_date"
    ).toPandas()
    spark.stop()
    pdf["stat_date"] = pd.to_datetime(pdf["stat_date"])
    for c in ("total_kwh", "sessions"):
        pdf[c] = pd.to_numeric(pdf[c], errors="coerce")
    return pdf.sort_values("stat_date").reset_index(drop=True)


def main():
    """Predict daily load and publish CSV plus the atomic web JSON artifact."""
    if not 1 <= N_FUTURE <= 366:
        raise ValueError("预测天数必须在 1 到 366 之间")
    bundle = joblib.load(MODEL_PATH)
    model, feats = bundle["model"], bundle["features"]
    t_max = bundle.get("t_max", 0)

    print("=" * 60)
    print(f"  NCS 充电负荷预测 —— 未来 {N_FUTURE} 天")
    print("=" * 60)

    hist = load_history()
    print(f"历史数据 {len(hist)} 天，最后一天 {hist['stat_date'].iloc[-1].date()}"
          f"（当日实际 {hist['total_kwh'].iloc[-1]:.1f} 度）")

    ses_model = LinearRegression().fit(hist[["total_kwh"]], hist["sessions"])

    kwh = list(hist["total_kwh"].values)
    ses = list(hist["sessions"].values)
    last_date = hist["stat_date"].iloc[-1]

    rows = []
    for i in range(1, N_FUTURE + 1):
        d = last_date + pd.Timedelta(days=i)
        anchor = float(np.mean(kwh[-14:]))          # 前14天均值（真实或预测混合）
        feat = {
            "t": t_max + i,
            "dow": d.dayofweek,
            "is_holiday": is_holiday(d),
            "is_rest": is_rest(d),
        }
        X = pd.DataFrame([[feat[f] for f in feats]], columns=feats)
        ratio = float(np.clip(np.exp(model.predict(X)[0]), 0.0, 3.0))
        pred_kwh = anchor * ratio
        pred_ses = max(
            float(ses_model.predict(pd.DataFrame({"total_kwh": [pred_kwh]}))[0]), 0.0
        )
        kwh.append(pred_kwh)
        ses.append(pred_ses)
        rows.append({
            "forecast_date": d.strftime("%Y-%m-%d"),
            "weekday": d.strftime("%a"),
            "is_holiday": feat["is_holiday"],
            "pred_kwh": round(pred_kwh, 2),
            "pred_sessions": round(pred_ses, 2),
        })

    print("-" * 60)
    print("最近 5 天真实值（供对照）：")
    for _, r in hist.tail(5).iterrows():
        print(f"  {r['stat_date'].date()}  {r['stat_date'].strftime('%a')}  "
              f"{r['total_kwh']:8.1f} 度  {int(r['sessions']):3d} 单")

    result = pd.DataFrame(rows)
    print("-" * 60)
    print(f"未来 {N_FUTURE} 天预测：")
    print(result.to_string(index=False))

    result.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    print("-" * 60)
    print(f"预测结果已保存：{OUT_CSV}")
    # Dates follow the source dataset, not the wall clock. Keep actual values and
    # model estimates separate so the web chart cannot imply observed future data.
    # The CSV is a human-readable copy; MySQL is the artifact the REST API serves.
    publish_forecast({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "history_end": last_date.strftime("%Y-%m-%d"),
        "history": [{"date": r["stat_date"].strftime("%Y-%m-%d"),
                     "energy": float(r["total_kwh"]), "sessions": int(r["sessions"])}
                    for _, r in hist.tail(14).iterrows()],
        "forecast": [{"date": r["forecast_date"], "energy": r["pred_kwh"],
                      "sessions": r["pred_sessions"]} for r in rows],
    })
    print("预测快照已发布到 MySQL（forecast_snapshot）")


if __name__ == "__main__":
    main()