# mashang-miit

工信部公告 · 获取与整理。独立仓库，与 mashang-fetch、mashang-service 平级。

开发交接与工作台接口方案见 [V1 handoff](workflow/miit_workbench_v1_handoff.md)；Hub 接入尚待开发。

## 独立运行

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
make test
make miit-scan BATCH=411
```

运行依赖仅声明在本仓库，不复用 Service 的环境。现阶段保留原有 CLI 管线；Inbox、人工核验和工作台 API 仍待实现。`.doc` 转换沿用现有解析器，部分平台路径使用 macOS `textutil` 或系统转换工具。

迁移包含现有 data/、reports/、runs/ 资产；未复制 Service 凭证或虚拟环境。新仓库尚未配置远程地址。

---

# MIIT Gov Proposed Vehicle Intelligence Pipeline

工信部拟公告新车情报模块：**发现拟公告 → 找到关注车型 → 归档车型事实 → 结构化参数 → 补充监管附件 → 生成分析数据与报告。**

管线技术细节见 [workflow/pipeline.md](workflow/pipeline.md)，命令速查见 [workflow/commands.md](workflow/commands.md)。

## 主链路

```
MIIT.gov.cn
  → P1 搜索   → data/search_results/ + reports/batch_{batch}/scan_report.html
  → P2 归档   → data/vehicle_details/ + data/vehicle_photos/ + data/fetch_status/
  → P3 补充   → data/vehicle_tax/车型清单_第XX批车船税.json
  → P4 Dataset→ data/wide_tables/wide_table_{batch}.csv
  → P4.5 统一Dataset → data/vehicle_parameters/product_master + vehicle_parameter
  → P5 报告   → reports/batch_{batch}/
```

## EIDC（confirmed 双源）

EIDC 正式公告（miit-eidc.org.cn）作为 confirmed source，与 Gov proposed 共用同一 canonical 出口：

```
EIDC 官方公告页
  → 03_fetch_eidc_batch.py（source 抓取/解析/归档）
  → data/eidc/batch_{N}/（product_list.json + import_manifest + 附件 evidence）
  → 06_build_vehicle_dataset.py（canonical 唯一入口，与 Gov 共用）
  → data/vehicle_parameters/（source=eidc, stage=confirmed）
```

- **source 层**（`eidc_source.py` / `eidc_parser.py`）只回答"官方页面提供了什么"；**领域解释**在 `vehicle_record_builder.py`；**canonical writer** 只有 `06`。
- 当前 **401-408 全部为 fresh rebuild**（官方公告 → 全量解析 → passenger scope gate），legacy 导入已删除。
- 分类维度 `vehicle_category` / `analysis_scope` 为派生，不参与 identity。
- **canonical scope**：Source archive 保留全量道路机动车辆；`vehicle_parameters/` 只落乘用车（`model_code valid AND vehicle_category==passenger_vehicle`）。Gov/EIDC 共用同一 `is_canonical_in_scope()` gate。

**完整技术说明 / source contract / pipeline 细节见 [data/eidc/README.md](data/eidc/README.md)。**

## MIIT 正式公告（primary confirmed）

MIIT 主站正式公告（`miit.gov.cn/jgsj/zbys/wjfb/` 文件发布）作为**最终确认主源**：

```
miit.gov.cn 文件发布栏目（正式公告，非拟发布公示）
  → 03_fetch_miit_formal_batch.py（发现/抓取/解析/归档）
  → data/miit_formal/batch_{N}/（product_list.json + import_manifest，source=miit_gov, stage=confirmed）
  → 06_build_vehicle_dataset.py（canonical，proposed→confirmed merge）
  → data/vehicle_parameters/
