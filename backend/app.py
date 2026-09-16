"""Serve the published MySQL analytics and ML forecast snapshots."""
import json

import mysql.connector
from flask import Flask, jsonify

from db import database_connection

app = Flask(__name__)


def _read_json_snapshot(query):
    """Read one JSON payload using a fixed internal snapshot query.

    Args:
        query: Constant SQL statement owned by this module. Request data must
            never be interpolated into it.

    Returns:
        dict | None: Decoded snapshot payload, or None when no row exists.

    Raises:
        mysql.connector.Error: MySQL query or connection failed.
    """
    with database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query)
            row = cursor.fetchone()
    return json.loads(row[0]) if row else None


def snapshot():
    """Read one consistent warehouse snapshot.

    Returns:
        dict | None: Published ADS payload, or None before the first publication.

    Raises:
        mysql.connector.Error: MySQL query or connection failed.
    """
    return _read_json_snapshot(
        'SELECT payload FROM dashboard_snapshot WHERE id=1')


def forecast_snapshot():
    """Read the latest complete ML forecast snapshot.

    Returns:
        dict | None: Published forecast payload, or None before the first run.

    Raises:
        mysql.connector.Error: MySQL query or connection failed.
    """
    return _read_json_snapshot(
        'SELECT payload FROM forecast_snapshot WHERE id=1')


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
    """Serve the last complete MySQL forecast snapshot.

    Returns:
        tuple | Response: Actual history and future estimates, or a retryable 503
        before prediction has run.
    """
    data = forecast_snapshot()
    if data is None:
        return jsonify(error='预测结果尚未就绪，请先运行预测任务'), 503
    response = jsonify(data)
    response.headers['Cache-Control'] = 'no-store'
    return response
