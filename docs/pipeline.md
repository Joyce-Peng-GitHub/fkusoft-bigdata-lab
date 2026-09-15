# 充电分析数据仓库

原始三份 CSV 从 `data/source/` 迁移到 `data/raw/`，内容保持不变。
执行 `docker compose exec backend sh /workspace/scripts/run-pipeline.sh`：
HDFS `/charging/raw` → Hive ODS 原始字符串 → DWD 类型转换、隔离异常、订单去重与站点关联 → DWS 聚合 → ADS 展示契约 → MySQL。
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
