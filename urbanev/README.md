# UrbanEV 数据源：数据探查与仓库分层设计

本目录是独立的数据源实验分支：把公开基准数据集
[UrbanEV](https://github.com/IntelligentSystemsLab/UrbanEV)（深圳 EV 充电，CC0 许可）
按本仓库的 ODS/DWD/DWS/ADS 四层规范落地，并验证"小时级 + 天气特征"的负荷预测。
与本仓库原有郑州订单数据完全独立，表名统一加 `urbanev_` 前缀，互不干扰。

- 数据集论文：UrbanEV: An Open Benchmark Dataset for Urban Electric Vehicle Charging
  Demand Prediction, Scientific Data (2025), doi:10.1038/s41597-025-04874-4
- 官方原始发布：https://doi.org/10.5061/dryad.np5hqc04z ；GitHub 仓库内 `data/` 为
  已清洗的 1 小时 × 小区级预聚合数据（本分支即用这一份）

## 数据画像（实测，2026-09-15 于本机）

| 项目 | 实测值 |
|------|--------|
| 时间范围 | 2022-09-01 00:00 ~ 2023-02-28 23:00，共 181 天 × 24 = **4344 小时** |
| 空间范围 | **275 个交通小区（TAZ）**、1362 站、17532 桩 |
| 文件形态 | 宽表：`time` + 275 个小区列（volume/occupancy/duration/e_price/s_price 等） |
| 缺失情况 | `volume.csv` 4344×275 无一空值；`weather_central.csv` 4344 行零空值 |
| 城市小时总电量 | 均值约 7.2 万 kWh，区间 0.95 万 ~ 14.1 万 |
| 城市日总电量 | 均值 172 万 kWh，区间 78.9 万 ~ 213.5 万 |
| 月度城市总电量 | 9月 5764 万 → 12月 5626 万 → **1月 4401 万**（2023 春节 1/21~1/27 拉低） |
| 星期效应 | 弱：周六均值 178.8 万最高，周日 170.9 万最低，工作日约 170 万 |
| 小时效应 | 强：0~1 点约 10.8 万 kWh 高峰，11 点 4.6 万低谷（日内 2.4 倍差） |
| 天气（central 站） | 气温 8.3 ~ 34.7 ℃；8.6% 的小时有雨（nRAIN≥1 共 372 小时） |

### 与本仓库现有郑州数据的对比

| 维度 | 现有郑州订单数据 | UrbanEV |
|------|------------------|---------|
| 时间粒度 | 日（小时覆盖率仅约 27%，小时级预测不可信） | **小时，全覆盖** |
| 空间粒度 | 单城市汇总 + 站点编号 | **275 小区 + 邻接矩阵 + 距离矩阵** |
| 外部特征 | 无天气、无出行 | **逐小时气象（气温/湿度/降雨等级）** |
| 趋势 | 强增长（网络扩张期，月订单个位数→数百） | 基本平稳（网络固定，春节回落） |
| 建模含义 | 必须用"相对锚点"法外推趋势 | 可直接回归日内/周内模式 + 天气响应 |

结论：UrbanEV 恰好补上现有数据的三个短板——**小时级预测可信、有真天气特征、有空间维度**，
而"趋势外推"这个原来的难点在这里不再是主要矛盾。

## 四层落地设计

| 层 | 表 | 内容与处理 |
|----|----|------------|
| ODS | `ods.urbanev_volume / _occupancy / _duration / _e_price / _s_price` | 宽表 CSV 原样入库（全字符串），HDFS `/urbanev/raw` |
| ODS | `ods.urbanev_weather_central / _weather_airport` | 气象站逐小时原始行（字符串） |
| ODS | `ods.urbanev_station / _adj / _distance / _poi` | 站点资料、275×275 邻接/距离矩阵、POI |
| DWD | `dwd.urbanev_load` | **核心事实表**：宽表 `unpivot` 成长表后按 `(ts, zone_id)` 对齐拼接 `volume_kwh / occupancy_pct / duration_h / e_price / s_price`，全 DOUBLE + 时间戳类型 |
| DWD | `dwd.urbanev_weather` | `weather_central` 类型化（时间解析 `yyyy/M/d H:mm`），列改名见下 |
| DWD | `dwd.urbanev_zone` | `inf.csv` 按 TAZID 汇总的维度表：站点数、桩数、面积、周长 |
| DWD | `dwd.urbanev_calendar` | 日历维度（chinesecalendar 生成）：`is_holiday` 法定假 / `is_rest` 真休息日（含调休） |
| DWD | `dwd.urbanev_rejected` | 类型转换失败、负值、时间缺失的行，留审计 |
| DWS | `dws.urbanev_city_hourly` | 全城逐小时：`total_kwh / total_duration_h / avg_occupancy_pct`，已关联天气 |
| DWS | `dws.urbanev_city_daily` | 全城逐日汇总（与郑州 `dws.daily_series` 同口径，便于对照） |
| DWS | `dws.urbanev_zone_daily` | 逐小区逐日 `total_kwh`（供后续空间/图模型） |
| ADS | `ads.urbanev_forecast_features` | **ML 输入契约**：逐小时电量 + 天气 + 日历特征，一行一时刻 |
| ADS | `ads.urbanev_forecast` | 预测输出（`urbanev/ml/predict.py` 写回） |

设计原则沿用 `spark/pipeline.py`：ODS 不加工、DWD 用 `try_cast` 显式暴露脏数据、
每层可独立用 spark-sql 复查、聚合结果做行数对账（宽表 4344×275 = 1,194,600 行）。

## ML 方案（与郑州 `ml/` 的差异）

- 目标：**逐小时全城充电量**（`total_kwh`），`log1p` 变换后回归；
- 特征：`t`（时间序号）、`hour`、`dow`、`is_holiday`、`is_rest`、`temp_c`、`humidity_pct`、`rain_level`；
- 模型：`GradientBoostingRegressor`（延续现有技术栈，不引入 torch）；
- 对照基线：上周同期值（lag 168h）、训练期"星期×小时"均值、**去掉天气特征的同模型**——
  用第三个对照量化天气特征的真实增量；
- 评估：按时间切分（测试集 = 最后 14 天 336 小时），MAE / RMSE / sMAPE；
- 预测：未来 24 小时递归；**天气输入用最近一天观测值滚动**（生产应接天气预报，文档如实注明）。

图模型（GCN/ASTGCN，利用 `adj/distance` 做小区级预测）不在本 PoC 范围，
`dws.urbanev_zone_daily` 与 ODS 矩阵表已为其备好数据。

## 运行（本课程本地集群）

```sh
# 0) 下载数据（约 110MB，走实验室代理；产物在 urbanev/data/raw/，不入库）
urbanev/fetch_data.sh

# 1) 四层落地（spark-submit 本地模式，写 Hive：ods/dwd/dws/ads）
spark-submit --master 'local[4]' urbanev/pipeline.py

# 2) 训练 + 评估（读 ads.urbanev_forecast_features）
ml/venv/bin/python urbanev/ml/train.py

# 3) 预测未来 24 小时并写回 ads.urbanev_forecast
ml/venv/bin/python urbanev/ml/predict.py 24
```

环境要求：Spark 3.4.1 + Hadoop 3.3.0（HDFS `hdfs://node100:9000`）+ Hive metastore（9083）；
Python 依赖见 `urbanev/ml/requirements.txt`（pandas / scikit-learn / chinesecalendar）。
