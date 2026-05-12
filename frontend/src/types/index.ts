// ─────────────────────────────────────────────────────────────────────────────
// 全局 TypeScript 类型定义
// 所有页面和组件共用的数据结构都在这里声明，保持类型一致性。
// ─────────────────────────────────────────────────────────────────────────────

// ── 文章数据（对应 message_info.json 中每篇博客的结构） ──────────────────────
export interface Article {
  id: string           // 唯一 ID：格式为 "{msgid}-{aid}-{create_time}"
  title: string        // 文章标题
  digest: string       // 文章摘要（微信原始摘要）
  link: string         // 微信原文链接（点击后跳转）
  cover: string        // 封面图原始 URL（微信 CDN，可能有防盗链）
  create_time: string  // 发布时间，格式 "YYYY-MM-DD HH:MM"
  is_deleted: boolean  // 是否已被公众号删除
  item_show_type: number  // 文章展示类型（0=普通图文，5=视频 等，非 0 一般跳过）

  // 预留 LLM 字段，目前为空，后续接入大模型打标签/摘要时填充
  tags?: string[]      // LLM 生成的标签列表
  summary?: string     // LLM 生成的文章摘要（比 digest 更精炼）
}

// ── 单个公众号的文章集合（message_info.json 中每个 key 对应的 value） ────────
export interface AccountData {
  latest_update_time: string  // 最后一次成功爬取的时间
  blogs: Article[]            // 该公众号的所有文章列表
}

// message_info.json 的完整结构：{ "公众号名称": AccountData, ... }
export type MessageInfo = Record<string, AccountData>

// name2fakeid.json 的结构：{ "公众号名称": "fakeid字符串", ... }
export type Name2FakeId = Record<string, string>

// ── 公众号信息（前端展示用，合并了 name2fakeid 和 message_info 的数据） ──────
export interface AccountInfo {
  name: string               // 公众号名称
  fakeid: string             // 微信内部 ID
  latest_update_time: string // 最后爬取时间
  article_count: number      // 当前有效文章数
  visible: boolean           // 是否在文章流中显示（可通过配置隐藏）
}

// ── 筛选/排序/分组相关类型 ────────────────────────────────────────────────────

// 文章排序方式
export type SortOrder = 'newest' | 'oldest'  // 最新优先 / 最早优先

// 文章分组方式
export type GroupBy = 'date' | 'account' | 'none'  // 按日期 / 按公众号 / 不分组

// 已读/收藏筛选
export type ReadFilter = 'all' | 'unread' | 'bookmarked'  // 全部 / 未读 / 已收藏

// FilterBar 组件管理的所有筛选条件
export interface FilterState {
  keyword: string        // 关键词搜索（匹配标题、摘要、AI 摘要）
  accounts: string[]     // 只显示选中公众号的文章（空数组=显示全部）
  tags: string[]         // 标签过滤（需同时含有所有选中标签）
  dateFrom: string       // 日期范围起始（格式 "YYYY-MM-DD"）
  dateTo: string         // 日期范围结束（格式 "YYYY-MM-DD"）
  sortOrder: SortOrder   // 排序方式
  groupBy: GroupBy       // 分组方式
  readFilter: ReadFilter // 已读状态筛选
}

// ── API 响应类型（与后端 api.py 中的 Pydantic 模型对应） ─────────────────────

// GET /api/auth/status 和 POST /api/auth/check 的响应
export interface AuthStatus {
  has_credentials: boolean  // id_info.json 中是否有 token 和 cookie
  valid: boolean            // 上次检测凭证是否有效
  checked_at: string        // 上次检测时间
  error: string             // 失败原因（正常时为空）
  token_hint: string        // token 前 8 位，供确认身份
  id_info_mtime: string     // id_info.json 最后修改时间
}

// GET /api/cache/preview 的响应（清理前预览）
export interface CachePreview {
  keep_days: number            // 保留天数
  cutoff_date: string          // 截止日期
  total_articles: number       // 当前文章总数
  removable_articles: number   // 将删除的文章数
  removable_covers: number     // 将删除的封面图数
  removable_detail_texts: number // 将删除的详情缓存数
}

