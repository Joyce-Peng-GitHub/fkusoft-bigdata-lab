# 郑州充电能源分析大屏

CSV → HDFS → Hive ODS / DWD / DWS / ADS → MySQL → Flask REST API → Vue 3 / DataV / ECharts。

## 启动

需要 Docker Compose，首次构建需要联网下载 Hadoop、Spark 和 Python 依赖。

```sh
docker compose up -d mysql backend
# 等待 HDFS 就绪后运行批处理，成功后才发布 MySQL。
docker compose exec backend hdfs dfsadmin -safemode wait
docker compose exec backend sh /workspace/scripts/run-pipeline.sh
docker compose up -d frontend
```

打开 http://localhost:5173 。API 默认 http://localhost:5000/api/dashboard 。
原始文件放在 `data/raw/`；更新 CSV 后重新执行批处理。前端每分钟刷新，并支持手动刷新。

如果已有课程服务占用端口，可使用独立项目：

```sh
export COMPOSE_PROJECT_NAME=charging-dashboard
export API_PORT=15000 HDFS_PORT=19870 YARN_PORT=18088 SPARK_PORT=14040 WEB_PORT=15173
# 随后执行上述启动命令；大屏端口改为 15173。
```

数据卷持久化 MySQL、HDFS 和 Hive metastore。`docker compose down` 保留数据；不要用 `down -v`，除非确定要删除数据。
默认数据库密码仅供本地课程使用，可通过环境变量 MYSQL_ROOT_PASSWORD / MYSQL_PASSWORD 设置。

## 验证

```sh
docker compose exec -e PYTHONPATH=/workspace/backend backend python -m unittest discover -s /workspace/tests -v
docker compose exec frontend npm run build
docker compose exec backend python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:5000/api/health').read().decode())"
```

[数据口径、仓库分层和 API](docs/pipeline.md)。10 个独立维度和 2 个交叉对比均来自真实 Spark 聚合；支持电量和订单量切换。
图表包含面积折线、排行条形、环形、分组柱状、热力图、气泡散点。DataV 提供大屏边框和动态装饰。
不使用随机值或模拟数据；后端不可用时明确提示，已有结果保留并展示生成时间。

浏览器回归脚本位于 `tests/browser-smoke.cjs`。在安装了 `playwright-core` 与 Chromium 的测试环境中执行：

```sh
BASE_URL=http://localhost:5173 CHROMIUM_PATH=/usr/bin/chromium node tests/browser-smoke.cjs
```

检查 13 个图表、指标切换、390px 窄屏布局、服务失败时保留旧数据和首次加载失败提示。
`tests/test_warehouse.py` 使用标准库独立复算随仓库提供的数据集，校验总量、两组交叉分析及区间顺序；需先成功运行批处理。
