"""Verify MySQL forecast publication and the independent HTTP contract."""
import json
import unittest
from unittest.mock import MagicMock, patch

import mysql.connector

from app import app
from export import publish_forecast


class _RecordingCursor:
    """Minimal DB-API cursor that records every statement and its parameters."""

    def __init__(self, executed):
        self._executed = executed

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def execute(self, statement, params=None):
        self._executed.append((statement, params))


class _RecordingConnection:
    """Minimal connection context manager recording commits and statements."""

    def __init__(self):
        self.executed = []
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def cursor(self):
        return _RecordingCursor(self.executed)

    def commit(self):
        self.committed = True


class ForecastTest(unittest.TestCase):
    """Exercise the producer artifact through the Flask consumer."""

    def setUp(self):
        """Use one deterministic contract shared by producer and consumer checks."""
        self.payload = {
            'generated_at': '2026-09-16T00:00:00+00:00',
            'history_end': '2015-10-31',
            'history': [{'date': '2015-10-31', 'energy': 10, 'sessions': 2}],
            'forecast': [{'date': '2015-11-01', 'energy': 0, 'sessions': 1.2}],
        }

    def test_publish_to_mysql(self):
        """Create the snapshot table and commit the exact API payload once."""
        connection = _RecordingConnection()
        with patch('export.database_connection', return_value=connection):
            publish_forecast(self.payload)
        self.assertTrue(connection.committed)
        self.assertIn('CREATE TABLE IF NOT EXISTS forecast_snapshot', connection.executed[0][0])
        self.assertEqual(json.loads(connection.executed[1][1][0]), self.payload)

    def test_reject_incomplete_and_non_finite(self):
        """Structural and JSON-safety failures happen before any database write."""
        connection = _RecordingConnection()
        with patch('export.database_connection', return_value=connection):
            with self.assertRaises(ValueError):
                publish_forecast({'generated_at': '2026-09-16T00:00:00+00:00'})
            with self.assertRaises(ValueError):
                publish_forecast(dict(self.payload, forecast=[{'energy': float('nan')}]))
        self.assertEqual(connection.executed, [])

    def test_failed_commit_propagates(self):
        """A commit failure surfaces instead of silently reporting success."""
        connection = _RecordingConnection()
        connection.commit = MagicMock(side_effect=mysql.connector.Error('write failed'))
        with patch('export.database_connection', return_value=connection):
            with self.assertRaises(mysql.connector.Error):
                publish_forecast(self.payload)

    def test_serve_contract(self):
        """Serve stored values, keep the response uncached and hide failures."""
        with patch('app.forecast_snapshot', return_value=self.payload):
            response = app.test_client().get('/api/ml/forecast')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json, self.payload)
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
        with patch('app.forecast_snapshot', return_value=None):
            self.assertEqual(app.test_client().get('/api/ml/forecast').status_code, 503)
        with patch('app.forecast_snapshot', side_effect=mysql.connector.Error('secret details')):
            response = app.test_client().get('/api/ml/forecast')
            self.assertEqual(response.status_code, 503)
            self.assertNotIn('secret', response.get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()