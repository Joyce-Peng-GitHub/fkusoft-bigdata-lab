"""Serve the published MySQL analytics snapshot and atomic ML forecast artifact."""
import json
import os
from pathlib import Path

import mysql.connector
from flask import Flask, jsonify

from db import database_connection

app = Flask(__name__)


def snapshot():
    """Read one consistent warehouse snapshot.

    Returns:
        dict | None: Published ADS payload, or None before the first publication.

    Raises:
        mysql.connector.Error: MySQL query or connection failed.
    """
    with database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute('SELECT payload FROM dashboard_snapshot WHERE id=1')
            row = cursor.fetchone()
    return json.loads(row[0]) if row else None


@app.errorhandler(mysql.connector.Error)
def database_error(error):
    """Return a retryable status without leaking database credentials or SQL.

    Args:
        error: Connector exception recorded in the server log.

    Returns:
        tuple: JSON error response and HTTP 503.
    """
    app.logger.warning('Database unavailable: %s', type(error).__name__)
    return jsonify(error='数据尚未就绪或数据库暂不可用，请稍后重试'), 503


@app.get('/api/health')
def health():
    """Report readiness of the published data, not just process liveness."""
    data = snapshot()
    if data is None:
        return jsonify(status='not_ready'), 503
    return jsonify(status='ok', generated_at=data['generated_at'])


@app.get('/api/dashboard')
def dashboard():
    """Return all dashboard metrics from one MySQL snapshot."""
    data = snapshot()
    if data is None:
        return jsonify(error='尚未发布分析结果，请先运行数据流水线'), 503
    response = jsonify(data)
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.get('/api/analysis/<dimension>')
def analysis(dimension):
    """Return one allowlisted analysis dimension without interpolating SQL.

    Args:
        dimension: Dimension key present in the published ADS snapshot.

    Returns:
        tuple | Response: JSON analysis or a 404/503 error response.
    """
    data = snapshot()
    if data is None:
        return jsonify(error='尚未发布分析结果'), 503
    if dimension not in data['dimensions']:
        return jsonify(error='未知分析维度'), 404
    return jsonify(dimension=dimension, rows=data['dimensions'][dimension])


@app.get('/api/ml/forecast')
def forecast():
    """Serve the last complete forecast without requiring MySQL availability.

    Returns:
        Response | tuple: Actual history and future estimates, or a retryable 503
        before prediction has run or when its shared artifact cannot be read.
    """
    path = Path(os.getenv('FORECAST_PATH', str(
        Path(__file__).resolve().parents[1] / 'data/processed/forecast.json')))
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return jsonify(error='预测结果尚未就绪，请先运行预测任务'), 503
    response = jsonify(payload)
    response.headers['Cache-Control'] = 'no-store'
    return response
