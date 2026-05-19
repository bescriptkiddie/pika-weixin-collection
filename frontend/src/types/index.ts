// ─────────────────────────────────────────────────────────────────────────────
// 全局 TypeScript 类型定义
// ─────────────────────────────────────────────────────────────────────────────

export interface Article {
  id: string
  title: string
  digest: string
  link: string
  cover: string
  create_time: string
  is_deleted: boolean
  item_show_type: number
  tags?: string[]
  summary?: string
}

export interface AccountData {
  latest_update_time: string
  blogs: Article[]
}

export type MessageInfo = Record<string, AccountData>
export type Name2FakeId = Record<string, string>

export interface AccountInfo {
  name: string
  fakeid: string
  latest_update_time: string
  article_count: number
  visible: boolean
}

export type SortOrder = 'newest' | 'oldest'
export type GroupBy = 'date' | 'account' | 'none'
export type ReadFilter = 'all' | 'unread' | 'bookmarked'

export interface FilterState {
  keyword: string
  accounts: string[]
  tags: string[]
  dateFrom: string
  dateTo: string
  sortOrder: SortOrder
  groupBy: GroupBy
  readFilter: ReadFilter
  excludeAds: boolean
  semanticSearch: boolean
}

export type ExportFormat = 'markdown' | 'csv' | 'json'

export interface AuthStatus {
  has_credentials: boolean
  valid: boolean
  checked_at: string
  error: string
  token_hint: string
  id_info_mtime: string
}

export interface CachePreview {
  keep_days: number
  cutoff_date: string
  total_articles: number
  removable_articles: number
  removable_covers: number
  removable_detail_texts: number
}

export interface CoverRefillPreview {
  total_articles: number
  missing_covers: number
}

export interface CoverRefillResult {
  total_articles: number
  missing_before: number
  downloaded: number
  failed: number
}

export interface CrawlScheduleStatus {
  enabled: boolean
  time: string
  last_run_at: string
  last_status: string
  last_message: string
}

export interface CrawlStatus {
  running: boolean
  total: number
  done: number
  current: string
  errors: string[]
  started_at: string
  finished_at: string
  new_articles: number
  auth_error: boolean
}

export interface WikiExportResult {
  export_root: string
  raw_sources_dir: string
  exported: number
  skipped: number
  accounts: number
}

export interface KnowledgeApplyIds {
  cards: string[]
  topics: string[]
}

export interface KnowledgeApplyReasons {
  cards: Record<string, string>
  topics: Record<string, string>
}

export interface KnowledgeApplyResult {
  export_root: string
  written_cards: number
  written_topics: number
  cards_index_file: string
  topics_index_file: string
  requested_ids: KnowledgeApplyIds
  accepted_ids: KnowledgeApplyIds
  rejected_ids: KnowledgeApplyIds
  rejected_reasons?: KnowledgeApplyReasons
}

export interface ExecutionFailureState {
  scope: string
  stage: string
  code: string
  message: string
  retryable: boolean
  degraded: boolean
  action_required: string
  action_hint: string
  provider: string
  provider_trace: Array<Record<string, unknown>>
  verify_type: string
  verify_uuid: string
  occurred_at: string
}

export interface ExecutionTask {
  task_id: string
  run_id: string
  kind: string
  status: string
  depends_on: string[]
  attempt: number
  input_ref: Record<string, unknown>
  output_ref: Record<string, unknown>
  provider_trace_ref: Record<string, unknown>
  started_at: string
  finished_at: string
  failure_state?: ExecutionFailureState | null
}

export interface ExecutionArtifact {
  artifact_id: string
  run_id: string
  task_id: string
  type: string
  path: string
  checksum: string
  created_at: string
  meta: Record<string, unknown>
}

export interface ExecutionReviewFollowUpError {
  target_id: string
  error: string
}

export interface ExecutionReviewResolveResponse {
  packet_id: string
  run_id: string
  task_id: string
  kind: string
  reason: string
  candidate_payload: Record<string, unknown>
  suggested_action: string
  status: string
  resolved_at: string
  resolved_by: string
  follow_up_result?: ExecutionActionResponse<Record<string, unknown> | KnowledgeApplyResult>
  follow_up_results?: Array<ExecutionActionResponse<Record<string, unknown> | KnowledgeApplyResult>>
  follow_up_errors?: ExecutionReviewFollowUpError[]
}

export interface ExecutionReviewPacket {
  packet_id: string
  run_id: string
  task_id: string
  kind: string
  reason: string
  candidate_payload: Record<string, unknown>
  suggested_action: string
  status: string
  resolved_at: string
  resolved_by: string
}

export interface ExecutionRun {
  run_id: string
  intent: string
  status: string
  trigger: string
  started_at: string
  finished_at: string
  summary: string
  context: Record<string, unknown>
  current_task: string
  failure_state?: ExecutionFailureState | null
}

