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

## 横向展板

桌面端采用单屏横向布局，支持 16:9（1920×1080）和 16:7（1920×840）。
顶部固定呈现核心指标；「运行总览」将月度趋势与历史预测置于中央，两侧展示平台构成、站点排名和时段分布。
通过「充电结构」「行为与电池」切换专题，保留全部 13 张分析图表。指标切换和刷新对各专题统一生效。
宽度不超过 1100px 或高度不足 700px 时采用可滚动布局，小屏幕自动切换为单列。

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
