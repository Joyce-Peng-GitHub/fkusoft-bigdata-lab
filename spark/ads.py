"""ADS stage: assemble the dashboard contract and publish the JSON artifact.

Reads the ``ads.<dimension>`` tables, orders interval dimensions by their
numeric boundaries, adds overview and battery aggregates plus quality
metadata, and writes both the ``ads.dashboard`` Hive table and the local
``dashboard.json`` consumed by the publication step.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pyspark.sql import functions as F

from common import DIMENSIONS, INTERVAL_ORDERS, output_path, spark_session


def main():
    """Collect ADS tables into the bounded dashboard JSON contract.

    Quality metadata is recomputed from ODS/DWD tables so this stage is
    independently runnable after any earlier stage rerun, without needing the
    counts captured during ODS.

    Raises:
        RuntimeError: A dimension no longer reconciles with the DWD total.
    """
    spark = spark_session('charging-ads')
    df = spark.table('dwd.sessions')
    total = df.count()

    dimensions = {}
    for name, keys in DIMENSIONS.items():
        rows = [r.asDict() for r in spark.table('ads.' + name).orderBy(*keys).collect()]
        if name in INTERVAL_ORDERS:
            rows.sort(key=lambda row: INTERVAL_ORDERS[name].index(row[keys[0]]))
        # Re-check the invariant at the export boundary; DWS already asserted it.
        if sum(r['sessions'] for r in rows) != total:
            raise RuntimeError('Dimension reconciliation failed: ' + name)
        dimensions[name] = rows

    overview = df.agg(F.count('*').alias('sessions'), F.sum('energy').alias('energy'),
        F.sum('fees').alias('fees'), F.countDistinct('station').alias('stations'),
        F.avg('duration').alias('avg_duration')).first().asDict()
    battery_rows = [r.asDict() for r in spark.table('dwd.battery').groupBy(
        (F.floor(F.col('soc')/10)*10).alias('soc_band')).agg(F.count('*').alias('samples'),
        F.avg('temperature').alias('temperature'), F.avg('voltage_spread').alias('voltage_spread'))
        .orderBy('soc_band').collect()]
    source_rows = {n: spark.table('ods.' + n).count() for n in ('sessions', 'battery', 'stations')}
    rejected = spark.table('dwd.rejected_sessions').count()
    battery_accepted = spark.table('dwd.battery').count()
    payload = {'generated_at': datetime.now(timezone.utc).isoformat(), 'overview': overview,
        'dimensions': dimensions, 'battery': battery_rows,
        'quality': {'source_rows': source_rows, 'accepted_sessions': total,
            'rejected_sessions': rejected,
            'duplicates_removed': source_rows['sessions'] - total - rejected,
            'battery_accepted': battery_accepted,
            'year_policy': '0014/0015 interpreted as 2014/2015; station metadata is a later snapshot',
            'telemetry_time': 'Unavailable: source scientific notation lost precision'}}
    # ADS stores the exact API contract, making MySQL publication reproducible.
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    spark.createDataFrame([(encoded,)], ['payload']).write.mode('overwrite').saveAsTable('ads.dashboard')
    output = output_path()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(spark.table('ads.dashboard').first()['payload'], encoding='utf-8')
    spark.stop()
    print(json.dumps({'stage': 'ads', 'overview': overview, 'quality': payload['quality']},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
