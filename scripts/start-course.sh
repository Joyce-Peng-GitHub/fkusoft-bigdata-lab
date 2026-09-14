#!/bin/sh
set -eu

mkdir -p /hadoop-data/namenode /hadoop-data/datanode

if [ ! -f /hadoop-data/namenode/current/VERSION ]; then
  hdfs namenode -format -force -nonInteractive
fi

hdfs --daemon start namenode
hdfs --daemon start datanode
yarn --daemon start resourcemanager
yarn --daemon start nodemanager

exec flask --app app run --host=0.0.0.0 --port=5000
