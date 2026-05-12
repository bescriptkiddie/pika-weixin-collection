<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { Bot, Database, ExternalLink, Filter, Inbox, RefreshCw, Search, Tag, Workflow, Wrench } from 'lucide-vue-next'
import { RouterLink } from 'vue-router'
import type { ContentLoopItem } from '@/types'
import { useContentItemsStore } from '@/stores/contentItems'

const props = defineProps<{
  selectedSourceType: string
}>()

const emit = defineEmits<{
  'update:selectedSourceType': [value: string]
}>()

const contentItemsStore = useContentItemsStore()
const feedbackingId = ref('')
const filters = reactive({
  keyword: '',
  sourceType: '',
  sourceName: '',
  humanDecision: '',
  aiCategory: '',
  tag: '',
  dateFrom: '',
  dateTo: '',
})

const sourceTypeLabels: Record<string, string> = {
  wechat_article: '公众号',
  github_repo: 'GitHub',
  bilibili_video: 'B站视频',
  podcast_episode: '播客',
  podcast_feed: '播客',
  rss_feed: 'RSS',
  manual_clip: '手动收藏',
}

const decisionLabels: Record<string, string> = {
  candidate: '候选',
  adopted: '采纳',
  rejected: '删除',
  rewrite: '改写',
  dig_deeper: '深挖',
  not_relevant: '不相关',
}

const sourceTypeOptions = computed(() => Object.entries(contentItemsStore.sourceTypeCounts)
  .sort((a, b) => b[1] - a[1])
  .map(([type, count]) => ({
    type,
    label: sourceTypeLabels[type] ?? type,
    count,
  })))

const sourceNameOptions = computed(() => Array.from(new Set(
  contentItemsStore.items
    .filter((item) => !filters.sourceType || item.source_type === filters.sourceType)
    .map((item) => item.source_name)
    .filter(Boolean),
)).sort((a, b) => a.localeCompare(b, 'zh-Hans-CN')))

const decisionOptions = computed(() => Array.from(new Set(
  contentItemsStore.items
    .map((item) => item.human_decision)
    .filter(Boolean),
)).sort())

const aiCategoryOptions = computed(() => Array.from(new Set(
  contentItemsStore.items
    .map((item) => item.ai_category || '')
    .filter(Boolean),
)).sort((a, b) => a.localeCompare(b, 'zh-Hans-CN')))

const tagOptions = computed(() => Array.from(new Set(
  contentItemsStore.items.flatMap((item) => item.tags || []),
)).sort((a, b) => a.localeCompare(b, 'zh-Hans-CN')))

const filteredItems = computed(() => contentItemsStore.items.filter((item) => matchesFilters(item)))

const pageTitle = computed(() => filters.sourceType === 'wechat_article' ? '公众号视图' : '统一内容池')
const pageSubtitle = computed(() => filters.sourceType === 'wechat_article'
  ? '公众号内容已降级为内容池里的一个来源筛选视图。'
  : '首页直接读取 /api/content-loop/items，按来源、标签、AI 状态和人工决策统一筛选。')

watch(
  () => props.selectedSourceType,
  (value) => {
    if (value !== filters.sourceType) {
      filters.sourceType = value || ''
    }
  },
  { immediate: true },
)

watch(
  () => filters.sourceType,
  (value) => {
    emit('update:selectedSourceType', value || '')
    if (!value) {
      filters.sourceName = ''
    }
  },
)

onMounted(async () => {
  if (!contentItemsStore.items.length) {
    await contentItemsStore.loadAll()
  }
})

function sourceTypeLabel(type: string) {
  return sourceTypeLabels[type] ?? type
}

function decisionLabel(decision: string) {
  return decisionLabels[decision] ?? decision
}