// GET /api/crawl/status 的响应（爬取进度，前端轮询）
export interface CrawlStatus {
  running: boolean      // 是否正在爬取
  total: number         // 本次需爬取的公众号总数
  done: number          // 已完成的公众号数
  current: string       // 正在爬取的公众号名称
  errors: string[]      // 本次爬取错误列表
  started_at: string    // 开始时间
  finished_at: string   // 结束时间（未结束时为空）
  new_articles: number  // 本次新增文章数
  auth_error: boolean   // 是否因凭证失效而终止
}

// POST /api/wiki/export-sources 的响应
export interface WikiExportResult {
  export_root: string
  raw_sources_dir: string
  exported: number
  skipped: number
  accounts: number
}

// ── 内容闭环：ContentItem / 外部源 / 反馈统计 ───────────────────────────────

export interface ContentLoopOverview {
  content_items: number
  feedback_events: number
  wechat_candidates: number
  external_sources: number
  enabled_external_sources: number
  source_types: Record<string, number>
  human_decisions: Record<string, number>
  tagged_items: number
  ai_summaries: number
  ai_tagged: number
  tag_counts: Record<string, number>
  auto_tag_counts: Record<string, number>
  content_items_file: string
  feedback_events_file: string
  source_config_file: string
  source_config_is_example: boolean
  last_content_pool_update: string
}

export interface ContentLoopItem {
  id: string
  source_type: string
  source_id: string
  source_name: string
  title: string
  url: string
  author: string
  published_at: string
  fetched_at: string
  summary: string
  ai_summary?: string
  tags: string[]
  auto_tags?: string[]
  ai_tags?: string[]
  ai_category?: string
  ai_confidence?: number
  ai_rationale?: string
  ai_enriched_at?: string
  tag_scores?: Record<string, number>
  tag_evidence?: Record<string, string[]>
  score: number
  status: string
  human_decision: string
  feedback_notes: string[]
  content_preview: string
  references: Array<Record<string, unknown>>
  metadata: Record<string, unknown>
}

export interface ExternalSourceConfig {
  id: string
  type: string
  name: string
  url: string
  enabled: boolean
  human_reason: string
  options: Record<string, unknown>
}

export interface ExternalSourceConfigResponse {
  path: string
  using_example: boolean
  sources: ExternalSourceConfig[]
}


export interface ExternalSourceSyncResult {
  config_path: string
  using_example_config: boolean
  export_root: string
  sources_total: number
  sources_selected: number
  sources_synced: number
  sources_skipped: number
  items_synced: number
  content_pool: Record<string, unknown>
  source_results: Array<Record<string, unknown>>
  errors: string[]
}

export interface UnifiedSourceItem {
  id: string
  source_id: string
  type: string
  name: string
  url: string
  enabled: boolean
  human_reason: string
  sync_policy: string
  last_synced_at: string
  last_error: string
  content_count: number
  latest_item_at: string
  metadata: Record<string, unknown>
}

export interface UnifiedSourcesResponse {
  sources: UnifiedSourceItem[]
  counts: {
    total: number
    wechat_accounts: number
    external_sources: number
    enabled: number
  }
  external_config_path: string
  external_config_is_example: boolean
}

export interface ExternalSourceUpsertResult {
  config_path: string
  source: ExternalSourceConfig
  created: boolean
  updated: boolean
  sources_total: number
  data_dir: string
  sync_result?: ExternalSourceSyncResult | null
}

export interface TaxonomyTag {
  name: string
  description: string
  keywords: string[]
}

export interface TaggingOverview {
  taxonomy_file: string
  using_example_taxonomy: boolean
  taxonomy_tags: TaxonomyTag[]
  content_items_file: string
  topic_tags_file: string
  total_items: number
  tagged_items: number
  untagged_items: number
  topic_mentions: number
  tag_counts: Record<string, number>
  auto_tag_counts: Record<string, number>
}

export interface TaggingResult {
  content_items_file: string
  topic_tags_file: string
  taxonomy_file: string
  using_example_taxonomy: boolean
  total: number
  tagged: number
  untagged: number
  updated: number
  tag_counts: Record<string, number>
}
