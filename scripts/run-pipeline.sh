#!/bin/sh
# One writer owns the embedded Hive metastore. Keep its files on the persistent
# volume. Stages run sequentially because the embedded metastore cannot be
# opened by simultaneous Spark writers; each layer can be rerun on its own.
set -eu
mkdir -p /hadoop-data/metastore
cd /hadoop-data/metastore
for stage in ods dwd dws ads; do
  spark-submit --master 'local[2]' --driver-memory 2g /workspace/spark/$stage.py
done
python /workspace/backend/publish.py
