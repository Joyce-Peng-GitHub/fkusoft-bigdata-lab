"""Shared configuration and helpers for the charging-data warehouse stages.

Each stage (ods/dwd/dws/ads) is a standalone ``spark-submit`` job that
materializes one warehouse layer. This module centralizes the source fixture
names, the analysis dimensions, the interval label ordering and the
SparkSession factory so every stage shares identical warehouse, time-zone and
shuffle settings.

Environment overrides (defaults match the containerized deployment):

``RAW_DIR``
    Local directory holding the source CSVs.
``HDFS_ROOT``
    HDFS namespace for raw uploads and the warehouse.
``OUTPUT_PATH``
    Local path for the ADS dashboard JSON artifact.
"""
import os
from pathlib import Path

from pyspark.sql import SparkSession

# Logical names become ODS table names; filenames are the immutable source
# fixture names expected below ``RAW_DIR``.
SOURCES = {
    'sessions': 'nvv2t.csv',
    'battery': 'dsv13r2.csv',
    'stations': 'nvv2t_md_end.csv',
}

# Each entry defines both an aggregate table and a dashboard API dimension.
# Multi-column entries preserve cross-dimensional relationships that cannot be
# recovered by combining independent one-dimensional totals. The station and
# location dimensions also carry their human-readable name column so the
# dashboard can label rows without a second lookup.
DIMENSIONS = {
    'month': ['month'], 'hour': ['hour'], 'weekday': ['weekday'],
    'platform': ['platform'], 'facility': ['facility'],
    'station': ['station', 'station_name'], 'location': ['location', 'location_name'],
    'duration': ['duration_band'],
    'energy': ['energy_band'], 'vehicle': ['vehicle'],
    'platform_facility': ['platform', 'facility'],
    'weekday_hour': ['weekday', 'hour'],
}

# Interval labels are presentation strings; lexical order is not numeric order.
# ADS sorts rows by these explicit boundaries before publishing the snapshot.
INTERVAL_ORDERS = {
    'duration': ['<1h', '1–3h', '3–6h', '≥6h'],
    'energy': ['<5kWh', '5–10kWh', '10–20kWh', '≥20kWh'],
}

# All four Hive layer databases, created up front so every stage is
# independently runnable regardless of which layer it writes.
LAYERS = ['ods', 'dwd', 'dws', 'ads']


def raw_dir():
    """Return the local directory holding the source CSVs."""
    return Path(os.getenv('RAW_DIR', '/workspace/data/raw'))


def hdfs_root():
    """Return the HDFS namespace for raw uploads and the warehouse."""
    return os.getenv('HDFS_ROOT', 'hdfs://backend:9000/charging')


def output_path():
    """Return the local path for the ADS dashboard JSON artifact."""
    return Path(os.getenv('OUTPUT_PATH', '/workspace/data/processed/dashboard.json'))


def spark_session(app_name):
    """Create a Hive-enabled SparkSession with shared warehouse settings.

    UTC makes calendar dimensions reproducible across hosts. Four shuffle
    partitions are sufficient for this bounded teaching dataset. All four layer
    databases are created here so each stage is independently runnable.

    Args:
        app_name: Spark UI label for the calling stage.

    Returns:
        SparkSession: Hive-enabled session with the warehouse under
        ``HDFS_ROOT/warehouse`` and ``WARN`` log level.
    """
    root = hdfs_root()
    spark = (SparkSession.builder.appName(app_name)
             .config('spark.sql.warehouse.dir', root + '/warehouse')
             .config('spark.sql.session.timeZone', 'UTC')
             .config('spark.sql.shuffle.partitions', '4')
             .enableHiveSupport().getOrCreate())
    spark.sparkContext.setLogLevel('WARN')
    for layer in LAYERS:
        spark.sql(f'CREATE DATABASE IF NOT EXISTS {layer}')
    return spark
