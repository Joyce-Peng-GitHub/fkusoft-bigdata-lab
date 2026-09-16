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

页面通过侧栏切换运营总览、周期规律、平台设施、充电特征、地点车辆、电池遥测和趋势预测，每页聚焦 1–3 个图表。地址栏的 hash（例如 `/#time`）可直接定位子页面，浏览器前进/后退也会同步导航。分析指标和刷新按钮对当前分析生效，数据每 60 秒自动刷新。顶部双线动画在首次进入、手动或自动刷新以及切换子页面时播放一次；系统启用减少动态效果时不播放。

桌面窗口（宽度大于 900px、高度至少 620px）按视口分配图表空间，减少页面滚动；较窄或较矮的窗口改为自然纵向布局，保留图表可读性。手机上导航排列在顶部，避免侧栏挤占图表宽度。周期规律采用上方热力图、下方两张节律图的布局，热力图绘图区按 24 列、7 行约束格子比例；平台设施采用左侧分组柱状图、右侧上下两张构成图的布局。

以下命令可以执行测试代码：

```sh
docker compose exec -e PYTHONPATH=/workspace/backend backend python -m unittest discover -s /workspace/tests -v
docker compose exec frontend npm run build
docker compose exec backend python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:5000/api/health').read().decode())"
```

## 停止

执行命令 `docker compose down` 停止容器。数据卷会持久化 MySQL、HDFS 和 Hive metastore。