function matchesFilters(item: ContentLoopItem) {
  if (filters.sourceType && item.source_type !== filters.sourceType) {
    return false
  }

  if (filters.sourceName && item.source_name !== filters.sourceName) {
    return false
  }

  if (filters.humanDecision && item.human_decision !== filters.humanDecision) {
    return false
  }

  if (filters.aiCategory && item.ai_category !== filters.aiCategory) {
    return false
  }

  if (filters.tag && !(item.tags || []).includes(filters.tag)) {
    return false
  }

  const publishedAt = item.published_at || item.fetched_at || ''
  const itemDate = publishedAt.slice(0, 10)
  if (filters.dateFrom && itemDate < filters.dateFrom) {
    return false
  }
  if (filters.dateTo && itemDate > filters.dateTo) {
    return false
  }

  const keyword = filters.keyword.trim().toLowerCase()
  if (!keyword) {
    return true
  }

  const haystack = [
    item.title,
    item.summary,
    item.ai_summary || '',
    item.content_preview,
    item.source_name,
    item.author,
    ...(item.tags || []),
  ].join('\n').toLowerCase()

  return haystack.includes(keyword)
}

function resetFilters() {
  filters.keyword = ''
  filters.sourceType = ''
  filters.sourceName = ''
  filters.humanDecision = ''
  filters.aiCategory = ''
  filters.tag = ''
  filters.dateFrom = ''
  filters.dateTo = ''
}

async function submitFeedback(item: ContentLoopItem, humanDecision: string, suggestedAction: string) {
  const note = window.prompt('人工备注（可留空）', '')
  if (note === null) {
    return
  }

  feedbackingId.value = item.id
  try {
    await contentItemsStore.sendFeedback({
      itemId: item.id,
      humanDecision,
      feedbackNote: note,
      suggestedAction,
    })
  } finally {
    feedbackingId.value = ''
  }
}
</script>

