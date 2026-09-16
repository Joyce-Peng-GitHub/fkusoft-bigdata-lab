-- =====================================================================
-- NCS 充电桩 ML 子系统 —— 00 构建日粒度时间序列（本仓库版）
-- 文件：ml/sql/00_build_timeseries.sql
-- 目的：从 DWD 会话明细聚合出“按天”的充电量/订单数序列，产出 dws.daily_series，
--       作为 ml/train.py 与 ml/predict.py 的唯一数据源。
-- 数据源：dwd.sessions（本仓库 ODS→DWD 管线产出，started 已把 0014/0015 修正为 2014/2015）
-- 执行：spark-sql -f ml/sql/00_build_timeseries.sql
--       （自动流水线中该表由 spark/pipeline.py 以同一聚合逻辑产出，二者互为等价实现；
--         本仓库嵌入式 metastore 不支持并发写入，二选一执行即可）
-- 关键处理：
--   ① 表头行：ods 读入时 header=True，混入的表头经 try_cast 后 started 为 NULL，
--      已被 dwd.sessions 的 valid 条件剔除，此处无需再过滤；
--   ② 年份：dwd.sessions.started 已完成 0014/0015 → 2014/2015 修正，无需再映射；
--   ③ 粒度：按天聚合；行数应等于 dwd.sessions 总数（每一单都归属唯一日期）。
-- =====================================================================

CREATE DATABASE IF NOT EXISTS dws;

DROP TABLE IF EXISTS dws.daily_series;
CREATE TABLE dws.daily_series (
  stat_date       DATE    COMMENT '统计日期(to_date(started))',
  sessions        BIGINT  COMMENT '当日订单数',
  total_kwh       DOUBLE  COMMENT '当日总充电量(度)，负荷预测目标',
  total_fee       DOUBLE  COMMENT '当日总费用(元)',
  active_stations BIGINT  COMMENT '当日有订单的站点数'
)
COMMENT 'ML 日粒度负荷序列（按天，由 dwd.sessions 聚合）'
STORED AS orc;

INSERT OVERWRITE TABLE dws.daily_series
SELECT
    to_date(started)                       AS stat_date,
    COUNT(*)                               AS sessions,
    SUM(energy)                            AS total_kwh,
    SUM(fees)                              AS total_fee,
    COUNT(DISTINCT station)                AS active_stations
FROM dwd.sessions
GROUP BY to_date(started);

-- ------------------------- 数据验证（务必确认行数与口径一致） -------------------------
SELECT 'daily rows'   AS metric, CAST(COUNT(*) AS STRING)  AS value FROM dws.daily_series
UNION ALL SELECT 'min date',       CAST(MIN(stat_date) AS STRING)   FROM dws.daily_series
UNION ALL SELECT 'max date',       CAST(MAX(stat_date) AS STRING)   FROM dws.daily_series
UNION ALL SELECT 'sessions_total', CAST(SUM(sessions) AS STRING)    FROM dws.daily_series
UNION ALL SELECT 'kwh_total',      CAST(ROUND(SUM(total_kwh),1) AS STRING) FROM dws.daily_series;