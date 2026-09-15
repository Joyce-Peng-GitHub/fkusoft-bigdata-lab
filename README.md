# FKUsoft Big Data Lab

## 启动容器

请先安装 Docker，并确保 Docker Compose 可用。在仓库根目录执行以下命令，构建镜像并在后台启动 MySQL、后端和前端容器：

```bash
docker compose up --build -d
```

首次构建需要下载 Hadoop、Spark 及项目依赖，可能需要等待一段时间。可通过以下命令确认各容器的运行状态：

```bash
docker compose ps
```

启动完成后，可访问以下服务：

- 前端界面：<http://localhost:5173>
- 后端健康检查：<http://localhost:5000/api/health>
- HDFS NameNode：<http://localhost:9870>
- YARN ResourceManager：<http://localhost:8088>
- Spark 作业界面：<http://localhost:4040>（仅在 Spark 作业运行时可用）

如需查看启动日志，请执行：

```bash
docker compose logs -f
```

使用完毕后，可停止并移除容器：

```bash
docker compose down
```

该命令会保留 Docker 卷中的 MySQL、Hadoop 和前端依赖数据；如需同时删除这些数据卷，请执行 `docker compose down -v`。
