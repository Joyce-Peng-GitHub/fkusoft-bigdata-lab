"""Verify atomic forecast publication and the independent HTTP contract."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app import app
from export import publish_forecast


class ForecastTest(unittest.TestCase):
    """Exercise the producer artifact through the Flask consumer."""

    def test_publish_and_serve(self):
        """Preserve dates, zero predictions and fractional auxiliary counts."""
        payload = {
            'generated_at': '2026-09-16T00:00:00+00:00',
            'history_end': '2015-10-31',
            'history': [{'date': '2015-10-31', 'energy': 10, 'sessions': 2}],
            'forecast': [{'date': '2015-11-01', 'energy': 0, 'sessions': 1.2}],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'forecast.json'
            with patch.dict(os.environ, FORECAST_PATH=str(path)):
                self.assertEqual(app.test_client().get('/api/ml/forecast').status_code, 503)
                publish_forecast(payload, path)
                response = app.test_client().get('/api/ml/forecast')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json, payload)
                self.assertEqual(response.headers['Cache-Control'], 'no-store')
                with self.assertRaises(ValueError):
                    publish_forecast({'energy': float('nan')}, path)
                self.assertEqual(json.loads(path.read_text()), payload)
                with patch('export.os.replace', side_effect=OSError('disk failure')):
                    with self.assertRaises(OSError):
                        publish_forecast({'energy': 1}, path)
                self.assertEqual(json.loads(path.read_text()), payload)
                self.assertEqual(list(Path(directory).iterdir()), [path])
                path.write_text('{partial')
                response = app.test_client().get('/api/ml/forecast')
                self.assertEqual(response.status_code, 503)
                self.assertNotIn(directory, response.get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
