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

## 单页展板

全部 13 张分析图表与历史预测合并在一个页面上，自上而下依次为：预测面板、核心指标、
多维分析图表网格。页面整体纵向滚动，不再切换专题；指标切换和刷新对全页统一生效。
桌面端图表网格为三列，热力图跨两列展示；宽度不超过 1100px 时为两列，小屏幕自动切换为单列。

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
