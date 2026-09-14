import os

import mysql.connector
from flask import Flask, jsonify

app = Flask(__name__)


def database_connection():
    return mysql.connector.connect(
        host=os.getenv("MYSQL_HOST", "mysql"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        database=os.getenv("MYSQL_DATABASE", "bigdata"),
        user=os.getenv("MYSQL_USER", "course"),
        password=os.getenv("MYSQL_PASSWORD", "course_dev_only"),
    )


@app.get("/api/health")
def health():
    with database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT VERSION()")
            mysql_version = cursor.fetchone()[0]

    return jsonify(
        status="ok",
        python="3.12",
        hadoop="3.5.0",
        pyspark="4.2.0",
        mysql=mysql_version,
    )
