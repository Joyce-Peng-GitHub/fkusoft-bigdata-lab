"""通过共用的 MySQL 存储发布 Web 预测快照。

分析大屏与 ML 预测都对外暴露"单行 JSON 快照"。复用同一个 MySQL 库和
同一套连接配置，保持统一的发布模式
"""

import json
import sys
from pathlib import Path

# 将 backend 目录加入模块搜索路径，以便复用 backend/db.py 的连接管理
_BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from db import database_connection


def publish_forecast(payload):
    """校验预测契约，并原子替换对外服务的快照。

    Args:
        payload: 完整的 API payload，包含 ``generated_at``、
            ``history_end``、``history`` 和 ``forecast`` 字段。原样存储，
            保证 REST 契约可以仅凭数据库内容完整复现。

    Raises:
        ValueError: payload 不是完整的预测快照，或含有 JSON 无法安全
            表示的非有限数（NaN/Inf）。
        mysql.connector.Error: 发布事务失败；此时上一次已发布的快照
            保持可读，不受影响。
    """
    if not isinstance(payload, dict):
        raise ValueError("Forecast snapshot must be a JSON object")
    # 四个顶层字段共同构成 REST 契约。history 与 forecast 还必须非空，
    # 避免一次不完整运行覆盖上次可用的预测快照。
    required_fields = ("generated_at", "history_end", "history", "forecast")
    missing_fields = [field for field in required_fields if not payload.get(field)]
    if missing_fields:
        raise ValueError(
            f'Incomplete forecast snapshot: missing {", ".join(missing_fields)}'
        )
    # allow_nan=False：NaN/Inf 会写出非法 JSON，提前在此失败而不是污染快照。
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    with database_connection() as connection:
        with connection.cursor() as cursor:
            # 固定 id=1 的单行表：INSERT ... ON DUPLICATE KEY UPDATE
            # 在单个事务内完成"替换"，读方要么读到旧快照、要么读到新快照
            cursor.execute("""CREATE TABLE IF NOT EXISTS forecast_snapshot (
                id TINYINT PRIMARY KEY, payload JSON NOT NULL,
                published_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP) ENGINE=InnoDB""")
            cursor.execute(
                """INSERT INTO forecast_snapshot (id,payload) VALUES (1,%s)
                ON DUPLICATE KEY UPDATE payload=%s""",
                (encoded, encoded),
            )
        connection.commit()
    print(f'已发布包含 {len(payload["forecast"])} 天预测的快照到 MySQL')
