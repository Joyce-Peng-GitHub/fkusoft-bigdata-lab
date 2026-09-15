# ML 模块 —— 充电负荷预测（时间序列）

基于历史充电数据预测**未来若干天的日充电量**，并给出辅助的订单数估算。
本模块是数据仓库四层之上的应用：**读取 DWD 明细 → 生成日序列（DWS）→ 输出预测（ADS）→ 供后端 REST 与前端大屏使用**。

> 数据源：本模块读取仓库 Hive 表 `dws.daily_series`（由 `spark/pipeline.py` 从 `dwd.sessions`
> 按天聚合产出，见 `ml/sql/00_build_timeseries.sql` 中的等价 SQL）。

---

## 目录结构

```
ml/
├── README.md                  # 本文档
├── requirements.txt           # Python 依赖（pandas / scikit-learn / chinesecalendar）
├── sql/
│   └── 00_build_timeseries.sql# 从明细聚合出“日期 × 电量”日粒度时间序列
├── holidays.py                # 节假日/休息日（chinesecalendar，含调休）
├── experiment.py              # 模型选型实验（滚动前推验证）
├── train.py                   # 训练 + 评估 + 保存模型
├── predict.py                 # 未来 N 天递归预测
├── model_forecast.pkl         # 训练产物（运行 train.py 生成，不纳入版本管理）
└── forecast_result.csv        # 预测产物（运行 predict.py 生成，不纳入版本管理）
```

## 在四层架构中的位置

| 层 | 本模块对应物 | 说明 |
|----|-------------|------|
| ODS | 复用仓库现有 `ods.sessions` | 原始 CSV 入库，不重复建设 |
| DWD | 复用仓库现有 `dwd.sessions` | 已清洗、已还原 `started` 时间戳的会话明细 |
| DWS | **本模块的日粒度时间序列** | 按天聚合的电量/订单/活跃站点，作为预测输入 |
| ADS | **预测结果表**（如 `ads.ml_forecast`）| 未来 N 天的预测值，供后端与前端读取 |

即：ML 不新增 ODS/DWD，而是在现有 DWD 之上产出 **DWS 序列** 与 **ADS 预测**，与仓库分层保持一致。

## 数据契约

### 输入（本模块需要的最小字段）

来自会话明细（本仓库为 `dwd.sessions`）：

| 字段 | 含义 |
|------|------|
| `started` | 充电开始时间（时间戳，仓库已把 `0014/0015` 修正为 `2014/2015`）|
| `energy` | 单次充电电量（度）|
| `station` | 站点编号（用于统计活跃站点数）|

按天聚合后得到日序列（本模块数据源 `dws.daily_series`）：

| 字段 | 含义 |
|------|------|
| `stat_date` | 统计日期 |
| `sessions` | 当日订单数 |
| `total_kwh` | 当日总充电量（预测目标）|
| `total_fee` | 当日总费用 |
| `active_stations` / `active_users` | 当日活跃站点/用户数 |

### 输出

预测结果（建议落地为 `ads.ml_forecast`）：

| 字段 | 含义 |
|------|------|
| `forecast_date` | 预测日期 |
| `pred_kwh` | 预测充电量（度）|
| `pred_sessions` | 预测订单数（辅助，线性估算）|
| `is_holiday` | 是否法定节假日 |
| `generated_at` | 预测生成时间 |

## 建模方法

数据存在**强增长趋势**（充电网络扩张期，月订单从个位数涨到数百），且树模型无法外推超出训练范围的数值。
因此不直接回归电量绝对值，而是**预测“相对最近水平的倍率”**：

```
kwĥ(t) = clip( exp( f(t, dow, is_holiday, is_rest) ), 0, 3 ) × 前14天均值(t)
```

- `f(...)`：`GradientBoostingRegressor`，训练目标是 `y = log(当日电量 / 前14天均值)`；
- **趋势由锚点（前14天均值）自动跟随**，模型只负责学“星期几 / 节假日”的相对高低；
- `clip(..., 0, 3)`：把倍率限制在 0~3，防止异常值把预测带偏；
- 特征：`t`（时间序号）、`dow`（星期几）、`is_holiday`（法定节假日）、`is_rest`（真休息日，含调休）；
- 掌握趋势外推与周末/节假日效应是本方案相对“直接回归”的核心改进。

### 验证方式

- **按时间切分**，禁止随机打乱：前 80% 天训练、后 20% 天测试；
- **滚动前推验证（walk-forward）**：6 折扩展窗口，用于模型选型，避免单一窗口的偶然性；
- 指标：MAE（平均绝对误差）、RMSE、sMAPE。

### 参考结果（当前数据集，2014-11 ~ 2015-10 共 237 天）

| 指标 | 本模型 | 对照：14 天均值 | 对照：朴素 lag7 |
|------|------:|---------------:|---------------:|
| 滚动验证 MAE | **23.35** | — | 39.87 |
| test MAE | **30.31** | 73.88 | 42.21 |
| test sMAPE | **33.4%** | — | 45.2% |

## 运行

依赖通过独立虚拟环境安装（PySpark 使用 Spark 自带，不通过 pip）：

```sh
python3 -m venv ml/venv
ml/venv/bin/pip install --only-binary=:all: -r ml/requirements.txt \
  -i https://pypi.tuna.tsinghua.edu.cn/simple
```

```sh
# 1) 生成日粒度时间序列（Hive；当前集群命令，接入本仓库后改为对 dwd.sessions 聚合）
spark-sql -f ml/sql/00_build_timeseries.sql

# 2) 训练 + 评估（生成 ml/model_forecast.pkl）
export SPARK_HOME=/opt/module/spark-3.4.1
export PYTHONPATH=$SPARK_HOME/python:$SPARK_HOME/python/lib/py4j-0.10.9.7-src.zip
ml/venv/bin/python ml/train.py

# 3) 预测未来 7 天（生成 ml/forecast_result.csv）
ml/venv/bin/python ml/predict.py 7

# 可选：复现模型选型实验
ml/venv/bin/python ml/experiment.py
```

## 接入本仓库

本仓库的 `spark/pipeline.py` 已在 `dwd.sessions` 中提供带正确时间戳的会话明细，
因此可直接从 `dwd.sessions` 聚合出日序列，**无需** `ncs-dashboard` 中针对 `created` 字段的日期还原逻辑。

已完成：

1. ✅ `dws.daily_series` 日序列表：`spark/pipeline.py` 在 DWD 之后按 `to_date(started)` 聚合产出
   （`ml/sql/00_build_timeseries.sql` 为等价的 spark-sql 独立重建脚本，二选一执行）；
2. ✅ `train.py` / `predict.py` 数据源已改为 `dws.daily_series`。

待办：

3. 预测结果写入 ADS（如 `ads.ml_forecast`），并加入 `publish` 流程；
4. 后端新增 `GET /api/ml/forecast`，返回“历史实际 + 未来预测”，供前端大屏绘图。

## 已知限制

- **预测粒度为“天”**：原始数据小时维度过于稀疏（仅约 27% 的“日期×小时”时段有订单），
  逐小时负荷预测在该数据上不可信，故不做 1h/24h 级预测；
- **仅有 11 个月**数据，学不到完整年度季节性；
- **无天气、用户出行等外部特征**，不可在对外描述中宣称使用这些特征；
- 订单数为线性辅助估算，并非独立建模；
- 节假日依赖 `chinesecalendar`（支持 2004~2026），超出范围时退回“周末即休息”。