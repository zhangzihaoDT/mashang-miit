# mashang-miit

本仓库独立维护工信部公告采集、解析、归档、核验与结构化数据。与 mashang-service 平级，不依赖其源码、虚拟环境或配置。

- 从本仓库根目录运行，路径统一通过 scripts/miit_paths.py 解析。
- scripts/ 是实现，workflow/ 是配置及契约，data/ 是原始与结构化数据，reports/ 是报告，runs/ 是运行记录。
- 不随意覆盖原始证据；身份、来源优先级及乘用车 canonical scope 沿用已有契约。
- 采集任务、核验状态与官方 proposed/confirmed 阶段必须分开。
- 依赖安装：python3 -m venv .venv && .venv/bin/python -m pip install -r requirements-dev.txt。
- 验证：make test；不要因软件验证执行真实采集或重建正式数据。
- 不提交凭证、cookies、浏览器 profile 或本地虚拟环境。
