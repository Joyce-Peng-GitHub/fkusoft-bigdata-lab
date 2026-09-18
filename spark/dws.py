"""DWS stage: build the daily series and one aggregate table per dimension.

Reads ``dwd.sessions`` and writes ``dws.daily_series`` plus a
``dws.<dimension>`` and an ``ads.<dimension>`` copy for each entry in
``DIMENSIONS``. Each aggregate is reconciled against the DWD session total so
accidental row loss or join fan-out surfaces here, before the dashboard
contract is published.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pyspark.sql import functions as F

from common import DIMENSIONS, spark_session


def main():
    """Materialize DWS aggregates and their ADS copies from DWD sessions.

    Raises:
        RuntimeError: A dimension's session total diverges from DWD.
    """
    spark = spark_session('charging-dws')
    # Daily-grain load series feeds the ml forecast module. ``started`` carries
    # the corrected 2014/2015 calendar date, so one pass over dwd.sessions is
    # enough; the row count must equal the DWD session total to stay reconciled.
    spark.sql("""SELECT to_date(started) AS stat_date,
      COUNT(*) AS sessions, SUM(energy) AS total_kwh, SUM(fees) AS total_fee,
      COUNT(DISTINCT station) AS active_stations
      FROM dwd.sessions GROUP BY to_date(started)""") \
        .write.mode('overwrite').saveAsTable('dws.daily_series')

    df = spark.table('dwd.sessions')
    total = df.count()
    for name, keys in DIMENSIONS.items():
        # DWS is the reusable aggregate layer. ADS copies the exact tables used
        # to form the external snapshot so publication can be reproduced.
        agg = df.groupBy(*keys).agg(
            F.count('*').alias('sessions'), F.sum('energy').alias('energy'),
            F.sum('fees').alias('fees'), F.avg('duration').alias('avg_duration'),
            (F.sum('energy') / F.sum('duration')).alias('avg_power'))
        agg.write.mode('overwrite').saveAsTable('dws.' + name)
        spark.table('dws.' + name).write.mode('overwrite').saveAsTable('ads.' + name)
        # Every session belongs to exactly one bucket in every dimension. This
        # invariant catches accidental row loss or join fan-out before export.
        agg_total = spark.table('dws.' + name).agg(F.sum('sessions').alias('s')).first()['s']
        if agg_total != total:
            raise RuntimeError('Dimension reconciliation failed: ' + name)
    spark.stop()
    print(json.dumps({'stage': 'dws', 'dimensions': len(DIMENSIONS), 'sessions': total},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
