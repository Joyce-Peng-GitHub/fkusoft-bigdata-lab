# 充电分析数据仓库

原始三份 CSV 从 `data/source/` 迁移到 `data/raw/`，内容保持不变。
执行 `docker compose exec backend sh /workspace/scripts/run-pipeline.sh`：
HDFS `/charging/raw` → Hive ODS 原始字符串 → DWD 类型转换、隔离异常、订单去重与站点关联 → DWS 聚合 → ADS 展示契约 → MySQL。
各层由独立脚本实现，`run-pipeline.sh` 依次 `spark-submit`：`spark/ods.py` → `spark/dwd.py` → `spark/dws.py` → `spark/ads.py`，每层可单独重跑；`spark/pipeline.py` 为一次性编排入口。
Hive 使用 Spark 内置 Hive 支持，Derby metastore 持久化到 `/hadoop-data/metastore`，表文件保存在 HDFS。
不依赖独立 HiveServer2；可在同一 metastore 目录使用 spark-sql 查询。不要并发打开嵌入式 metastore。

分析维度：月份、小时、星期、平台、设施类型、站点、地点、时长区间、电量区间、管理车辆标识。
交叉对比：平台 × 设施类型、星期 × 小时。指标包括订单量、电量、费用、平均时长及加权平均功率（总电量 / 总充电小时，不代表设备额定功率）。
电池另提供 SOC 分段的温度与单体压差统计，独立聚合，避免一对多关联放大订单总量。

`0014` / `0015` 年按 2014 / 2015 解释，其他年份不改写；星期和小时由修正日期重新计算。
站点资料是 2019 年快照，名称仅用于标注，不推断历史设备容量或利用率。
遥测 `record_time` 已被科学计数法截断，无法恢复，不用于时序或同步关联。
订单类型转换失败、负电量/费用、非正时长、日期倒序等进入 `dwd.rejected_sessions`。
完全重复订单去重，冲突主键立即报错；缺站点资料保留订单并使用站点编号。
每个聚合维度验证订单数等于 DWD 总数；输出质量计数随 API 提供。

## REST 接口

- `GET /api/health`：已发布数据就绪返回 200；尚未发布或数据库故障返回 503。
- `GET /api/dashboard`：指标、12 组分析、电池统计、数据质量和生成时间。
- `GET /api/analysis/<dimension>`：单维或交叉分析；未知维度返回 404。
- `GET /api/ml/forecast`：ML 预测的历史实际与未来若干天；尚未生成或数据库故障返回 503。

Flask 只查询 MySQL，不在请求线程执行 Spark，也不回退到本地文件或模拟数据。
MySQL `dashboard_snapshot` 保存 ADS 的完整 JSON 契约；单行事务更新保证请求读取同一批次。
ML 预测以同样方式存入 `forecast_snapshot`（独立表、独立事务），由 `ml/predict.py` 发布。
重复执行流水线覆盖 Hive 表和 MySQL 快照，不累加数据。失败时大屏仍可读取上次成功发布的数据，生成时间用于识别旧批次。

大屏在展示边界统一格式化数值：电量、费用、时长及温度最多两位小数，订单量及采样量按整数展示。
图表悬浮提示、数值坐标轴与热力图图例使用同一精度口径；原始分析值保留用于绘图和排名，不提前截断。