<template>
  <div class="content-pool-shell h-full overflow-y-auto px-4 py-5 sm:px-6 sm:py-6">
    <div class="mx-auto grid max-w-[1500px] gap-5">
      <section class="content-pool-hero">
        <div>
          <div class="flex items-center gap-3">
            <span class="content-pool-mark">
              <Workflow class="h-5 w-5" />
            </span>
            <p class="content-pool-kicker">Content Hub</p>
          </div>
          <h1>{{ pageTitle }}</h1>
          <p>{{ pageSubtitle }}</p>
        </div>
        <div class="content-pool-actions">
          <button type="button" class="pool-btn pool-btn--ghost" :disabled="contentItemsStore.loading" @click="contentItemsStore.loadAll()">
            <RefreshCw class="h-4 w-4" :class="contentItemsStore.loading ? 'animate-spin' : ''" />
            刷新
          </button>
          <RouterLink to="/loop" class="pool-btn pool-btn--accent">
            <Wrench class="h-4 w-4" />
            进入闭环台
          </RouterLink>
        </div>
      </section>

      <div v-if="contentItemsStore.error" class="content-pool-alert">
        {{ contentItemsStore.error }}
      </div>

      <section class="content-pool-stats">
        <article class="stat-tile">
          <Database class="h-4 w-4" />
          <span>内容池</span>
          <strong>{{ contentItemsStore.overview?.content_items ?? contentItemsStore.items.length }}</strong>
        </article>
        <article class="stat-tile">
          <Workflow class="h-4 w-4" />
          <span>来源类型</span>
          <strong>{{ sourceTypeOptions.length }}</strong>
        </article>
        <article class="stat-tile">
          <Tag class="h-4 w-4" />
          <span>已打标签</span>
          <strong>{{ contentItemsStore.overview?.tagged_items ?? 0 }}</strong>
        </article>
        <article class="stat-tile">
          <Bot class="h-4 w-4" />
          <span>AI 摘要</span>
          <strong>{{ contentItemsStore.overview?.ai_summaries ?? 0 }}</strong>
        </article>
      </section>

      <section class="content-pool-panel grid gap-4">
        <div class="panel-head">
          <div>
            <p class="panel-label">Filters</p>
            <h2>统一筛选</h2>
          </div>
          <button type="button" class="pool-reset-btn" @click="resetFilters">
            <Filter class="h-3.5 w-3.5" />
            清空
          </button>
        </div>

        <div class="filter-grid">
          <label class="filter-field filter-field--wide">
            <span>关键词</span>
            <div class="filter-input-wrap">
              <Search class="h-4 w-4" />
              <input v-model="filters.keyword" type="text" placeholder="标题、摘要、来源、标签" autocomplete="off" />
            </div>
          </label>
          <label class="filter-field">
            <span>来源名称</span>
            <select v-model="filters.sourceName">
              <option value="">全部</option>
              <option v-for="name in sourceNameOptions" :key="name" :value="name">{{ name }}</option>
            </select>
          </label>
          <label class="filter-field">
            <span>人工决策</span>
            <select v-model="filters.humanDecision">
              <option value="">全部</option>
              <option v-for="decision in decisionOptions" :key="decision" :value="decision">{{ decisionLabel(decision) }}</option>
            </select>
          </label>
          <label class="filter-field">
            <span>AI 分类</span>
            <select v-model="filters.aiCategory">
              <option value="">全部</option>
              <option v-for="category in aiCategoryOptions" :key="category" :value="category">{{ category }}</option>
            </select>
          </label>
          <label class="filter-field">
            <span>开始日期</span>
            <input v-model="filters.dateFrom" type="date" />
          </label>
          <label class="filter-field">
            <span>结束日期</span>
            <input v-model="filters.dateTo" type="date" />
          </label>
        </div>

        <div class="chip-section">
          <p class="chip-label">来源类型</p>
          <div class="chip-row">
            <button type="button" class="chip-btn" :class="filters.sourceType === '' ? 'chip-btn--active' : ''" @click="filters.sourceType = ''">
              全部
              <span>{{ contentItemsStore.items.length }}</span>
            </button>
            <button
              v-for="option in sourceTypeOptions"
              :key="option.type"
              type="button"
              class="chip-btn"
              :class="filters.sourceType === option.type ? 'chip-btn--active' : ''"
              @click="filters.sourceType = filters.sourceType === option.type ? '' : option.type"
            >
              {{ option.label }}
              <span>{{ option.count }}</span>
            </button>
          </div>
        </div>

        <div class="chip-section">
          <p class="chip-label">标签</p>
          <div class="chip-row">
            <button type="button" class="chip-btn" :class="filters.tag === '' ? 'chip-btn--active' : ''" @click="filters.tag = ''">
              全部
            </button>
            <button
              v-for="tagName in tagOptions"
              :key="tagName"
              type="button"
              class="chip-btn"
              :class="filters.tag === tagName ? 'chip-btn--active' : ''"
              @click="filters.tag = filters.tag === tagName ? '' : tagName"
            >
              {{ tagName }}
            </button>
          </div>
        </div>
      </section>

      <section class="content-pool-panel">
        <div class="panel-head">
          <div>
            <p class="panel-label">Items</p>
            <h2>候选素材</h2>
          </div>
          <span class="panel-count">{{ filteredItems.length }} / {{ contentItemsStore.items.length }}</span>
        </div>

        <div v-if="contentItemsStore.loading && !contentItemsStore.items.length" class="empty-state">
          <RefreshCw class="h-5 w-5 animate-spin" />
          加载内容池...
        </div>
        <div v-else-if="filteredItems.length === 0" class="empty-state">
          <Inbox class="h-5 w-5" />
          当前筛选条件下没有内容。
        </div>
        <div v-else class="item-list">
          <article v-for="item in filteredItems" :key="item.id" class="content-item">
            <div class="min-w-0">
              <div class="item-meta">
                <span>{{ sourceTypeLabel(item.source_type) }}</span>
                <span>{{ item.source_name }}</span>
                <span>{{ item.published_at || item.fetched_at || '未标时间' }}</span>
                <span>{{ decisionLabel(item.human_decision || 'candidate') }}</span>
              </div>
              <h3>{{ item.title }}</h3>
              <p>{{ item.ai_summary || item.summary || item.content_preview }}</p>
              <div v-if="item.ai_summary" class="ai-summary-meta">
                <Bot class="h-3 w-3" />
                <span>{{ item.ai_category || 'AI 摘要' }}</span>
                <span v-if="typeof item.ai_confidence === 'number'">可信度 {{ Math.round(item.ai_confidence * 100) }}%</span>
              </div>
              <div v-if="item.tags?.length" class="item-tags">
                <span v-for="tagName in item.tags.slice(0, 6)" :key="tagName">{{ tagName }}</span>
              </div>
              <a v-if="item.url" :href="item.url" target="_blank" rel="noopener noreferrer" class="item-link">
                <ExternalLink class="h-3.5 w-3.5" />
                原始来源
              </a>
            </div>
            <div class="item-actions">
              <button type="button" class="decision-btn decision-btn--keep" :disabled="feedbackingId === item.id" @click="submitFeedback(item, 'adopted', 'raise_item_score')">
                采纳
              </button>
              <button type="button" class="decision-btn" :disabled="feedbackingId === item.id" @click="submitFeedback(item, 'rewrite', 'adjust_generation_template')">
                改写
              </button>
              <button type="button" class="decision-btn decision-btn--dig" :disabled="feedbackingId === item.id" @click="submitFeedback(item, 'dig_deeper', 'raise_topic_priority')">
                深挖
              </button>
              <button type="button" class="decision-btn decision-btn--reject" :disabled="feedbackingId === item.id" @click="submitFeedback(item, 'not_relevant', 'lower_item_score')">
                不相关
              </button>
            </div>
          </article>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.content-pool-shell {
  --pool-bg: #f6f4ef;
  --pool-paper: rgba(255, 253, 248, 0.88);
  --pool-ink: #20221f;
  --pool-muted: #62665e;
  --pool-line: rgba(92, 84, 70, 0.2);
  --pool-green: #0f7b65;
  --pool-blue: #225c9d;
  --pool-coral: #b64a3b;
  --pool-amber: #9f6b16;
  background:
    linear-gradient(90deg, rgba(34, 35, 31, 0.04) 1px, transparent 1px),
    linear-gradient(180deg, rgba(34, 35, 31, 0.04) 1px, transparent 1px),
    var(--pool-bg);
  background-size: 28px 28px;
  color: var(--pool-ink);
}

