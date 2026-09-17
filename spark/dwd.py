"""DWD stage: type, validate and de-duplicate sessions and battery telemetry.

Reads ``ods.*`` and writes ``dwd.sessions``, ``dwd.stations``, ``dwd.battery``
and the ``dwd.rejected_sessions`` audit table. Telemetry timestamps are
intentionally not reconstructed: scientific notation in the source has
irreversibly lost precision. Session timestamps use the documented
``0014/0015`` to ``2014/2015`` correction instead.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import spark_session

# Bounds reject impossible values and infinities without imposing business
# thresholds on otherwise plausible sessions. ``coalesce`` is necessary below
# because applying NOT to an unknown predicate still yields NULL, not TRUE.
VALID = ("session_id IS NOT NULL AND energy >= 0 AND energy < 1e9 "
         "AND fees >= 0 AND fees < 1e9 AND duration > 0 AND duration < 1e6 "
         "AND started IS NOT NULL AND finished >= started AND stationId IS NOT NULL")


def main():
    """Materialize the DWD layer from ODS with auditable rejection.

    Raises:
        RuntimeError: Conflicting session or station IDs prevent safe dedup.
    """
    spark = spark_session('charging-dwd')
    # Explicit try_cast keeps malformed numeric values auditable under ANSI
    # SQL: conversion failures become NULL and are retained in rejected.
    spark.sql("""CREATE OR REPLACE TEMP VIEW typed AS SELECT *,
      try_cast(sessionId AS BIGINT) AS session_id,
      try_cast(kwhTotal AS DOUBLE) AS energy,
      try_cast(charging_fees AS DOUBLE) AS fees,
      try_cast(chargeTimeHrs AS DOUBLE) AS duration,
      try_to_timestamp(regexp_replace(created, '^00(14|15)-', '20$1-'), 'yyyy-MM-dd HH:mm:ss') AS started,
      try_to_timestamp(regexp_replace(ended, '^00(14|15)-', '20$1-'), 'yyyy-MM-dd HH:mm:ss') AS finished
      FROM ods.sessions""")
    spark.sql(f'SELECT * FROM typed WHERE NOT coalesce(({VALID}), false)') \
        .write.mode('overwrite').saveAsTable('dwd.rejected_sessions')
    # Exact duplicate source rows are harmless retries. Reusing a session ID
    # for different data is ambiguous, so fail instead of choosing an arbitrary
    # row.
    clean = spark.sql(f'SELECT * FROM typed WHERE {VALID}').dropDuplicates()
    if clean.groupBy('session_id').count().filter('count > 1').count():
        raise RuntimeError('Conflicting session IDs; refusing arbitrary deduplication')
    clean.createOrReplaceTempView('clean')
    # Station metadata must be one-to-one before the join; otherwise a single
    # charging session would fan out and inflate every downstream aggregate.
    stations = spark.table('ods.stations').dropDuplicates()
    if stations.groupBy('stationId').count().filter('count > 1').count():
        raise RuntimeError('Conflicting station IDs')
    stations.write.mode('overwrite').saveAsTable('dwd.stations')
    # Spark dayofweek uses Sunday=1. The pmod expression converts it to
    # ISO-style Monday=1 through Sunday=7, matching the dashboard and tests.
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
      FROM clean c LEFT JOIN dwd.stations s ON c.stationId=s.stationId""") \
        .write.mode('overwrite').saveAsTable('dwd.sessions')
    # Battery telemetry has no trustworthy event time, so it is validated as an
    # independent sample population and never joined onto individual sessions.
    battery = spark.sql("""SELECT try_cast(esd AS BIGINT) session_id,
      try_cast(soc AS DOUBLE) soc,
      try_cast(`max_temperature (℃)` AS DOUBLE) temperature,
      try_cast(`max_cell_voltage (V)` AS DOUBLE)-try_cast(`min_cell_voltage (V)` AS DOUBLE) voltage_spread
      FROM ods.battery""")
    battery.filter('session_id IS NOT NULL AND soc BETWEEN 0 AND 100 '
                   'AND temperature BETWEEN -50 AND 100 AND voltage_spread BETWEEN 0 AND 5') \
        .write.mode('overwrite').saveAsTable('dwd.battery')
    spark.stop()
    print('{"stage": "dwd"}')


if __name__ == '__main__':
    main()
