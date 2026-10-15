# V1.0 实施计划与迁移审计

日期：2026-10-15；依据 miit_workbench_v1_handoff.md 与本地实际文件。

## 产品方向

V1.0 的任务账本和 Inbox 不是终点，而是汽车公告数据资产业务应用的入口。后续建设必须围绕完整生命周期展开：来源证据可追溯、候选可核验、正式记录可发布、历史修订可比较、资产可检索导出，并以稳定契约供 mashang-service 消费。

## 审计结论

独立目录和 Git 元数据已存在，但本仓库尚无首次提交、无已确认远程。不能重复初始化或覆盖当前未跟踪资产。Service 已在 1dadb73 提交迁出；本次只读审计，不回滚、不删除 Service 文件。迁移前基线为 96e78bc71bf0e5133324793bb379c07c29ffe101。

逐文件读取 Service 基线的 512 个 Git blob，与本仓库比较：全部存在；435 个 data 文件逐字节一致，24 个 scripts 中仅 08/09 报告页脚产品名变化，其余实现一致；5 个 runs 一致；45 个 workflow 文件中仅 README、commands、pipeline 说明变化。Makefile、README 为独立环境适配。完整 SHA-256 清单见 reports/miit_migration_inventory.json。此结论限于旧 Git 已跟踪资产，不能证明旧环境中未跟踪、已忽略资产完整；当前 data 约 257 MB、reports 约 20 MB、runs 约 32 KB。尚未重建 canonical 进行语义对照。

Service 留存验证日志最后为 make verify 失败，包含已迁出入口 smoke 失败；不能把该日志描述为 Service 验证通过。当前 Service 还有无关未提交变更，不在本任务修改范围。保持 Service 功能可用的最终验收仍需在独立、干净的 Service 检出完成，不能据 README 宣称完成。

## 迁移范围与入口

| 能力 | 本仓库路径 | 策略 |
|---|---|---|
| Gov 公示发现、详情、搜索 | scripts/01_scan_gov_batch.py、02_archive_gov_vehicle_details.py、miit_gov_search.py | 已迁入；V1 后续来源适配，不由 UI 直接调用写正式路径 |
| 正式公告及 EIDC | scripts/03_fetch_miit_formal_batch.py、03_fetch_eidc_batch.py、miit_formal_source.py、eidc_source.py | 已迁入；先支持 MIIT 正式公告 URL |
| 附件解析/提取 | scripts/eidc_parser.py、eidc_doc_extract.py、04_parse_vehicle_tax.py、05_parse_purchase_tax.py | 原样复用；转换隔离到任务目录 |
| 身份、分类、来源合并 | scripts/vehicle_record_builder.py | 原样复用；batch:model，MIIT formal > EIDC > proposed，乘用车 scope gate |
| canonical 唯一 writer | scripts/06_build_vehicle_dataset.py | 保留；采集应用不得调用 main/write_table，V1.1 才设计事务发布 |
| 派生及报告 | scripts/07_build_wide_table.py、08_generate_brand_report.py、09_generate_category_report.py、report_common.py | 保留 CLI，不纳入采集任务副作用 |
| 路径/配置/契约 | scripts/miit_paths.py、workflow/batches.yaml、brand_watchlist.yaml、model_name_map.json、schemas/ | 本仓库自主维护，禁止兄弟目录运行依赖 |
| 原始及中间资产 | data/search_results、vehicle_details、vehicle_photos、raw_html、fetch_status、vehicle_tax、eidc、miit_formal | 原位保留，应用只读历史证据，新增任务隔离存储 |
| 兼容产物 | data/vehicle_parameters、wide_tables；reports；runs | 不重建、不直接导入成已核验记录 |

入口为 Makefile 的 miit-* 与 01–09 CLI；miit-run 会写 canonical 和报告，不可用于软件验证。fetch_status 是车型 checkpoint，不能冒充任务账本。Service jobs_config 未发现 MIIT job。

## 依赖与技术选择

