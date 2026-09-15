"""Atomically publish a successful Hive ADS snapshot to MySQL.

A single-row InnoDB transaction prevents readers from seeing mixed job versions.
Failed Spark jobs never invoke this module; failed commits retain the old snapshot.
"""
import json
import os
from pathlib import Path

from db import database_connection


def publish():
    """Validate the ADS export and replace the served snapshot in one transaction.

    Raises:
        ValueError: Snapshot counts or schema are inconsistent.
        mysql.connector.Error: Publication fails; the previous snapshot remains.
    """
    payload = json.loads(Path(os.getenv('OUTPUT_PATH', '/workspace/data/processed/dashboard.json')).read_text(encoding='utf-8'))
    total = payload['overview']['sessions']
    if total <= 0 or len(payload['dimensions']) < 12:
        raise ValueError('Incomplete ADS snapshot')
    for rows in payload['dimensions'].values():
        if sum(row['sessions'] for row in rows) != total:
            raise ValueError('ADS reconciliation failed')
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    with database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute('''CREATE TABLE IF NOT EXISTS dashboard_snapshot (
                id TINYINT PRIMARY KEY, payload JSON NOT NULL,
                published_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP) ENGINE=InnoDB''')
            cursor.execute('''INSERT INTO dashboard_snapshot (id,payload) VALUES (1,%s)
                ON DUPLICATE KEY UPDATE payload=%s''', (encoded, encoded))
        connection.commit()
    print(f'Published {total} sessions to MySQL')


if __name__ == '__main__':
    publish()
