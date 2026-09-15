"""Verify API contracts and safe failures independently of database availability."""
import unittest
from unittest.mock import patch

import mysql.connector
from app import app


class ApiTest(unittest.TestCase):
    """Exercise public routes through Flask's request dispatcher."""

    def test_snapshot_and_dimension(self):
        """Dashboard and dimension routes return the published contract."""
        data = {'generated_at': '2026-01-01', 'dimensions': {'month': [{'sessions': 2}]}}
        with patch('app.snapshot', return_value=data):
            client = app.test_client()
            self.assertEqual(client.get('/api/dashboard').json, data)
            self.assertEqual(client.get('/api/analysis/month').json['rows'], [{'sessions': 2}])
            self.assertEqual(client.get('/api/analysis/unknown').status_code, 404)
            self.assertEqual(client.get('/api/health').status_code, 200)

    def test_unavailable(self):
        """Empty storage and connector failures produce retryable responses."""
        for value in [None, mysql.connector.Error('secret details')]:
            with patch('app.snapshot', **({'side_effect': value} if value else {'return_value': None})):
                for path in ['/api/health', '/api/dashboard', '/api/analysis/month']:
                    response = app.test_client().get(path)
                    self.assertEqual(response.status_code, 503)
                    self.assertNotIn('secret', response.get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
