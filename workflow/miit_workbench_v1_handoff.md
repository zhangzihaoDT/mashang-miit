# mashang-miit V1：现有能力核对与开发对接方案

日期：2026-10-15。本文是基于本地源代码的开发交接方案，不代表接口已经实现。MIIT 已迁至与 mashang-service 平级的独立仓库 mashang-miit；本文同步迁入，由 MIIT 项目维护。

长期产品定位：`mashang-miit` 是维护汽车公告数据资产的完整业务应用。获取、解析、归档、车型身份、核验、版本、入库、检索、导出和下游消费契约属于同一产品边界；当前 V1 工作台只是其中的第一阶段。当前业务范围聚焦工信部汽车公告，历史研究模块不计入能力范围。

## 结论

复用 mashang-fetch 的界面外壳和交互模式，将文件对象替换为公告批次与车型记录。MIIT 已具备脚本管线，但尚需应用层才能实现“输入链接 → 采集解析 → Inbox 核验 → 入库 → 历史检索”。第一版不增加研究看板、AI 对话或战略分析。

## 核对依据

- Fetch：兄弟仓库 mashang-fetch 的 `web/src/App.jsx`、`api.js`、`components/FetchBar.jsx`、`FileSidebar.jsx`、`PreviewPane.jsx`。
- MIIT：`README.md`（以下 MIIT 路径均相对本仓库根目录）、`workflow/pipeline.md`、`workflow/schemas/product_master.schema.json`、`fetch_status.schema.json`、`scripts/02_archive_gov_vehicle_details.py`、`scripts/06_build_vehicle_dataset.py`。
- 迁移时核对的 Service `jobs/config/jobs_config.json` 没有 MIIT job；Hub 接入尚未实现，不能将 Service 的 jobs CLI 宣称为 MIIT 可用的应用接口。MIIT 的应用接口和执行适配应在本仓库维护，Hub 通过明确契约调用，不回迁 Service。

## 复用与适配

| Fetch 现有组件 | MIIT 处理 |
|---|---|
| Header / App 两栏外壳 | 保留布局，将产品名和副标题替换为 mashang-miit / 工信部公告 · 获取与整理 |
| FetchBar | URL 输入、忙碌及错误反馈保留；输出格式改为自动识别/公告批次/车型页面 |
| FileSidebar | 保留列表交互；对象改为批次、候选车型及任务；导航为 Inbox/资料库/采集任务 |
| PreviewPane | 保留预览容器和来源信息；内容改为原始公告/结构化数据/变更对比 |
| MarkdownPreview / PdfPreview | 仅按实际原始资料类型复用 |
| api.js / state.js | 适配领域对象和异步任务，不能直接复用文件 API 契约 |
| keep / rename / delete | “移入资料库”替换为核验与入库；文件重命名、删除不直接映射为公告操作 |

复用路径只是本地参考，不引入对兄弟仓库绝对路径的运行依赖。第一步迁入必要组件和样式并注明来源；共享组件包留待真实重复需求出现。

## 现有后端可复用部分

- Gov proposed 发现与详情归档；MIIT formal 和 EIDC confirmed 抓取与附件解析。
- 原始 HTML、附件、照片、抓取 checkpoint 与来源归档。
- `06_build_vehicle_dataset.py` 是现有 canonical writer，输出 product_master / vehicle_parameter 的 CSV 和 JSON。
- 已有车型键 `vehicle_record_id={batch_no}:{model_code}`；观测键 `observation_id={batch_no}:{model_code}:{stage}`。
- 正式来源优先级为 MIIT formal > EIDC formal > Gov proposed；现有 canonical 仅收乘用车，原始来源保留全量道路机动车辆。

## 必须补齐的应用层

1. URL 类型识别及来源路由：现有入口主要按批次和配置运行，尚不能等价为任意 URL 采集 API。未知、无法识别或不支持的来源返回明确错误，不擅自猜批次。
2. 持久任务记录：现有 fetch_status 是车型抓取 checkpoint，不是每次执行独立留存的任务账本。
3. 候选快照与核验记录：采集完成先保存候选版本，记录缺失、重复、解析错误、人工处理结论。
4. 入库事务：现有 writer 会生成数据文件，尚不是逐条审核、并发控制及审计完备的入库服务。
5. 查询、原文定位、历史版本及字段比较 API。

不要让“采集”直接触发 canonical 全量写入。新增适配层应调用既有采集/解析能力生成隔离候选，再通过唯一写入路径发布。

## 对象与状态契约（建议）

| 对象 | 身份与用途 |
|---|---|
| 采集任务 | task_id；每次执行独立，保存输入 URL、识别类型、时间、错误、产物及重试关系 |
| 候选快照 | candidate_id + revision；关联 task_id，保存不可变解析结果、内容摘要和核验问题 |
| 公告批次 | batch_no 作为批次索引；同一批次可有公示、正式公告和多来源证据，不能互相覆盖 |
| 车型记录 | 沿用 vehicle_record_id；跨批次型号相同仍是不同申报记录 |
| 观测及修订 | observation_id + revision/content_hash；同一官方阶段再次采集有变化时保存新修订 |
| 原始证据 | evidence_id；关联来源 URL、获取时间、归档路径及内容摘要；字段指向证据及可用定位信息 |

