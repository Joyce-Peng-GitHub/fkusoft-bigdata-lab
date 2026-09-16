# 验证记录

工作区从 2026-09-15 获取的 `origin/main`（`e871987`）创建，分支 `codex/data-dashboard`。

## 实际链路

独立 Docker Compose 项目 `charging-dashboard`，使用独立 HDFS / MySQL 卷和端口。
实际执行三次 Spark 4.2.0 / Hadoop 3.5.0 作业，覆盖首次运行、重启后重跑和审核修复后重跑。
ODS / DWD / DWS / ADS 均通过 Spark Hive catalog 持久化；每次成功作业发布同一 MySQL 快照行。

结果：3,395 条订单，105 个站点，19,723.69 kWh，费用 401.52，平均时长约 2.84149 小时。
订单异常隔离 0，重复删除 0；电池有效记录 1,594 条。重复执行总量保持一致。

## 自动验证

- Flask 和仓库测试：5 项通过；验证 200/404/503 响应、敏感错误隐藏、独立 CSV 总量复算、两组交叉分析、数值区间排序。
- Vue TypeScript + Vite 生产构建通过。构建有大体积 bundle 提示（约 1.48 MB，gzip 479 KB），未影响功能；当前为本地课程大屏。
- Vite 同源代理实际返回 Flask/MySQL 的 3,395 条订单汇总。
- Chromium 真浏览器回归通过：13 个图表均生成 canvas、切换订单指标、390px 无横向溢出、刷新失败保留旧数据、首次失败不展示指标、无未捕获页面异常。

## 子代理审核

两位子代理分别检查仓库规范与需求正确性。
首轮均发现同一个 P2：时长、电量分段按字符串排序。已加入显式数值顺序和回归检查。
第二轮两位均报告无剩余可操作问题。

浏览器测试按图表容器及其 canvas 检查渲染，不将 canvas 个数等同图表个数，因为 ECharts 可为单张图创建多个图层。

## 浮点显示修复

真实 Chromium / ECharts 提示曾复现 `123.99999999999993`。展示层格式化后，13 个图表的提示均显示舍入值（例如 `124`），不再泄露浮点尾差；TypeScript 和生产构建通过。子代理复核无可操作问题。
使用与浏览器回归相同的 playwright-core / Chromium 环境执行 `node tests/precision-smoke.cjs`；该脚本面向 Vite 开发服务，通过实际加载的 ECharts 模块触发提示。

## PR #6：机器学习预测接入 Web（2026-09-16）

- 合并 `origin/main` 的面板调整；根目录 `README.md` 与 main 完全一致。
- 独立 Compose 项目 `ml-forecast-pr6` 完成镜像构建、真实 Spark/Hive 流水线、
  MySQL 发布、模型训练与 7 天递归预测。历史截至 **2015-10-04**，预测范围为
  **2015-10-05 至 2015-10-11**；日期基于数据末日，不是当前日期。
- 预测 JSON 原子发布到共享数据目录；浏览器经 Vite → Flask 读取，7 个电量点与模型输出逐项一致。
- 容器中 `PYTHONPATH=/workspace/backend:/workspace/ml python -m unittest discover -s /workspace/tests -v`：
  **6 项全部通过**，包含实际仓库对账、API 合约、原子替换失败保留旧结果和未就绪状态。
- `npm run build`：TypeScript 与生产构建通过；保留现有 bundle 大小提示。
- Chromium：`tests/forecast-browser.cjs` 使用确定性接口数据验证实际/预测边界、零值、
  小数订单估算、指标切换、390px 布局、刷新失败保留旧结果、首次失败及恢复。
  使用 Vite 开发服务运行，需安装 `playwright`，可设置 `BASE_URL` 与 `CHROMIUM_PATH`。
- 真实服务上的 `tests/browser-smoke.cjs` 和 `tests/precision-smoke.cjs` 均通过，
  原有 13 张分析图、指标切换、移动布局、失败处理和提示精度无回归。

## ML 预测改为 MySQL 发布（2026-09-16，分支 `feat/ml-forecast-mysql`）

- 预测产物从共享文件 `data/processed/forecast.json` 改为 MySQL `forecast_snapshot` 单行 JSON 快照：
  `ml/export.py` 复用 `backend/db.py` 的 `MYSQL_*` 连接设置做单行事务发布，
  `GET /api/ml/forecast` 改为查询该表，删除 `FORECAST_PATH` 文件读取分支。
- `ml/predict.py` 仍输出 `ml/forecast_result.csv` 作为人工查看副本；`ml/requirements.txt` 增加
  `mysql-connector-python`。
- 本机（`node100`，非 Docker）执行 `PYTHONPATH=backend:ml python3 -m unittest discover -s tests -v`：
  共 6 项，其中 1 项依赖流水线产物的对账用例按设计跳过，其余全部通过。覆盖快照表 DDL、
  提交负载、结构与 NaN 校验、提交失败上抛、接口 200/503 及敏感错误隐藏。
- 未在本机重跑完整 Spark/Hive/Docker 链路；Dockerfile 与 Compose 未改动，仅发布与读取通道变化。

### Forecast panel presentation update

The panel is now titled “历史与预测”. The metadata and explanatory paragraphs
have been removed. The dashed prediction series starts at the final historical
value, connecting it to the first forecast point for both energy and sessions.
TypeScript checks, the production build, and the updated forecast browser
regression passed, including the title, removed paragraphs and dashed connection.
