<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Database, GitBranch, Radio, RefreshCw, Rss, Wrench } from 'lucide-vue-next'
import { RouterLink } from 'vue-router'
import type { UnifiedSourceItem } from '@/types'
import { useSourcesStore } from '@/stores/sources'

const sourcesStore = useSourcesStore()
const syncingSourceId = ref('')
const syncResult = ref('')

const sourceTypeLabels: Record<string, string> = {
  wechat_account: '公众号',
  github_repo: 'GitHub',
  bilibili_video: 'B站视频',
  podcast_feed: '播客 RSS',
  rss_feed: 'RSS',
  manual_clip: '手动收藏',
}

const groupedSources = computed(() => {
  const rows = sourcesStore.payload?.sources ?? []
  const groups = rows.reduce<Record<string, typeof rows>>((acc, source) => {
    const key = source.type
    const existing = acc[key] ?? []
    return {
      ...acc,
      [key]: [...existing, source],
    }
  }, {})

  return Object.entries(groups)
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([type, sources]) => ({
      type,
      label: sourceTypeLabels[type] ?? type,
      sources,
    }))
})

async function syncSource(source: UnifiedSourceItem) {
  syncingSourceId.value = source.id
  syncResult.value = ''
  try {
    const result = await sourcesStore.syncSource(source)
    const payload = result.result || {}
    const synced = typeof payload.items_synced === 'number'
      ? payload.items_synced
      : typeof payload.normalized === 'number'
        ? payload.normalized
        : 0
    syncResult.value = `${source.name} 已同步 ${synced} 条`
  } finally {
    syncingSourceId.value = ''
  }
}

onMounted(async () => {
  if (!sourcesStore.payload) {
    await sourcesStore.loadSources()
  }
})
</script>

<template>
  <div class="sources-shell h-full overflow-y-auto px-4 py-5 sm:px-6 sm:py-6">
    <div class="mx-auto grid max-w-[1500px] gap-5">
      <section class="sources-hero">
        <div>
          <div class="flex items-center gap-3">
            <span class="sources-mark">
              <Database class="h-5 w-5" />
            </span>
            <p class="sources-kicker">Sources</p>
          </div>
          <h1>统一信源视图</h1>
          <p>公众号注册表和外部源配置已经收敛到同一读模型，新增、停用、删除仍保持原路径。</p>
        </div>
        <button type="button" class="sources-btn" :disabled="sourcesStore.loading" @click="sourcesStore.loadSources()">
          <RefreshCw class="h-4 w-4" :class="sourcesStore.loading ? 'animate-spin' : ''" />
          刷新
        </button>
      </section>

        <div v-if="sourcesStore.error" class="sources-alert">{{ sourcesStore.error }}</div>
        <div v-else-if="syncResult" class="sources-alert sources-alert--success">{{ syncResult }}</div>

      <section class="sources-stats">
        <article class="stat-tile">
          <Database class="h-4 w-4" />
          <span>总信源</span>
          <strong>{{ sourcesStore.payload?.counts.total ?? 0 }}</strong>
        </article>
        <article class="stat-tile">
          <Rss class="h-4 w-4" />
          <span>公众号</span>
          <strong>{{ sourcesStore.payload?.counts.wechat_accounts ?? 0 }}</strong>
        </article>
        <article class="stat-tile">
          <GitBranch class="h-4 w-4" />
          <span>外部源</span>
          <strong>{{ sourcesStore.payload?.counts.external_sources ?? 0 }}</strong>
        </article>
        <article class="stat-tile">
          <Radio class="h-4 w-4" />
          <span>启用中</span>
          <strong>{{ sourcesStore.payload?.counts.enabled ?? 0 }}</strong>
        </article>
      </section>

      <section class="sources-panel">
        <div class="panel-head">
          <div>
            <p class="panel-label">Registry</p>
            <h2>当前信源</h2>
          </div>
          <span class="file-chip">{{ sourcesStore.payload?.external_config_path || 'data/external_sources.json' }}</span>
        </div>

        <div v-if="sourcesStore.loading && !sourcesStore.payload" class="empty-state">
          <RefreshCw class="h-5 w-5 animate-spin" />
          加载信源中...
        </div>
        <div v-else class="group-list">
          <section v-for="group in groupedSources" :key="group.type" class="source-group">
            <div class="group-head">
              <h3>{{ group.label }}</h3>
              <span>{{ group.sources.length }}</span>
            </div>
            <div class="source-list">
              <article v-for="source in group.sources" :key="source.id" class="source-row">
                <div class="source-icon">
                  <Database v-if="source.type === 'wechat_account'" class="h-4 w-4" />
                  <GitBranch v-else class="h-4 w-4" />
                </div>
                <div class="min-w-0">
                  <h4>{{ source.name }}</h4>
                  <p>{{ sourceTypeLabels[source.type] ?? source.type }} · {{ source.url || '本地公众号配置' }}</p>
                  <p class="source-meta">
                    内容 {{ source.content_count }} 条
                    <span v-if="source.last_synced_at">· 最近同步 {{ source.last_synced_at }}</span>
                    <span v-if="source.latest_item_at">· 最近内容 {{ source.latest_item_at }}</span>
                  </p>
                  <p v-if="source.human_reason" class="source-reason">{{ source.human_reason }}</p>
                </div>
                <div class="source-side">
                  <button type="button" class="sources-btn sources-btn--small" :disabled="syncingSourceId === source.id" @click="syncSource(source)">
                    <RefreshCw class="h-3.5 w-3.5" :class="syncingSourceId === source.id ? 'animate-spin' : ''" />
                    同步
                  </button>
                  <RouterLink v-if="source.type !== 'wechat_account'" to="/loop" class="source-link">
                    去闭环台
                  </RouterLink>
                  <RouterLink v-else to="/config" class="source-link">
                    去配置页
                  </RouterLink>
                  <span class="source-state" :class="source.enabled ? 'source-state--on' : ''">
                    {{ source.enabled ? '启用' : '停用' }}
                  </span>
                  <span class="source-state source-state--muted">
                    {{ source.sync_policy }}
                  </span>
                </div>
              </article>
            </div>
          </section>
          <div v-if="!groupedSources.length" class="empty-state">
            <Wrench class="h-5 w-5" />
            暂无信源。
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.sources-shell {
  --sources-bg: #f6f4ef;
  --sources-paper: rgba(255, 253, 248, 0.88);
  --sources-ink: #20221f;
  --sources-muted: #62665e;
  --sources-line: rgba(92, 84, 70, 0.2);
  --sources-green: #0f7b65;
  --sources-blue: #225c9d;
  background:
    linear-gradient(90deg, rgba(34, 35, 31, 0.04) 1px, transparent 1px),
    linear-gradient(180deg, rgba(34, 35, 31, 0.04) 1px, transparent 1px),
    var(--sources-bg);
  background-size: 28px 28px;
  color: var(--sources-ink);
}

