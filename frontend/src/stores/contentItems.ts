import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import type {
  ContentLoopItem,
  ContentLoopOverview,
  ExternalSourceConfigResponse,
  ExternalSourceSyncResult,
  ExternalSourceUpsertResult,
  TaggingOverview,
  TaggingResult,
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

  async function loadAll(limit = 500) {
    loading.value = true
    error.value = ''
    try {
      const [overviewData, itemsData, sourcesData, tagsData] = await Promise.all([
        requestJson<ContentLoopOverview>('/api/content-loop/overview'),
        requestJson<ContentLoopItem[]>(`/api/content-loop/items?limit=${limit}`),
        requestJson<ExternalSourceConfigResponse>('/api/content-loop/sources'),
        requestJson<TaggingOverview>('/api/content-loop/tags'),
      ])
      overview.value = overviewData
      items.value = itemsData
      sourceConfig.value = sourcesData
      tagOverview.value = tagsData
    } catch (e) {
      error.value = e instanceof Error ? e.message : '加载失败'
    } finally {
      loading.value = false
    }
  }

  async function runTagging() {
    const result = await requestJson<TaggingResult>('/api/content-loop/tagging', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    })
    await loadAll()
    return result
  }

  async function runAIEnrichment(payload: {
    limit?: number
    onlyMissing?: boolean
    sourceType?: string | null
    tag?: string | null
    itemIds?: string[] | null
    maxChars?: number
  }) {
    const result = await requestJson('/api/content-loop/ai-enrich', {
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
    const result = await requestJson('/api/content-loop/sync-wechat', { method: 'POST' })
    await loadAll()
    return result
  }

  async function syncExternalSources(payload?: { useExample?: boolean; sourceIds?: string[] | null }) {
    const result = await requestJson<ExternalSourceSyncResult>('/api/content-loop/sync-external', {
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

  async function addMediaSource(payload: {
    url: string
    sourceType: string
    name: string
    transcribe: boolean
    enabled?: boolean
    syncNow?: boolean
    tags?: string[] | null
  }) {
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

  async function sendFeedback(payload: {
    itemId: string
    event?: string
    humanDecision: string
    feedbackNote?: string
    suggestedAction?: string
    channel?: string
    weight?: number
  }) {
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
    loading,
    error,
    sourceTypeCounts,
    loadAll,
    runTagging,
    runAIEnrichment,
    syncWechatPool,
    syncExternalSources,
    addMediaSource,
    sendFeedback,
  }
})