```

- 附件与 EIDC 同源（同一 `miit.gov.cn/cms_files` 的「道路机动车辆生产企业及产品（第N批）.doc」），**解析层完全复用** `eidc_parser`。
- 定位：**MIIT formal = primary final source；EIDC formal = fallback / historical support**。
- canonical merge 优先级：`MIIT formal > EIDC formal > Gov proposed`；formal 确认字段优先，proposed rich fields 只补缺。
- 详见 [workflow/pipeline.md](workflow/pipeline.md) 与 [data/miit_formal/README.md](data/miit_formal/README.md)。

## 5 类资产（阅读顺序）

| 目录 | 是什么 | 什么时候打开 |
|------|--------|--------------|
| [workflow/](workflow/) | 规则、规划、配置、命令 | **想知道怎么用 / 为什么存在** |
| [scripts/](scripts/) | 所有可执行脚本（平铺，按管线顺序编号） | **想运行** |
| [data/](data/) | 获取的数据 + 加工中间数据（按内容命名） | **想看原始 / 中间数据** |
| [reports/](reports/) | 最终给人看的产出 | **想看结论** |
| [runs/](runs/) | 每轮运行记录 / 经验沉淀 | **想知道上一批踩了什么坑** |

```
MIIT/
├── README.md
├── Makefile
├── reports/       ① 最终报告（batch_409/ batch_410/）
├── data/          ② 事实数据（eidc/ search_results/ vehicle_details/ vehicle_photos/ raw_html/ vehicle_tax/ vehicle_parameters/ wide_tables/ fetch_status/）
├── scripts/       ③ 执行脚本（01~09 管线 entrypoint 平铺；未编号 = 内部实现/validation）
├── runs/          ④ 运行记录（batch_409.md batch_410.md eidc_fresh_rebuild.md）
└── workflow/      ⑤ 规则与配置（pipeline.md commands.md batches.yaml brand_watchlist.yaml model_name_map.json schemas/ docs/）
```

> 这不是标准 Python package，而是一个**持续运行、持续积累数据、持续形成分析结果的 Research Intelligence Workspace**。
> 顶层只保留 5 个认知入口；脚本按管线顺序 `01→07` 平铺在 scripts/。

## 快速跑一轮

```bash
make miit-run BATCH=410   # P1 搜索 → P2 归档 → P4 宽表 → P4.5 统一Dataset → P5 报告
```

分步见 [workflow/commands.md](workflow/commands.md)；P3 车船税补充为手动步骤。

## 当前状态

已处理 **401–411** 全部批次。统一 Dataset（`data/vehicle_parameters/product_master` + `vehicle_parameter`）当前 **930 车型，全部为乘用车（`vehicle_category == passenger_vehicle`）**：
- **miit_gov / confirmed**：409（**128** = 49 Gov variant 被正式公告确认 + 79 formal-only，MIIT 正式公告 2026-08-13）
- **miit_gov / proposed**：410:17 + 411:20（37）
- **eidc / confirmed**：**401-408 全部 fresh rebuild**，合计 765
  - 401:117 / 402:135 / 403:43 / 404:84 / 405:63 / 406:94 / 407:96 / 408:133

> **401-408 EIDC fresh/confirmed + 409 MIIT formal confirmed + 410-411 Gov fresh/proposed = 干净版本节点。**
> canonical 收敛为乘用车业务事实层：Source archive 保留全量道路机动车辆，`vehicle_parameters/` 只落乘用车（`model_code valid AND vehicle_category==passenger_vehicle`）。
> 409 的 Gov proposed 由 MIIT 正式公告做 **formal confirmation matching**：variant 保留完整申报型号（`XMA6500KREEVA1`），formal 基码只补缺、不覆盖，`stage` 升级为 `confirmed`；无 Gov 详情的正式车型以目录基码独立成行。

观测时间轴：`observation_id = {batch}:{model_code}:{stage}`，401 confirmed → 411 proposed。
批次索引见 [workflow/docs/公告批次.md](workflow/docs/公告批次.md)，各批运行经验见 [runs/](runs/)。

## 测试

```bash
make test       # 冒烟：所有脚本 --help 可用
```

## 后续方向

- 自动发现 pageId；新增 vs 改款自动标识；差异增量通知
- 跨批次 diff（401 confirmed → 410 proposed）：默认 `analysis_scope='in_scope'`（乘用车）为母体
- 409/410 Gov proposed 批次 fresh 解析（当前为公示 scan，可补 Gov 官方详情页深度参数）
- Agent / API 默认消费 `vehicle_parameters/`（乘用车业务层），不再过滤全量

## 本地工作台 V1.0 开发切片

审计、迁移路径和逐阶段验收见 [实施计划](workflow/v1_implementation_plan.md)，历史资产比较清单见 [迁移清单](reports/miit_migration_inventory.json)。清单记录应用开发前的迁移状态，不是运行数据的发布版本。

```bash
make workbench-replay  # 第 409 批真实归档离线回放，不访问官方网络
# 浏览器打开 http://127.0.0.1:8787
# 输入链接：
# https://www.miit.gov.cn/jgsj/zbys/wjfb/art/2026/art_4951b91392884d049c623d59387f6172.html
```

`make workbench` 为实时采集模式，仅在用户提交 URL 后执行网络采集。V1.0 支持 MIIT 文件发布栏目正式公告详情链接；其他来源、车型链接返回明确错误。服务固定监听 loopback，同一运行目录只允许一个进程。运行数据在 `runs/workbench/`，包含 SQLite 任务账本、候选快照和任务隔离证据，已加入忽略规则；备份时应停止服务后完整复制该目录。

客户端 `POST /api/miit/tasks` 提交 `url` 和 `idempotency_key`，返回持久 task_id；GET 同路径查看最近 100 条任务。`GET /api/miit/inbox`、`candidates/{id}`、`evidence/{id}` 提供候选和证据预览；`POST tasks/{id}/retry` 使用新幂等键创建关联重试。队列在服务运行时自动消费；进程中断后 running 任务变为明确失败，queued 任务继续执行。API 是本地 V1 开发契约，完整分页、审核发布、资料库及导出待 V1.1。

候选保留全量来源行，质量问题单列；候选的 confirmed 是官方阶段，pending_review 是人工核验状态。当前不提供审核和入库接口，不调用 canonical writer，不把历史 CSV 自动标记成已审核资料库。第 409 批离线回放验证来源解析一致性；实时网络、DOC 转换及 Service 回归尚需独立验收。
