import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import type {
  AIEnrichmentResult,
  ContentLoopItem,
  ContentLoopOverview,
  ExecutionActionResponse,
  ExecutionReviewResolveResponse,
  ExecutionRunDetail,
  ExternalSourceConfigResponse,
  ExternalSourceSyncResult,
  ExternalSourceUpsertResult,
  FeedbackProjectionSummary,
  GeoVariantResult,
  KnowledgeApplyResult,
  OpenExecutionReviewPacketResponse,
  TaggingOverview,
  TaggingResult,
  WikiExportResult,
} from '@/types'

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init)
  const data = (await res.json().catch(() => ({}))) as { detail?: string }
  if (!res.ok) {
    throw new Error(data.detail || '请求失败')
  }
  return data as T
}

export const useContentItemsStore = defineStore('content-items', () => {
  const overview = ref<ContentLoopOverview | null>(null)
  const items = ref<ContentLoopItem[]>([])
  const sourceConfig = ref<ExternalSourceConfigResponse | null>(null)
  const tagOverview = ref<TaggingOverview | null>(null)
  const latestRun = ref<ExecutionRunDetail | null>(null)
  const lastReviewResolution = ref<ExecutionReviewResolveResponse | null>(null)
  const openReviewPackets = ref<OpenExecutionReviewPacketResponse | null>(null)
  const feedbackProjection = ref<FeedbackProjectionSummary | null>(null)
  const knowledgeCandidates = ref<{ cards_index_file: string; topics_index_file: string; cards: Array<Record<string, unknown>>; topics: Array<Record<string, unknown>> } | null>(null)
  const generationBriefs = ref<{ briefs_file: string; briefs: Array<Record<string, unknown>> } | null>(null)
  const generationDrafts = ref<{ drafts_file: string; drafts: Array<Record<string, unknown>> } | null>(null)
  const geoVariants = ref<{ geo_file: string; variants: Array<Record<string, unknown>> } | null>(null)
  const lastKnowledgeApplyResult = ref<ExecutionActionResponse<KnowledgeApplyResult> | null>(null)
  const loading = ref(false)
  const error = ref('')

  const sourceTypeCounts = computed<Record<string, number>>(() => {
    if (overview.value?.source_types) {
      return overview.value.source_types
    }
    return items.value.reduce<Record<string, number>>((counts, item) => {
      const key = item.source_type || 'unknown'
      return {
        ...counts,
        [key]: (counts[key] || 0) + 1,
      }
    }, {})
  })

  async function loadLatestRun() {
    latestRun.value = await requestJson<ExecutionRunDetail>('/api/execution/runs/latest')
    return latestRun.value
  }

  async function loadAll(limit = 500) {
    loading.value = true
    error.value = ''
    try {
      const [overviewData, itemsData, sourcesData, tagsData, latestRunData, openReviewData, projectionData, knowledgeData, briefsData, draftsData, geoData] = await Promise.all([
        requestJson<ContentLoopOverview>('/api/content-loop/overview'),
        requestJson<ContentLoopItem[]>(`/api/content-loop/items?limit=${limit}`),
        requestJson<ExternalSourceConfigResponse>('/api/content-loop/sources'),
        requestJson<TaggingOverview>('/api/content-loop/tags'),
        requestJson<ExecutionRunDetail>('/api/execution/runs/latest'),
        requestJson<OpenExecutionReviewPacketResponse>('/api/execution/review-packets'),
        requestJson<FeedbackProjectionSummary>('/api/content-loop/feedback-projection'),
        requestJson<{ cards_index_file: string; topics_index_file: string; cards: Array<Record<string, unknown>>; topics: Array<Record<string, unknown>> }>('/api/wiki/knowledge-candidates'),
        requestJson<{ briefs_file: string; briefs: Array<Record<string, unknown>> }>('/api/generation/briefs'),
        requestJson<{ drafts_file: string; drafts: Array<Record<string, unknown>> }>('/api/generation/drafts'),
        requestJson<{ geo_file: string; variants: Array<Record<string, unknown>> }>('/api/generation/geo'),
      ])
      overview.value = overviewData
      items.value = itemsData
      sourceConfig.value = sourcesData
      tagOverview.value = tagsData
      latestRun.value = latestRunData
      openReviewPackets.value = openReviewData
      feedbackProjection.value = projectionData
      knowledgeCandidates.value = knowledgeData
      generationBriefs.value = briefsData
      generationDrafts.value = draftsData
      geoVariants.value = geoData
    } catch (e) {
      error.value = e instanceof Error ? e.message : '加载失败'
    } finally {
      loading.value = false
    }
  }

  async function runTagging() {
    const result = await requestJson<ExecutionActionResponse<TaggingResult>>('/api/content-loop/tagging', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    })
    await loadAll()
    return result
  }

  async function runAIEnrichment(payload: { limit?: number; onlyMissing?: boolean; sourceType?: string | null; tag?: string | null; itemIds?: string[] | null; maxChars?: number }) {
    const result = await requestJson<ExecutionActionResponse<AIEnrichmentResult>>('/api/content-loop/ai-enrich', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        limit: payload.limit ?? 30,
        only_missing: payload.onlyMissing ?? true,
        source_type: payload.sourceType ?? null,
        tag: payload.tag ?? null,
        item_ids: payload.itemIds ?? null,
        max_chars: payload.maxChars ?? 3200,
      }),
    })
    await loadAll()
    return result
  }

  async function syncWechatPool() {
    const result = await requestJson<ExecutionActionResponse<Record<string, unknown>>>('/api/content-loop/sync-wechat', { method: 'POST' })
    await loadAll()
    return result
  }

  async function syncExternalSources(payload?: { useExample?: boolean; sourceIds?: string[] | null }) {
    const result = await requestJson<ExecutionActionResponse<ExternalSourceSyncResult>>('/api/content-loop/sync-external', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        use_example: payload?.useExample ?? true,
        source_ids: payload?.sourceIds ?? null,
      }),
    })
    await loadAll()
    return result
  }

  async function exportWikiSources() {
    const result = await requestJson<ExecutionActionResponse<WikiExportResult>>('/api/wiki/export-sources', { method: 'POST' })
    await loadAll()
    return result
  }

  async function rebuildFeedbackProjection() {
    const result = await requestJson<ExecutionActionResponse<Record<string, unknown>>>('/api/content-loop/feedback-projection', { method: 'POST' })
    await loadAll()
    return result
  }

  async function resolveReviewPacket(runId: string, packetId: string, status: 'approved' | 'rejected' | 'edited', continueAfterResolve = false) {
    const result = await requestJson<ExecutionReviewResolveResponse>(`/api/execution/runs/${runId}/review/${packetId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status, continue_after_resolve: continueAfterResolve }),
    })
    lastReviewResolution.value = result
    await loadAll()
    return result
  }

  async function buildKnowledgeCandidates(limit = 30, payload?: { projectedAction?: string; itemIds?: string[] }) {
    const params = new URLSearchParams({ limit: String(limit) })
    if (payload?.projectedAction) params.set('projected_action', payload.projectedAction)
    if (payload?.itemIds?.length) params.set('item_ids', payload.itemIds.join(','))
    const result = await requestJson<ExecutionActionResponse<Record<string, unknown>>>(`/api/wiki/build-knowledge-candidates?${params.toString()}`, { method: 'POST' })
    await loadAll()
    return result
  }

  async function applyReviewedKnowledge(payload?: { cardIds?: string[]; topicIds?: string[] }) {
    const params = new URLSearchParams()
    if (payload?.cardIds?.length) params.set('card_ids', payload.cardIds.join(','))
    if (payload?.topicIds?.length) params.set('topic_ids', payload.topicIds.join(','))
    const query = params.toString()
    const result = await requestJson<ExecutionActionResponse<KnowledgeApplyResult>>(`/api/wiki/apply-reviewed-knowledge${query ? `?${query}` : ''}`, { method: 'POST' })
    lastKnowledgeApplyResult.value = result
    await loadAll()
    return result
  }

  async function buildTopicSynthesis(limit = 30, payload?: { itemIds?: string[] }) {
    const params = new URLSearchParams({ limit: String(limit) })
    if (payload?.itemIds?.length) params.set('item_ids', payload.itemIds.join(','))
    const result = await requestJson<ExecutionActionResponse<Record<string, unknown>>>(`/api/wiki/build-topic-synthesis?${params.toString()}`, { method: 'POST' })
    await loadAll()
    return result
  }

  async function buildGenerationBriefs(limit = 10, payload?: { projectedAction?: string; knowledgeCardIds?: string[] }) {
    const params = new URLSearchParams({ limit: String(limit) })
    if (payload?.projectedAction) params.set('projected_action', payload.projectedAction)
    if (payload?.knowledgeCardIds?.length) params.set('knowledge_card_ids', payload.knowledgeCardIds.join(','))
    const result = await requestJson<ExecutionActionResponse<Record<string, unknown>>>(`/api/generation/build-briefs?${params.toString()}`, { method: 'POST' })
    await loadAll()
    return result
  }

  async function buildGenerationDraft(briefId: string) {
    const result = await requestJson<ExecutionActionResponse<Record<string, unknown>>>(`/api/generation/build-draft?brief_id=${encodeURIComponent(briefId)}`, { method: 'POST' })
    await loadAll()
    return result
  }

  async function buildGeoVariants(draftId: string) {
    const result = await requestJson<ExecutionActionResponse<GeoVariantResult>>(`/api/generation/build-geo?draft_id=${encodeURIComponent(draftId)}`, { method: 'POST' })
    await loadAll()
    return result
  }

  async function addMediaSource(payload: { url: string; sourceType: string; name: string; transcribe: boolean; enabled?: boolean; syncNow?: boolean; tags?: string[] | null }) {
    const result = await requestJson<ExternalSourceUpsertResult>('/api/content-loop/sources', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        url: payload.url,
        source_type: payload.sourceType,
        name: payload.name,
        transcribe: payload.transcribe,
        sync_now: payload.syncNow ?? true,
        enabled: payload.enabled ?? true,
        tags: payload.tags ?? null,
      }),
    })
    await loadAll()
    return result
  }

  async function sendFeedback(payload: { itemId: string; event?: string; humanDecision: string; feedbackNote?: string; suggestedAction?: string; channel?: string; weight?: number }) {
    const result = await requestJson('/api/content-loop/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        item_id: payload.itemId,
        event: payload.event ?? 'content_pool_reviewed',
        human_decision: payload.humanDecision,
        feedback_note: payload.feedbackNote ?? '',
        suggested_action: payload.suggestedAction ?? '',
        channel: payload.channel ?? 'local_web',
        weight: payload.weight ?? 1,
      }),
    })
    await loadAll()
    return result
  }

  return {
    overview,
    items,
    sourceConfig,
    tagOverview,
    latestRun,
    lastReviewResolution,
    lastKnowledgeApplyResult,
    openReviewPackets,
    feedbackProjection,
    knowledgeCandidates,
    generationBriefs,
    generationDrafts,
    geoVariants,
    loading,
    error,
    sourceTypeCounts,
    loadAll,
    loadLatestRun,
    runTagging,
    runAIEnrichment,
    syncWechatPool,
    syncExternalSources,
    exportWikiSources,
    rebuildFeedbackProjection,
    resolveReviewPacket,
    buildKnowledgeCandidates,
    buildTopicSynthesis,
    applyReviewedKnowledge,
    buildGenerationBriefs,
    buildGenerationDraft,
    buildGeoVariants,
    addMediaSource,
    sendFeedback,
  }
})