.dark .sources-shell {
  --sources-bg: oklch(13% 0.025 264);
  --sources-paper: rgba(24, 26, 34, 0.86);
  --sources-ink: oklch(93% 0.01 264);
  --sources-muted: oklch(72% 0.02 264);
  --sources-line: rgba(255, 255, 255, 0.13);
}

.sources-hero,
.sources-panel,
.stat-tile,
.sources-alert {
  border: 1px solid var(--sources-line);
  border-radius: 8px;
  background: var(--sources-paper);
  box-shadow: 0 14px 34px rgba(42, 38, 29, 0.08);
  backdrop-filter: blur(18px);
}

.sources-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 18px;
  align-items: center;
  padding: 22px;
}

.sources-mark {
  display: grid;
  width: 36px;
  height: 36px;
  place-items: center;
  border: 1px solid rgba(15, 123, 101, 0.35);
  border-radius: 50%;
  background: rgba(15, 123, 101, 0.12);
  color: var(--sources-green);
}

.sources-kicker,
.panel-label {
  color: var(--sources-muted);
  font-size: 12px;
  font-weight: 760;
  text-transform: uppercase;
}

.sources-hero h1,
.panel-head h2 {
  margin-top: 8px;
  font-size: 24px;
  font-weight: 760;
}

.sources-hero p {
  margin-top: 6px;
  color: var(--sources-muted);
  font-size: 13px;
  line-height: 1.5;
}

.sources-btn--small {
  min-height: 30px;
  padding: 0 10px;
}

.source-link {
  color: var(--sources-blue);
  font-size: 12px;
  font-weight: 720;
}

.sources-alert--success {
  color: var(--sources-green);
}

.sources-stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.stat-tile {
  display: grid;
  gap: 6px;
  padding: 15px;
}

.stat-tile span {
  color: var(--sources-muted);
  font-size: 12px;
}

.stat-tile strong {
  font-size: 28px;
  line-height: 1;
}

.sources-panel {
  display: grid;
  gap: 16px;
  padding: 18px;
}

.panel-head,
.group-head,
.source-row,
.source-side {
  display: flex;
}

.panel-head,
.group-head {
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.file-chip,
.source-state {
  border: 1px solid var(--sources-line);
  border-radius: 999px;
  padding: 5px 9px;
  color: var(--sources-muted);
  font-size: 11px;
  white-space: nowrap;
}

.group-list,
.source-list {
  display: grid;
  gap: 12px;
}

.source-group {
  display: grid;
  gap: 10px;
}

.group-head h3 {
  font-size: 16px;
  font-weight: 740;
}

.source-row {
  justify-content: space-between;
  gap: 14px;
  align-items: flex-start;
  border: 1px solid var(--sources-line);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.28);
  padding: 14px;
}

.dark .source-row {
  background: rgba(255, 255, 255, 0.04);
}

.source-icon {
  display: grid;
  width: 36px;
  height: 36px;
  place-items: center;
  border-radius: 8px;
  background: rgba(34, 92, 157, 0.1);
  color: var(--sources-blue);
}

.source-row h4 {
  font-size: 16px;
  font-weight: 740;
}

.source-row p {
  margin-top: 6px;
  color: var(--sources-muted);
  font-size: 13px;
  line-height: 1.5;
}

.source-meta,
.source-side {
  gap: 8px;
}

.source-side {
  flex-direction: column;
  align-items: flex-end;
}

.source-state--on {
  color: var(--sources-green);
  border-color: rgba(15, 123, 101, 0.24);
  background: rgba(15, 123, 101, 0.1);
}

.source-state--muted {
  text-transform: lowercase;
}

.empty-state {
  display: flex;
  min-height: 180px;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--sources-muted);
  font-size: 13px;
}

@media (max-width: 900px) {
  .sources-stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .sources-hero,
  .source-row {
    grid-template-columns: minmax(0, 1fr);
  }

  .source-side {
    align-items: flex-start;
  }
}

@media (max-width: 720px) {
  .sources-hero,
  .sources-stats {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