export interface OpenExecutionReviewPacket extends ExecutionReviewPacket {
  run_intent: string
  run_status: string
  run_summary: string
  started_at: string
  preview?: {
    label: string
    summary: string
    items?: string[]
    details?: Record<string, unknown>
  }
  follow_up?: {
    action: string
    target_id?: string
    target_ids?: string[]
    count?: number
    label: string
  }
}



export interface OpenExecutionReviewPacketResponse {
  review_packets: OpenExecutionReviewPacket[]
}

export interface ExecutionRunDetail {
  run: ExecutionRun | null
  tasks: ExecutionTask[]
  events: Array<{
    timestamp: string
    type: string
    message: string
    details: Record<string, unknown>
  }>
  review_packets: ExecutionReviewPacket[]
  artifacts: ExecutionArtifact[]
}

export interface ExecutionActionResponse<T> {
  run: ExecutionRun
  task: ExecutionTask
  artifact: ExecutionArtifact
  failure_state: ExecutionFailureState | null
  review_packet?: ExecutionReviewPacket | null
  result: T
}

export interface FeedbackProjectionRule {
  scope: string
  key: string
  total_feedback: number
  priority_delta?: number
  dominant_decision: string
  decision_counts: Record<string, number>
  strategy_hint?: string
}

export interface FeedbackProjectionReason {
  scope: string
  key: string
  priority_delta: number
  dominant_decision: string
  total_feedback: number
  strategy_hint?: string
}

export interface ProjectedActionInfo {
  projected_action?: string
  projected_action_label?: string
  projected_action_reason?: string
  projected_action_scope?: string
}

export interface FeedbackProjectionBlockedReasonEntry {
  reason: string
  count: number
}

export interface FeedbackProjectionRecommendedAction {
  action: string
  action_key?: string
  label: string
  count: number
  top_score: number
  score_range: {
    min: number
    max: number
  }
  actionable: boolean
  execution_kind: string
  execution_label: string
  execution_blocked_reason: string
  precondition_statuses: string[]
  precondition_passed: boolean
  ready_count: number
  blocked_count: number
  blocked_item_ids: string[]
  blocked_reason_by_item: Record<string, string>
  blocked_reason_breakdown: FeedbackProjectionBlockedReasonEntry[]
  blocked_sample_titles: string[]
  pending_approval_label?: string
  pending_approval_count: number
  pending_approval_item_ids: string[]
  missing_candidate_item_ids: string[]
  pending_approval_card_ids: string[]
  pending_approval_packet_ids: string[]
  pending_approval_sample_titles: string[]
  missing_candidate_count: number
  missing_candidate_sample_titles: string[]
  fallback_actionable: boolean
  fallback_execution_kind: string
  fallback_execution_label: string
  fallback_execution_params: Record<string, unknown>
  execution_params: Record<string, unknown>
  item_ids: string[]
  sample_titles: string[]
  sample_ids: string[]
}

export interface FeedbackProjectionProjectedItem {
  id: string
  title: string
  source_name: string
  projected_score: number
  feedback_projection_delta: number
  projected_action: string
  projected_action_label: string
  projected_action_reason: string
}

export interface FeedbackProjectionSummary {
  projection_file: string
  rows: number
  scope_counts: {
    tag: number
    source: number
    action: number
  }
  updated_at: string
  top_positive: FeedbackProjectionRule[]
  top_negative: FeedbackProjectionRule[]
  top_actions: FeedbackProjectionRule[]
  recommended_actions: FeedbackProjectionRecommendedAction[]
  top_projected_items: FeedbackProjectionProjectedItem[]
}

export interface ContentLoopOverview {
  content_items: number
  feedback_events: number
  feedback_projection_rules?: number
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
  feedback_projection_file?: string
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
  projected_score?: number
  feedback_projection_delta?: number
  feedback_projection_reasons?: FeedbackProjectionReason[]
  projected_action?: string
  projected_action_label?: string
  projected_action_reason?: string
  projected_action_scope?: string
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

export interface AIEnrichmentOverview {
  configured: boolean
  base_url: string
  model: string
  has_api_key: boolean
  api_key_hint: string
  ai_summaries: number
  ai_tagged: number
  ai_errors: number
}


export interface AIEnrichmentResult {
  content_items_file: string
  total_candidates: number
  processed: number
  skipped: number
  failed: number
  model: string
  errors: Array<{
    item_id: string
    error: string
  }>
}

export interface GeoVariantResult {
  geo_file: string
  created: number
  geo_id: string
  draft_id: string
}

export interface GenerationTraceFields {
  source_run_id?: string
  source_task_id?: string
  source_packet_id?: string
  applied_run_id?: string
  applied_task_id?: string
  applied_packet_id?: string
}
