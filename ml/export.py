"""Publish the web forecast snapshot through the shared MySQL store.

The analytics dashboard and the ML forecast both expose a single-row JSON
snapshot. Reusing the same MySQL database and connection settings keeps one
publication pattern: a single-row InnoDB transaction replaces the payload
atomically, so API readers never observe a half-written forecast and any
failure before commit leaves the previously published snapshot readable.

The backend database helper lives next to the Flask app, so this module adds
that directory to ``sys.path`` before importing it. ``predict.py`` runs as a
standalone script from ``ml/`` and has no other way to reach ``backend/db.py``.
"""
import json
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[1] / 'backend'
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from db import database_connection


def publish_forecast(payload):
    """Validate the forecast contract and replace the served snapshot atomically.

    Args:
        payload: Complete API payload with ``generated_at``, ``history`` and
            ``forecast``. It is stored verbatim so the REST contract stays
            reproducible from the database alone.

    Raises:
        ValueError: The payload is not a complete forecast or contains a
            non-finite number that JSON cannot represent safely.
        mysql.connector.Error: The publication transaction fails; the
            previously published snapshot remains readable.
    """
    if not isinstance(payload, dict) or not payload.get('history') or not payload.get('forecast'):
        raise ValueError('Incomplete forecast snapshot')
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    with database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute('''CREATE TABLE IF NOT EXISTS forecast_snapshot (
                id TINYINT PRIMARY KEY, payload JSON NOT NULL,
                published_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP) ENGINE=InnoDB''')
            cursor.execute('''INSERT INTO forecast_snapshot (id,payload) VALUES (1,%s)
                ON DUPLICATE KEY UPDATE payload=%s''', (encoded, encoded))
        connection.commit()
    print(f'Published forecast with {len(payload["forecast"])} predicted days to MySQL')