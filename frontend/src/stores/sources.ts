import { ref } from 'vue'
import { defineStore } from 'pinia'
import type { UnifiedSourcesResponse, UnifiedSourceItem } from '@/types'

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init)
  const data = (await res.json().catch(() => ({}))) as { detail?: string }
  if (!res.ok) {
    throw new Error(data.detail || '请求失败')
  }
  return data as T
}

export const useSourcesStore = defineStore('sources', () => {
  const payload = ref<UnifiedSourcesResponse | null>(null)
  const loading = ref(false)
  const error = ref('')

  async function loadSources() {
    loading.value = true
    error.value = ''
    try {
      payload.value = await requestJson<UnifiedSourcesResponse>('/api/sources')
    } catch (e) {
      error.value = e instanceof Error ? e.message : '加载失败'
    } finally {
      loading.value = false
    }
  }

  async function syncSource(source: UnifiedSourceItem) {
    const result = await requestJson<{ source_id: string; source_name?: string; source_type: string; result: Record<string, unknown> }>(`/api/sources/${encodeURIComponent(source.id)}/sync`, {
      method: 'POST',
    })
    await loadSources()
    return result
  }

  return {
    payload,
    loading,
    error,
    loadSources,
    syncSource,
  }
})
