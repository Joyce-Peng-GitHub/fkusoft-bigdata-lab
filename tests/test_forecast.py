"""Verify MySQL forecast publication and the independent HTTP contract."""
import json
import unittest
from unittest.mock import MagicMock, patch

import mysql.connector

from app import app
from export import publish_forecast


class _RecordingCursor:
    """Minimal DB-API cursor that records every statement and its parameters."""

    def __init__(self, connection):
        self._connection = connection

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def execute(self, statement, params=None):
        self._connection.executed.append((statement, params))
        if statement.lstrip().startswith('INSERT INTO forecast_snapshot'):
            self._connection.row = (params[0],)

    def fetchone(self):
        return self._connection.row


class _RecordingConnection:
    """Minimal connection context manager recording commits and statements."""

    def __init__(self, row=None):
        self.executed = []
        self.committed = False
        self.row = row

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def cursor(self):
        return _RecordingCursor(self)

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

    def test_publish_to_mysql_and_serve_same_payload(self):
        """Commit the exact API payload and read it through the HTTP endpoint."""
        connection = _RecordingConnection()
        with patch('export.database_connection', return_value=connection), \
                patch('app.database_connection', return_value=connection):
            publish_forecast(self.payload)
            response = app.test_client().get('/api/ml/forecast')
        self.assertTrue(connection.committed)
        self.assertIn('CREATE TABLE IF NOT EXISTS forecast_snapshot', connection.executed[0][0])
        self.assertEqual(json.loads(connection.executed[1][1][0]), self.payload)
        self.assertEqual(connection.executed[1][1][0], connection.executed[1][1][1])
        self.assertIn('SELECT payload FROM forecast_snapshot', connection.executed[2][0])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, self.payload)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')

    def test_reject_incomplete_and_non_finite(self):
        """Structural and JSON-safety failures happen before any database write."""
        connection = _RecordingConnection()
        with patch('export.database_connection', return_value=connection):
            for field in self.payload:
                with self.subTest(field=field), self.assertRaises(ValueError):
                    publish_forecast({
                        key: value for key, value in self.payload.items()
                        if key != field
                    })
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
        """Return 503 for an empty snapshot and hide database failures."""
        with patch('app.database_connection', return_value=_RecordingConnection()):
            self.assertEqual(app.test_client().get('/api/ml/forecast').status_code, 503)
        with patch('app.database_connection',
                   side_effect=mysql.connector.Error('secret details')):
            response = app.test_client().get('/api/ml/forecast')
            self.assertEqual(response.status_code, 503)
            self.assertNotIn('secret', response.get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