三套状态分开保存：

- 任务状态：queued → running → succeeded / partial_success / failed。
- 核验状态：pending_review → approved / rejected；approved 且入库成功后为 imported；未处理阻断问题不得 approved。
- 官方阶段：proposed / confirmed，沿用原定义；公示记录可以完成核验并入库，入库不自动变成 confirmed。

任务失败不等于已有正式记录无效。失败重试创建新 task_id 并关联前次任务。同一任务可部分成功，成功候选可单独核验，失败项必须可见。

## 入库规则

- 以 candidate_id + revision 绑定核验；解析内容变化后旧核验失效。
- 入库时重新检查候选修订、必填字段、作用域、稳定身份、重复及来源优先级。
- 请求携带幂等键与预期版本；重复点击只提交一次，版本冲突返回明确结果。
- 同键同内容关联新增采集证据，不新增重复车型；同键内容变化保存修订及差异。
- 比较基线优先同一记录的上个已入库修订；跨批次车型匹配必须额外建立关联，不能单凭 model_code 自动认定同一市场车型。
- 首版以整份候选中的可入库车型集合原子提交：有阻断问题则不提交；用户可明确排除问题行后重新核验提交集合。排除记录留痕。
- 正式写入与审计应同成同败；不得出现 UI 显示成功但查询不到记录，或失败后只写入半套主表与参数表。
- CSV/JSON 可继续作为兼容导出；任务、审核、版本和发布需要可事务化的持久层。具体存储选型属于独立开发任务。

## API 草案（均待实现）

| 方法与路径 | 职责 |
|---|---|
| POST /api/miit/tasks | 输入 url、capture_type、客户端幂等键；202 返回 task_id |
| GET /api/miit/tasks | 分页查看任务和错误 |
| GET /api/miit/tasks/{id} | 查看进度、候选及失败项 |
| POST /api/miit/tasks/{id}/retry | 新建关联重试任务 |
| GET /api/miit/inbox | 分页查询待核验候选 |
| GET /api/miit/candidates/{id} | 候选字段、修订、质量问题、证据与差异 |
| POST /api/miit/candidates/{id}/review | 提交绑定 revision 的通过/驳回及问题处理、排除行 |
| POST /api/miit/candidates/{id}/import | 携带 revision、预期正式版本与幂等键；返回 inserted/updated/unchanged |
| GET /api/miit/batches | 批次列表及入库统计 |
| GET /api/miit/vehicles | 按批次、品牌、型号、企业、官方阶段分页检索 |
| GET /api/miit/vehicles/{id}/versions | 版本和证据链 |
| GET /api/miit/evidence/{id} | 经受控路径解析读取原始证据，不开放任意本地路径 |
| GET /api/miit/export | 导出显式筛选范围 CSV/JSON，包含来源及官方阶段 |

采集 URL 应限制到支持的官方来源并验证跳转；后台异步执行固定参数入口，不将用户输入拼成 shell。所有错误返回 code/message/task_id（适用时）及可重试标识。

## 第一版验收场景

1. 已支持的批次链接产生独立任务；成功后在 Inbox 展示真实候选及来源。
2. 车型链接只采对应对象，不误触整批采集；未知类型显示可理解的错误。
3. 待核验数据不会出现在正式资料库；采集本身不改 canonical。
4. 缺失必填字段、非法型号、非乘用车候选可查看原因并被阻断或明确排除。
5. 同一链接重复采集保留两次执行记录，正式车型不重复。
6. 公示与正式发布来源的合并遵守现有优先级并保留证据；官方阶段与入库状态各自正确。
7. 任一展示字段可回到已有原文证据；缺乏精确字段定位时如实展示文档级证据。
8. 旧候选核验后内容被更新，入库请求被版本检查阻断。
9. 入库失败不产生部分正式记录；重复请求和并发入库结果一致。
10. 资料库可按批次/品牌/型号检索，并导出同一筛选范围；空值不显示为 0。
11. 无可用比较版本时显示“暂无对比版本”，不伪造差异。

## 实施顺序

A. 在独立开发任务中建立 MIIT 应用 API、持久任务及候选层，先打通一个受支持批次来源。
B. 从 Fetch 复用外壳，接入真实任务、Inbox 与原文/结构化预览。
C. 实现绑定版本的核验、幂等入库、资料库检索与 CSV/JSON 导出。
D. 补齐同记录修订比较、车型链接入口以及多来源冲突场景。

后续软件实现从本仓库根目录启动，遵守本仓库 AGENTS.md；本文中的 API、核验与入库机制仍属待实现方案。Hub 侧运行协议以 mashang-hub 的协议文档为准，本文不代表已完成 Hub 接入。
