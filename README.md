# mashang-miit

汽车公告数据资产业务应用：获取工信部汽车公告，归档原始证据，解析车型参数，并为汽车行业研究提供可追溯的数据与报告。

项目独立维护采集、解析和数据契约，可通过本地工作台使用，也可作为独立服务接入 [mashang-hub](https://github.com/zhangzihaoDT/mashang-hub)。与 `mashang-fetch`、`mashang-service` 平级，不依赖它们的源码、虚拟环境或配置。

## 开始使用

需要 Python 3.11 或以上版本。Finder 打开功能仅支持 macOS；部分 `.doc` 附件转换使用 macOS `textutil`，并保留备用提取方式。

在仓库根目录安装依赖并启动：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
./scripts/dev.sh start
```

浏览器打开 [本地工作台](http://127.0.0.1:8790)。服务管理：

```bash
./scripts/dev.sh status
./scripts/dev.sh logs
./scripts/dev.sh stop
./scripts/dev.sh restart
```

修改后端后需重启服务，前端页面刷新后加载更新。

## 本地工作台

工作台沿用 Fetch 的界面结构：顶部采集入口，左侧任务与报告导航，右侧详情预览。

### 采集任务

在顶部粘贴 **MIIT 文件发布栏目正式公告详情链接**并开始采集，页面会自动选中新任务。左侧展示最近 100 条真实任务，页面可见时每 2 秒更新状态。

任务详情提供来源链接、执行状态、时间、错误信息，以及完成后生成的候选记录、质量与作用域标记、公告元数据和来源证据。支持候选快照下载、证据预览与下载、失败关联重试，以及在 Finder 中打开当前任务的产物目录。任务角标表示最近 100 条记录中的任务数。

当前工作台尚不支持公示页、车型详情或 EIDC 链接；这些来源的既有采集能力由 CLI 管线提供。采集完成的候选仍待核验，**官方 confirmed 阶段不等于人工已审核，也不代表已正式入库**。

### Reports

直接浏览本机 `reports/` 目录，支持文件夹展开、刷新、下载、Finder 打开目录和默认应用打开文件。预览支持 Markdown（含 GFM 表格）、CSV、JSON、TXT、HTML 和常见图片格式。

Reports 角标表示整个目录的递归可见文件数，各子目录显示自身的递归文件数；不计文件夹、隐藏项或符号链接。HTML 使用隔离预览且不运行脚本；CSV 最多预览 500 行，超过 8 MiB 的文本可下载查看。

Reports 与采集任务分别浏览。历史报告和 `data/` 文件缺少任务关联时，不推断归属；不新增 Inbox 文件夹或 `data/library/`。

## 数据与采集管线

CLI 保留从官方来源到结构化数据和报告的处理链路：

```text
官方公告 / 公示
  → 发现与采集
  → 原始页面、附件、车型详情归档
  → 附件解析与参数补充
  → 车型身份、分类及来源合并
  → canonical 车型与参数表
  → 宽表与报告
```

支持的来源及优先级：

| 来源 | 官方阶段 | 作用 |
| --- | --- | --- |
| MIIT 主站正式公告 | confirmed | 最终确认主源 |
| EIDC 正式公告 | confirmed | 历史与备用确认来源 |
| MIIT 主站拟发布公示 | proposed | 提前发现及丰富车型参数 |

合并优先级为 **MIIT formal > EIDC formal > Gov proposed**。正式公告字段优先，公示详情补缺。来源归档保留全量道路机动车辆，canonical 只保留有效申报型号的乘用车。车型身份按批次与型号确定，不假设型号跨批次全局唯一。

`data/vehicle_parameters/` 中的 `product_master` 和 `vehicle_parameter` 是现有结构化消费出口。当前本地历史基线覆盖 401–411 批，共 930 条乘用车记录；这是历史数据快照，不是工作台已核验发布的记录数。

CLI 命令见 [命令速查](workflow/commands.md)，来源规则、身份和合并契约见 [管线说明](workflow/pipeline.md)。CLI 业务命令可能采集网络数据或重写正式产物，不用于软件验证。

## 项目结构与存储

| 路径 | 内容 |
| --- | --- |
| `scripts/` | 采集、解析、数据构建、报告及工作台后端 |
| `web/` | 工作台界面与品牌资源 |
| `workflow/` | 配置、数据契约、来源规则与设计方案 |
| `data/` | 本地原始证据、中间数据与结构化数据 |
| `reports/` | 可浏览的报告及分析产物 |
| `runs/` | 管线运行记录与工作台持久状态 |

路径统一由 `scripts/miit_paths.py` 解析。工作台 SQLite 账本位于 `runs/workbench/`，任务证据位于 `runs/workbench/tasks/`；新增采集与历史 canonical 数据隔离。

Git 主要版本化实现、文档与契约，**克隆仓库不等于获得本机完整数据资产**。大部分数据、报告、运行状态及原始附件被忽略，需单独备份和恢复。备份工作台时应先停止服务，再完整复制 `runs/workbench/`。不提交凭证、cookies、浏览器 profile 或虚拟环境。

## Hub 与下游集成

Hub Runtime 提供 MIIT 服务状态、启停、日志和独立工作台入口；任务、数据和报告由 MIIT 自己维护。Worker 可配置：

| 环境变量 | 用途 |
| --- | --- |
| `MASHANG_MIIT_ROOT` | MIIT 仓库路径 |
| `MASHANG_MIIT_URL` | 本地健康探测地址，默认 `http://127.0.0.1:8790` |
| `MASHANG_MIIT_UI_URL` | 可选的浏览器访问地址，与健康探测分别配置 |

工作台 API 提供持久任务创建与查询、幂等提交、关联重试、候选和证据读取；接口设计见 [工作台方案](workflow/miit_workbench_v1_handoff.md)，当前行为以实现为准。

人工审核、事务入库、不可变修订及版本化数据发布仍待实现；Service 消费 MIIT 发布快照的对接也尚未完成。后续设计见 [实施与消费契约](workflow/v1_implementation_plan.md)。

## 开发与验证

```bash
make test
```

测试覆盖解析、来源与身份规则、任务持久化、幂等和恢复、HTTP API、文件访问边界及目录计数。需要绑定临时本地端口；测试不进行真实采集或重建正式数据。部分离线验收依赖本机历史归档，纯代码检出后需先恢复相应数据。

浏览器离线验收需要可用的 Playwright 与 Chrome / Chromium：

```bash
PLAYWRIGHT_MODULE=/path/to/playwright \
CHROME_PATH=/path/to/chrome \
node scripts/tests/workbench_browser.cjs
```

该验收使用临时账本与第 409 批本地归档，覆盖提交、状态跟踪、候选与证据、重试、Finder 请求、计数和移动端布局；不设置 `CHROME_PATH` 时使用 Playwright 默认 Chromium。实时官方抓取与 DOC 转换需另行验收，待有效的新公告链接可用后执行。

文件预览组件维护见 [web/REUSE.md](web/REUSE.md)。
