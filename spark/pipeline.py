"""Charging-data warehouse: run every stage in one process.

The warehouse is split into ``ods``/``dwd``/``dws``/``ads`` stage modules (see
those files). This orchestrator runs them in order for callers that want one
command. The preferred, layer-by-layer entry point is
``scripts/run-pipeline.sh``, which ``spark-submit``s each stage separately so
each layer can be rerun or inspected on its own.

Telemetry timestamps are intentionally not reconstructed: scientific notation
in the supplied source has irreversibly lost precision. Session timestamps use
the documented source-specific ``0014/0015`` to ``2014/2015`` correction
instead.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ads import main as ads
from dwd import main as dwd
from dws import main as dws
from ods import main as ods


def main():
    """Run ODS, DWD, DWS and ADS in sequence within one Spark driver.

    Each stage creates and stops its own SparkSession, so the embedded Hive
    metastore is released between layers.
    """
    ods()
    dwd()
    dws()
    ads()


if __name__ == '__main__':
    main()