Python >=3.11；requests、PyYAML、olefile；测试 pytest。独立 .venv，不借用 Service。现有 .doc 首选 macOS textutil，失败可用 olefile 备用；转换差异必须可见。V1.0 使用标准库 SQLite（事务、唯一键、持久任务/候选/证据索引）和本地 HTTP 服务，无云基础设施。单进程 worker，loopback 监听；后续扩容前明确 worker 租约和锁策略。

参考 Fetch 的 web/src/App.jsx、FetchBar.jsx、FileSidebar.jsx、PreviewPane.jsx：URL 输入在顶端、Inbox/资料库/任务导航在左、结构化及原文预览在右。只复用交互结构，不运行依赖 Fetch 文件 API，不把 keep/delete 映射为公告入库。

## V1.0 开发步骤及验收

1. 固化本审计、完整哈希清单、离线 baseline 测试；不移动数据。建立独立环境并执行 make test。
2. 在 scripts/ 新增应用任务与隔离 source 适配，路径经 miit_paths 解析。任务 SQLite 持久化；客户端幂等键唯一，异参复用返回冲突；重试生成新任务并保留关系；重启将中断任务标记失败，排队任务继续执行。
3. 正式公告 URL 严格验证 scheme/host/path，页面必须解析出批号，附件和跳转同样检查；不使用 get_batch_config 的未知批次默认回退。先只支持正式公告详情页；车型、公示、EIDC URL 明确返回不支持，不误抓整批。
4. 复用 parse_formal_metadata、parse_road_products、normalize_model_code、classify_source_record，保存不可变 candidate revision=1、内容 hash、来源/阶段、质量问题及证据。成功候选与任务成功状态在一个事务提交。空解析失败，不把空结果报成功；非乘用车保留原始行并标记范围问题，不进入正式库。
5. 提供 POST/GET tasks、retry、Inbox、candidate、受控 evidence API 与本地 UI。UI 可切任务、候选，查看原文及 JSON；资料库明确未开放发布，不把现存 CSV 冒充已核验库。V1.0 不提供审核/入库按钮。
6. 第 409 批使用真实归档进行离线回放，重新解析 road txt 并与历史 product_list 比较；临时目录验证任务→候选→原文链路。所有网络在测试中禁用或 mock；正式数据哈希前后保持一致。实时采集属于另一次明确的业务执行，不混入 make test。

V1.0 通过条件：支持的 URL 可创建持久任务；重复请求幂等且不同执行可留存；失败和重试可追踪；候选待核验并具备真实证据；重启可恢复；UI 真实读取 API；测试不写历史数据。完整“核验→正式入库”的业务闭环属于 V1.1，不宣称在 V1.0 已完成。

## 后续版本与消费契约

V1.1：审核绑定 candidate_id+revision+hash；问题排除留痕；幂等发布与预期版本校验；主表、参数表、审计同事务；资料库查询与同筛选导出。既有 writer 的领域函数复用，文件导出作为数据库已提交发布的派生产物，崩溃后可重试导出。

V1.2：同 observation_id 的不可变修订、差异、多来源冲突；跨批次关联需额外身份关系。V1.3：Service 仅消费带 schema_version/release_id 的发布快照，沿用 product_master/vehicle_parameter schema、vehicle_record_id、observation_id、source、stage、evidence 引用；兼容性测试通过后才退出旧入口。本次不修改旧 Service。

## 风险及阻断

- 迁出先于新应用验收已发生：记录事实，不继续移除；保留旧 Git baseline 可恢复性，Service 独立验证待完成。
- 部分历史证据被 Git 忽略：只对已跟踪资产证明完整，需额外 manifest 才能封存完整快照；不随意 git add 257 MB。
- textutil 平台差异、官方反爬/超时/格式变化：任务失败可见，原始附件保留，禁止静默空解析成功。
- 旧脚本默认写正式目录、未知批次回退及 no-download 参数实现不完整：应用不直接使用其 CLI 编排，复用无副作用解析函数。
- URL 跳转、附件路径与 HTML 脚本：限制官方 HTTPS 路径、拒绝任意跳转；原文以纯文本呈现，受控 evidence_id 读取。
- SQLite 只承诺本地单进程 worker；事务和幂等不等价于未来多机调度保证。
- V1.0 候选 source snapshot 尚不等价于完整富集 canonical 行；不新增业务推断、不改来源合并规则。
