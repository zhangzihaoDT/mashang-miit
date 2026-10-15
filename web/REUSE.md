# Fetch 报告预览交互复用

参考来源：mashang-fetch/web/src/components/FileSidebar.jsx、PreviewPane.jsx、PreviewBody.jsx、MarkdownPreview.jsx，以及 app/preview.py、app/service.py。

- FileSidebar 的展开状态、当前文件高亮、文件大小及刷新交互适配到 library.js；Fetch 原实现按完整目录路径分组，MIIT 改为懒加载的真实逐级目录树。
- PreviewPane 的标题、路径、大小、下载与本地打开动作适配到现有工作台。
- PreviewBody 的 CSV 表格、JSON/TXT 原文预览沿用相同数据契约，CSV 由 Python 标准库处理引号、逗号和跨行字段；预览最多 500 行。
- components/MarkdownPreview.jsx 直接复制自 Fetch，沿用 ReactMarkdown + remark-gfm。仅以独立 bundle 接入原生 JS，不迁入 Fetch 的整套应用、管理写操作或构建运行环境。
- HTML 与图片为 MIIT 补充。HTML 使用 sandbox iframe 和响应 CSP，保留原文件；脚本不运行。原公告引用的未归档站点样式/图片可能不显示，正文仍可查看。

vendor/markdown.js 已提交，运行工作台不需要 Node/npm，也不依赖兄弟仓库。构建源码在 components/；需要更新 bundle 时从本目录运行 `npm install`、`npm run build:markdown`。依赖版本固定在 package.json。bundle 保留依赖自带的许可注释；react/react-dom/react-markdown/remark-gfm 均使用 MIT 许可。

Reports 文件浏览只读取 `miit_paths.REPORTS_DIR`，不把 `data/` 合并到报告树；无新数据库、索引或持久元数据。默认隐藏点文件、运行日志和数据库文件；不展示 `runs/`，不跟随符号链接。
