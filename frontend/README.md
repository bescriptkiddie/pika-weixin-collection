# 微信公众号聚合 - 前端

基于 Vue 3 + TypeScript + Vite 构建的本地 Web 界面，当前已从单一公众号阅读器扩展为统一内容池前端：首页是多来源内容池，`/feed` 保留公众号兼容视图，`/sources` 与 `/loop` 提供统一信源与闭环操作台。

## 快速启动

```bash
# 安装依赖（首次）
npm install

# 启动开发服务器
npm run dev
# 浏览器访问 http://localhost:5173

# 生产构建
npm run build
```

## 路由结构

| 路径 | 页面 | 说明 |
|------|------|------|
| `/#/` | `UnifiedContentView.vue` | 统一内容池首页，按来源、标签、AI 分类、人工决策统一筛选 |
| `/#/feed` | `FeedView.vue` | 公众号兼容视图，保留导出、广告过滤、语义搜索、已读收藏 |
| `/#/sources` | `SourcesView.vue` | 统一信源视图，聚合公众号与外部源读模型 |
| `/#/loop` | `ContentLoopView.vue` | 内容闭环台，含同步、标签、AI 富化、人工反馈、新增信源 |
| `/#/stats` | `StatsView.vue` | 统计图表页 |
| `/#/config` | `ConfigView.vue` | 公众号管理、扫码登录、立即爬取、定时爬取、缓存清理、封面补全 |
| `/#/logs` | `LogView.vue` | 操作日志页 |

## 主要目录

```text
frontend/
├── index.html
├── package.json
├── public/
│   ├── manifest.webmanifest
│   ├── sw.js
│   └── pwa-*.png
├── scripts/
│   └── copy-static-data.mjs
└── src/
    ├── App.vue
    ├── main.ts
    ├── router/index.ts
    ├── types/index.ts
    ├── stores/
    │   ├── articles.ts
    │   ├── config.ts
    │   ├── contentItems.ts
    │   └── sources.ts
    ├── composables/
    │   └── useFilters.ts
    ├── components/
    │   ├── articles/
    │   ├── layout/
    │   └── ui/
    └── views/
        ├── UnifiedContentView.vue
        ├── FeedView.vue
        ├── SourcesView.vue
        ├── ContentLoopView.vue
        ├── StatsView.vue
        ├── ConfigView.vue
        └── LogView.vue
```

## 数据来源

### 公众号兼容视图

`articles.ts` 继续读取本地静态数据：

- `/data/message_info.json`
- `/data/name2fakeid.json`

这些数据供 `/feed`、`/stats` 和配置页中的公众号管理使用。

### 统一内容池

`contentItems.ts` 通过后端 API 读取和操作统一内容池：

- `GET /api/content-loop/overview`
- `GET /api/content-loop/items`
- `GET /api/content-loop/sources`
- `GET /api/content-loop/tags`
- `POST /api/content-loop/sync-wechat`
- `POST /api/content-loop/sync-external`
- `POST /api/content-loop/tagging`
- `POST /api/content-loop/ai-enrich`
- `POST /api/content-loop/feedback`
- `POST /api/content-loop/sources`

### 统一信源视图

`sources.ts` 读取统一信源读模型：

- `GET /api/sources`
- `POST /api/sources/:sourceId/sync`

## 保留的公众号能力

`FeedView.vue` 与 `useFilters.ts` 仍保留：

- 导出 Markdown / CSV / JSON
- 广告过滤
- 语义搜索排序
- 日期、标签、分组、排序筛选
- 已读 / 收藏
- Feed 主题切换

## 生产构建

`npm run build` 会执行：

1. `vue-tsc -b`
2. `vite build`
3. `node scripts/copy-static-data.mjs`

构建后会把运行所需的 `data/*.json`、`data/*.jsonl` 以及存在的 `covers/` 一并复制到 `dist/data/`，便于静态部署。
