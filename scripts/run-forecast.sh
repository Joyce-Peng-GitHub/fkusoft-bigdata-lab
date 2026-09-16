#!/bin/sh
# Use the same persistent Hive catalog as run-pipeline.sh. Run sequentially:
# the embedded metastore cannot be opened by simultaneous Spark writers.
set -eu
cd /hadoop-data/metastore
spark-submit --master 'local[2]' --driver-memory 2g /workspace/ml/train.py
spark-submit --master 'local[2]' --driver-memory 2g /workspace/ml/predict.py "${1:-7}"