.dark .content-pool-shell {
  --pool-bg: oklch(13% 0.025 264);
  --pool-paper: rgba(24, 26, 34, 0.86);
  --pool-ink: oklch(93% 0.01 264);
  --pool-muted: oklch(72% 0.02 264);
  --pool-line: rgba(255, 255, 255, 0.13);
}

.content-pool-hero,
.content-pool-panel,
.stat-tile,
.content-pool-alert {
  border: 1px solid var(--pool-line);
  border-radius: 8px;
  background: var(--pool-paper);
  box-shadow: 0 14px 34px rgba(42, 38, 29, 0.08);
  backdrop-filter: blur(18px);
}

.content-pool-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 18px;
  padding: 22px;
}

.content-pool-mark {
  display: grid;
  width: 36px;
  height: 36px;
  place-items: center;
  border: 1px solid rgba(15, 123, 101, 0.35);
  border-radius: 50%;
  background: rgba(15, 123, 101, 0.12);
  color: var(--pool-green);
}

.content-pool-kicker,
.panel-label,
.chip-label {
  color: var(--pool-muted);
  font-size: 12px;
  font-weight: 760;
  text-transform: uppercase;
}

.content-pool-hero h1,
.panel-head h2 {
  margin-top: 8px;
  font-size: 24px;
  font-weight: 760;
  line-height: 1.2;
}

.content-pool-hero p {
  margin-top: 6px;
  color: var(--pool-muted);
  font-size: 13px;
  line-height: 1.5;
}

.content-pool-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.pool-btn,
.pool-reset-btn,
.chip-btn,
.decision-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 720;
  transition: transform 0.16s ease, background 0.16s ease;
}

.pool-btn,
.decision-btn {
  min-height: 36px;
  padding: 0 13px;
  border: 1px solid rgba(15, 123, 101, 0.24);
  background: rgba(15, 123, 101, 0.1);
  color: var(--pool-green);
}

.pool-btn:hover,
.pool-reset-btn:hover,
.chip-btn:hover,
.decision-btn:hover {
  transform: translateY(-1px);
}

.pool-btn--ghost,
.pool-reset-btn {
  border: 1px solid var(--pool-line);
  background: transparent;
  color: var(--pool-muted);
}

.pool-btn--accent,
.chip-btn--active {
  border: 1px solid rgba(34, 92, 157, 0.26);
  background: rgba(34, 92, 157, 0.12);
  color: var(--pool-blue);
}

.content-pool-alert {
  padding: 12px 14px;
  color: var(--pool-coral);
  font-size: 13px;
}

.content-pool-stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.stat-tile {
  display: grid;
  gap: 6px;
  padding: 15px;
}

