"""Independently reconcile a real pipeline export against the supplied CSV fixture.

Set OUTPUT_PATH and RAW_DIR to validate other completed runs of this fixture.
These integration checks intentionally use Python's CSV/date/decimal libraries,
not Spark expressions, so they can catch aggregation and date-conversion errors.
"""
import csv
import json
import os
import unittest
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path


class WarehouseTest(unittest.TestCase):
    """Check source totals and two independent cross-tabulations."""

    @classmethod
    def setUpClass(cls):
        """Read source data and the ADS output, skipping before the first run."""
        output = Path(os.getenv('OUTPUT_PATH', '/workspace/data/processed/dashboard.json'))
        if not output.exists():
            raise unittest.SkipTest('Run the Spark pipeline before integration checks')
        cls.payload = json.loads(output.read_text(encoding='utf-8'))
        raw = Path(os.getenv('RAW_DIR', '/workspace/data/raw'))
        with (raw / 'nvv2t.csv').open(encoding='utf-8-sig') as source:
            cls.source = list(csv.DictReader(source))

    def test_source_totals(self):
        """All supplied orders and their additive measures survive every group."""
        overview = self.payload['overview']
        self.assertEqual(overview['sessions'], len(self.source))
        for field, source_field in [('energy', 'kwhTotal'), ('fees', 'charging_fees')]:
            expected = float(sum(Decimal(row[source_field]) for row in self.source))
            self.assertAlmostEqual(overview[field], expected, places=6)
            for rows in self.payload['dimensions'].values():
                self.assertAlmostEqual(sum(row[field] for row in rows), expected, places=6)
                self.assertEqual(sum(row['sessions'] for row in rows), len(self.source))

    def test_cross_comparisons(self):
        """Recompute platform/facility and corrected weekday/hour from source."""
        expected_platform = defaultdict(int)
        expected_time = defaultdict(int)
        for row in self.source:
            expected_platform[(row['platform'], row['facilityType'])] += 1
            started = datetime.strptime('20' + row['created'][2:], '%Y-%m-%d %H:%M:%S')
            expected_time[(started.isoweekday(), started.hour)] += 1
        actual_platform = {(row['platform'], row['facility']): row['sessions']
                           for row in self.payload['dimensions']['platform_facility']}
        actual_time = {(row['weekday'], row['hour']): row['sessions']
                      for row in self.payload['dimensions']['weekday_hour']}
        self.assertEqual(actual_platform, dict(expected_platform))
        self.assertEqual(actual_time, dict(expected_time))

    def test_interval_order(self):
        """Distribution bins retain increasing numerical boundary order."""
        for name, field, order in [
            ('duration', 'duration_band', ['<1h', '1–3h', '3–6h', '≥6h']),
            ('energy', 'energy_band', ['<5kWh', '5–10kWh', '10–20kWh', '≥20kWh']),
        ]:
            actual = [row[field] for row in self.payload['dimensions'][name]]
            self.assertEqual(actual, [label for label in order if label in actual])
