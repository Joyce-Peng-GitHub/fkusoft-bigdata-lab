# 郑州充电能源分析大屏

CSV → HDFS → Hive ODS / DWD / DWS / ADS → MySQL → Flask REST API → Vue 3 / DataV / ECharts。

## 启动

需要 Docker Compose，首次构建需要联网下载 Hadoop、Spark 和 Python 依赖。

```sh
docker compose up -d mysql backend
docker compose exec backend hdfs dfsadmin -safemode wait
docker compose exec backend sh /workspace/scripts/run-pipeline.sh
docker compose up -d frontend
```

如果端口被占用，可以设置环境变量：

```sh
export COMPOSE_PROJECT_NAME=charging-dashboard
export API_PORT=15000 HDFS_PORT=19870 YARN_PORT=18088 SPARK_PORT=14040 WEB_PORT=15173
# 然后执行启动命令，大屏端口即为 15173
```

默认数据库密码可通过环境变量 `MYSQL_ROOT_PASSWORD` / `MYSQL_PASSWORD` 设置。

## 验证

打开 http://localhost:5173 。

以下命令可以执行测试代码：

```sh
docker compose exec -e PYTHONPATH=/workspace/backend backend python -m unittest discover -s /workspace/tests -v
docker compose exec frontend npm run build
docker compose exec backend python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:5000/api/health').read().decode())"
```

## 停止

执行命令 `docker compose down` 停止容器。数据卷会持久化 MySQL、HDFS 和 Hive metastore。