.stat-tile svg {
  color: var(--pool-green);
}

.stat-tile span {
  color: var(--pool-muted);
  font-size: 12px;
}

.stat-tile strong {
  font-size: 28px;
  line-height: 1;
}

.content-pool-panel {
  display: grid;
  gap: 16px;
  padding: 18px;
}

.panel-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.panel-count {
  color: var(--pool-muted);
  font-size: 12px;
  font-weight: 720;
}

.filter-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.filter-field {
  display: grid;
  gap: 6px;
  min-width: 0;
}

.filter-field--wide {
  grid-column: span 2;
}

.filter-field span:first-child {
  color: var(--pool-muted);
  font-size: 12px;
  font-weight: 720;
}

.filter-field input,
.filter-field select,
.filter-input-wrap {
  width: 100%;
  min-width: 0;
  min-height: 38px;
  border: 1px solid var(--pool-line);
  border-radius: 8px;
  background: rgba(255, 253, 248, 0.62);
  color: var(--pool-ink);
  font-size: 13px;
}

.dark .filter-field input,
.dark .filter-field select,
.dark .filter-input-wrap {
  background: rgba(255, 255, 255, 0.04);
}

.filter-field input,
.filter-field select {
  padding: 0 11px;
  outline: none;
}

.filter-input-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 11px;
}

.filter-input-wrap input {
  min-height: auto;
  border: 0;
  background: transparent;
  padding: 0;
}

.filter-input-wrap svg {
  color: var(--pool-muted);
}

.chip-section {
  display: grid;
  gap: 8px;
}

.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.chip-btn {
  min-height: 30px;
  border: 1px solid var(--pool-line);
  background: rgba(255, 253, 248, 0.52);
  color: var(--pool-muted);
  padding: 0 10px;
}

.dark .chip-btn {
  background: rgba(255, 255, 255, 0.04);
}

.chip-btn span {
  color: inherit;
  opacity: 0.8;
}

.item-list {
  display: grid;
  gap: 12px;
}

.content-item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 14px;
  align-items: start;
  border: 1px solid var(--pool-line);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.28);
  padding: 14px;
}

.dark .content-item {
  background: rgba(255, 255, 255, 0.04);
}

.item-meta,
.ai-summary-meta,
.item-tags,
.item-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.item-meta {
  color: var(--pool-muted);
  font-size: 12px;
}

.content-item h3 {
  margin-top: 8px;
  font-size: 17px;
  font-weight: 740;
}

.content-item p {
  margin-top: 8px;
  color: var(--pool-muted);
  font-size: 13px;
  line-height: 1.55;
}

.ai-summary-meta {
  margin-top: 8px;
  color: var(--pool-blue);
  font-size: 12px;
  align-items: center;
}

.item-tags {
  margin-top: 10px;
}

.item-tags span {
  border-radius: 999px;
  background: rgba(34, 92, 157, 0.1);
  color: var(--pool-blue);
  padding: 5px 8px;
  font-size: 12px;
}

.item-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: 10px;
  color: var(--pool-green);
  font-size: 12px;
  font-weight: 720;
}

.item-actions {
  width: 220px;
  justify-content: flex-end;
}

.decision-btn--keep {
  color: var(--pool-green);
}

.decision-btn--dig {
  color: var(--pool-amber);
  border-color: rgba(159, 107, 22, 0.28);
  background: rgba(159, 107, 22, 0.12);
}

.decision-btn--reject {
  color: var(--pool-coral);
  border-color: rgba(182, 74, 59, 0.24);
  background: rgba(182, 74, 59, 0.1);
}

.empty-state {
  display: flex;
  min-height: 180px;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--pool-muted);
  font-size: 13px;
}

@media (max-width: 1100px) {
  .content-pool-stats,
  .filter-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .content-item {
    grid-template-columns: minmax(0, 1fr);
  }

  .item-actions {
    width: auto;
    justify-content: flex-start;
  }
}

@media (max-width: 720px) {
  .content-pool-hero {
    grid-template-columns: minmax(0, 1fr);
  }

  .content-pool-actions {
    justify-content: flex-start;
  }

  .content-pool-stats,
  .filter-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .filter-field--wide {
    grid-column: span 1;
  }
}
</style>
