#!/bin/sh
# One writer owns the embedded Hive metastore. Keep its files on the persistent volume.
set -eu
mkdir -p /hadoop-data/metastore
cd /hadoop-data/metastore
spark-submit --master 'local[2]' --driver-memory 2g /workspace/spark/pipeline.py
python /workspace/backend/publish.py
