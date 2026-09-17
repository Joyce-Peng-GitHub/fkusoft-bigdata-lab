"""ODS stage: land source CSVs in HDFS and materialize all-string Hive tables.

Run standalone with ``spark-submit`` after HDFS is available. ODS preserves
source strings for auditability; ``FAILFAST`` rejects structural CSV
corruption, while value-level problems are classified later in DWD.
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import SOURCES, hdfs_root, raw_dir, spark_session


def main():
    """Upload source CSVs to HDFS and write the ``ods.*`` tables.

    Raises:
        subprocess.CalledProcessError: An HDFS upload fails.
    """
    raw = raw_dir()
    root = hdfs_root()
    # Uploading before Spark starts gives every executor one stable HDFS source
    # rather than relying on container-local paths that workers may not share.
    subprocess.run(['hdfs', 'dfs', '-mkdir', '-p', root + '/raw'], check=True)
    for filename in SOURCES.values():
        subprocess.run(['hdfs', 'dfs', '-put', '-f', str(raw / filename), root + '/raw/'], check=True)

    spark = spark_session('charging-ods')
    counts = {}
    for name, filename in SOURCES.items():
        df = spark.read.option('header', True).option('mode', 'FAILFAST').csv(root + '/raw/' + filename)
        # Some fixture exports include a UTF-8 BOM on the first header. Removing
        # it here keeps downstream SQL independent of the producer's encoding.
        df = df.toDF(*[c.lstrip('\ufeff') for c in df.columns])
        counts[name] = df.count()
        df.write.mode('overwrite').saveAsTable('ods.' + name)
    spark.stop()
    print(json.dumps({'stage': 'ods', 'source_rows': counts}, ensure_ascii=False))


if __name__ == '__main__':
    main()
