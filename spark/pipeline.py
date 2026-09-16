"""Load charging CSVs through HDFS and persistent Hive ODS/DWD/DWS/ADS tables.

Run with spark-submit. Telemetry timestamps are intentionally not reconstructed:
scientific notation in the supplied source has irreversibly lost precision.
"""
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from pyspark.sql import SparkSession, functions as F

SOURCES = {'sessions': 'nvv2t.csv', 'battery': 'dsv13r2.csv', 'stations': 'nvv2t_md_end.csv'}
DIMENSIONS = {
    'month': ['month'], 'hour': ['hour'], 'weekday': ['weekday'],
    'platform': ['platform'], 'facility': ['facility'], 'station': ['station'],
    'location': ['location'], 'duration': ['duration_band'],
    'energy': ['energy_band'], 'vehicle': ['vehicle'],
    'platform_facility': ['platform', 'facility'],
    'weekday_hour': ['weekday', 'hour'],
}


def main():
    """Materialize all warehouse layers and export a bounded dashboard snapshot.

    Raises:
        RuntimeError: Input keys conflict or reconciliation fails.
        subprocess.CalledProcessError: HDFS upload fails.
    """
    raw = Path(os.getenv('RAW_DIR', '/workspace/data/raw'))
    root = os.getenv('HDFS_ROOT', 'hdfs://backend:9000/charging')
    subprocess.run(['hdfs', 'dfs', '-mkdir', '-p', root + '/raw'], check=True)
    for filename in SOURCES.values():
        subprocess.run(['hdfs', 'dfs', '-put', '-f', str(raw / filename), root + '/raw/'], check=True)
    spark = (SparkSession.builder.appName('charging-warehouse')
             .config('spark.sql.warehouse.dir', root + '/warehouse')
             .config('spark.sql.session.timeZone', 'UTC')
             .config('spark.sql.shuffle.partitions', '4')
             .enableHiveSupport().getOrCreate())
    spark.sparkContext.setLogLevel('WARN')
    for layer in ['ods', 'dwd', 'dws', 'ads']:
        spark.sql(f'CREATE DATABASE IF NOT EXISTS {layer}')
    counts = {}
    for name, filename in SOURCES.items():
        df = spark.read.option('header', True).option('mode', 'FAILFAST').csv(root + '/raw/' + filename)
        df = df.toDF(*[c.lstrip('\ufeff') for c in df.columns])
        counts[name] = df.count()
        df.write.mode('overwrite').saveAsTable('ods.' + name)
    # Explicit try_cast keeps malformed numeric values auditable under ANSI SQL.
    spark.sql("""CREATE OR REPLACE TEMP VIEW typed AS SELECT *,
      try_cast(sessionId AS BIGINT) AS session_id,
      try_cast(kwhTotal AS DOUBLE) AS energy,
      try_cast(charging_fees AS DOUBLE) AS fees,
      try_cast(chargeTimeHrs AS DOUBLE) AS duration,
      try_to_timestamp(regexp_replace(created, '^00(14|15)-', '20$1-'), 'yyyy-MM-dd HH:mm:ss') AS started,
      try_to_timestamp(regexp_replace(ended, '^00(14|15)-', '20$1-'), 'yyyy-MM-dd HH:mm:ss') AS finished
      FROM ods.sessions""")
    valid = "session_id IS NOT NULL AND energy >= 0 AND energy < 1e9 AND fees >= 0 AND fees < 1e9 AND duration > 0 AND duration < 1e6 AND started IS NOT NULL AND finished >= started AND stationId IS NOT NULL"
    spark.sql(f'SELECT * FROM typed WHERE NOT coalesce(({valid}), false)').write.mode('overwrite').saveAsTable('dwd.rejected_sessions')
    clean = spark.sql(f'SELECT * FROM typed WHERE {valid}').dropDuplicates()
    if clean.groupBy('session_id').count().filter('count > 1').count():
        raise RuntimeError('Conflicting session IDs; refusing arbitrary deduplication')
    clean.createOrReplaceTempView('clean')
    stations = spark.table('ods.stations').dropDuplicates()
    if stations.groupBy('stationId').count().filter('count > 1').count():
        raise RuntimeError('Conflicting station IDs')
    stations.write.mode('overwrite').saveAsTable('dwd.stations')
    spark.sql("""SELECT c.session_id, c.energy, c.fees, c.duration, c.started,
      date_format(c.started, 'yyyy-MM') month, hour(c.started) hour,
      pmod(dayofweek(c.started)+5,7)+1 weekday,
      coalesce(nullif(trim(c.platform),''),'unknown') platform,
      coalesce(c.facilityType,'unknown') facility,
      c.stationId station, coalesce(c.locationId,'unknown') location,
      coalesce(c.managerVehicle,'unknown') vehicle,
      CASE WHEN c.duration < 1 THEN '<1h' WHEN c.duration < 3 THEN '1–3h'
           WHEN c.duration < 6 THEN '3–6h' ELSE '≥6h' END duration_band,
      CASE WHEN c.energy < 5 THEN '<5kWh' WHEN c.energy < 10 THEN '5–10kWh'
           WHEN c.energy < 20 THEN '10–20kWh' ELSE '≥20kWh' END energy_band,
      coalesce(s.station_name, concat('站点 ',c.stationId)) station_name
      FROM clean c LEFT JOIN dwd.stations s ON c.stationId=s.stationId""").write.mode('overwrite').saveAsTable('dwd.sessions')
    battery = spark.sql("""SELECT try_cast(esd AS BIGINT) session_id,
      try_cast(soc AS DOUBLE) soc,
      try_cast(`max_temperature (℃)` AS DOUBLE) temperature,
      try_cast(`max_cell_voltage (V)` AS DOUBLE)-try_cast(`min_cell_voltage (V)` AS DOUBLE) voltage_spread
      FROM ods.battery""")
    battery.filter('session_id IS NOT NULL AND soc BETWEEN 0 AND 100 AND temperature BETWEEN -50 AND 100 AND voltage_spread BETWEEN 0 AND 5').write.mode('overwrite').saveAsTable('dwd.battery')
    # Daily-grain load series feeds the ml forecast module. `started` already carries the
    # corrected 2014/2015 calendar date, so one pass over dwd.sessions is enough; the row
    # count must equal the DWD session total to stay reconciled with the dashboard.
    spark.sql("""SELECT to_date(started) AS stat_date,
      COUNT(*) AS sessions, SUM(energy) AS total_kwh, SUM(fees) AS total_fee,
      COUNT(DISTINCT station) AS active_stations
      FROM dwd.sessions GROUP BY to_date(started)""").write.mode('overwrite').saveAsTable('dws.daily_series')
    df = spark.table('dwd.sessions')
    total = df.count()
    dimensions = {}
    for name, keys in DIMENSIONS.items():
        agg = df.groupBy(*keys).agg(F.count('*').alias('sessions'), F.sum('energy').alias('energy'),
             F.sum('fees').alias('fees'), F.avg('duration').alias('avg_duration'),
             (F.sum('energy') / F.sum('duration')).alias('avg_power'))
        agg.write.mode('overwrite').saveAsTable('dws.' + name)
        spark.table('dws.' + name).write.mode('overwrite').saveAsTable('ads.' + name)
        rows = [r.asDict() for r in spark.table('ads.' + name).orderBy(*keys).collect()]
        # Interval labels are presentation strings; lexical order is not numeric order.
        interval_orders = {
            'duration': ['<1h', '1–3h', '3–6h', '≥6h'],
            'energy': ['<5kWh', '5–10kWh', '10–20kWh', '≥20kWh'],
        }
        if name in interval_orders:
            rows.sort(key=lambda row: interval_orders[name].index(row[keys[0]]))
        if sum(r['sessions'] for r in rows) != total:
            raise RuntimeError('Dimension reconciliation failed: ' + name)
        dimensions[name] = rows
    overview = df.agg(F.count('*').alias('sessions'), F.sum('energy').alias('energy'),
        F.sum('fees').alias('fees'), F.countDistinct('station').alias('stations'),
        F.avg('duration').alias('avg_duration')).first().asDict()
    battery_rows = [r.asDict() for r in spark.table('dwd.battery').groupBy(
        (F.floor(F.col('soc')/10)*10).alias('soc_band')).agg(F.count('*').alias('samples'),
        F.avg('temperature').alias('temperature'), F.avg('voltage_spread').alias('voltage_spread')).orderBy('soc_band').collect()]
    payload = {'generated_at': datetime.now(timezone.utc).isoformat(), 'overview': overview,
        'dimensions': dimensions, 'battery': battery_rows,
        'quality': {'source_rows': counts, 'accepted_sessions': total,
            'rejected_sessions': spark.table('dwd.rejected_sessions').count(),
            'duplicates_removed': counts['sessions'] - total - spark.table('dwd.rejected_sessions').count(),
            'battery_accepted': spark.table('dwd.battery').count(),
            'year_policy': '0014/0015 interpreted as 2014/2015; station metadata is a later snapshot',
            'telemetry_time': 'Unavailable: source scientific notation lost precision'}}
    # ADS stores the exact API contract, making MySQL publication reproducible.
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    spark.createDataFrame([(encoded,)], ['payload']).write.mode('overwrite').saveAsTable('ads.dashboard')
    output = Path(os.getenv('OUTPUT_PATH', '/workspace/data/processed/dashboard.json'))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(spark.table('ads.dashboard').first()['payload'], encoding='utf-8')
    print(json.dumps({'overview': overview, 'quality': payload['quality']}, ensure_ascii=False))
    spark.stop()


if __name__ == '__main__':
    main()
