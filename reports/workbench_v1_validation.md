# V1.0 开发切片验收记录

日期：2026-10-15。执行环境为本仓库独立 .venv，未使用 Service 虚拟环境或 Hub 任务。

## 已完成

- 审计交接文档、Service 迁出前 Git blob、当前脚本/配置/数据、Fetch UI 交互结构。
- 独立 Python 环境；本地 SQLite 持久任务、幂等创建、失败关联重试、启动中断恢复、候选与证据索引原子提交。
- MIIT formal 受限 URL 路由、附件受限 URL、拒绝跳转、40 MB 下载上限、隔离证据存储；复用原解析和分类函数。
- 本地 URL 输入、任务列表、Inbox、结构化/问题/原文预览；资料库显示待后续开放。

## 验证证据

`make test`：46 passed in 1.65s。首次受限运行无法绑定 loopback，获得工具执行许可后完成全套测试。测试中禁止 requests 网络请求，实时适配分支采用 mock。包括并发同幂等键、异参冲突、重试关系、进程中断、事务失败回滚、跳转拒绝、空解析失败、HTTP API 和 evidence HTML 纯文本响应。

第 409 批归档：使用 raw_detail.html 和原始 road 附件转换文本重新运行已有 parser，1,526 条记录与历史 product_list.json 完整相等。原始归档和 data/vehicle_parameters 下文件在测试前后 SHA-256 不变。1,426 行具有至少一个质量/作用域标记；这不是 1,426 个解析错误，也不是已核验或已入库车型数。保留全量来源记录，不重新推断 canonical。

浏览器手动验证：输入真实公告 URL → 创建任务 → worker 完成 → Inbox 一条待核验候选 → 第 409 批结构化预览 → road.txt 原文按钮。此次使用 archive_replay 模式，无官方网络请求。任务 0aac217a8ff14fb39df7af062a7fe2db，候选及证据保存在 runs/workbench/（忽略的本地运行数据）。截图：workbench_v1_preview.png。服务通过 make workbench-replay 启动，监听 127.0.0.1:8787。

JavaScript `node --check web/app.js` 与新增 Python 模块 compileall 通过。

## 尚未验收 / 后续

- 实时官方网络和当前机器 DOC 转换未执行；不能把 mock 分支通过等价为真实采集通过。
- V1.0 目前是正式公告单来源开发切片，列表只返回最近 100 条，尚无游标分页。公示/EIDC/单车型入口按计划分步适配，未知来源明确拒绝。
- 核验、事务入库、正式资料库、导出在 V1.1；此次没有完成“核验→正式发布”的完整业务闭环。
- Service 干净检出的回归验证未执行；已有迁出日志含失败，保持为开放风险。本次不修改 Service，也不进一步移除旧代码。
- Git 无首次提交、无远程配置。没有擅自整体暂存历史数据、创建 GitHub 仓库或推送。
