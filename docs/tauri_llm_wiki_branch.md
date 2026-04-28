# Tauri + llm_wiki Branch

这个分支的方向是把现有微信公众号采集能力接到 llm_wiki 风格的知识库底座上。

## 分层

- 采集层：继续复用现有 FastAPI/Python 代码，负责公众号搜索、扫码登录、文章列表、正文缓存、封面缓存和打标签。
- 桌面壳：`frontend/src-tauri` 启动 Tauri 桌面应用，并在启动时拉起本地 FastAPI 后端。
- 知识库输入层：`src/llm_wiki_bridge` 把 `message_info.json` 与 `message_detail_text.json` 导出为 llm_wiki 兼容的 `raw/sources/wechat/**/*.md`。
- 知识库生成层：下一步接入 ingest，把 raw sources 编译成 `wiki/sources`、`wiki/entities`、`wiki/concepts`、`wiki/overview.md`。

## 当前数据出口

默认导出目录：

```text
data/llm_wiki/wechat_oa/
├── purpose.md
├── schema.md
├── raw/sources/wechat/<公众号>/<日期>-<标题>-<文章ID>.md
└── wiki/
    ├── index.md
    ├── log.md
    └── overview.md
```

命令行：

```bash
uv run python scripts/export_llm_wiki_sources.py
```

API：

```bash
curl -X POST http://127.0.0.1:8000/api/wiki/export-sources
```

桌面开发启动：

```bash
cd frontend
npm run desktop:dev
```
