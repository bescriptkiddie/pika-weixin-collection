<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  Bot,
  CheckCircle2,
  Database,
  ExternalLink,
  GitBranch,
  Link2,
  Loader2,
  MessageSquareText,
  PenLine,
  Radio,
  RefreshCw,
  Repeat2,
  Search,
  Tag,
  Video,
  Workflow,
  XCircle,
} from 'lucide-vue-next'
import type {
  ContentLoopItem,
  ContentLoopOverview,
  ExternalSourceConfigResponse,
  ExternalSourceUpsertResult,
  TaggingOverview,
  TaggingResult,
} from '@/types'

const overview = ref<ContentLoopOverview | null>(null)
const items = ref<ContentLoopItem[]>([])
const sourceConfig = ref<ExternalSourceConfigResponse | null>(null)
const loading = ref(false)
const syncing = ref(false)
const syncingExternal = ref(false)
const tagging = ref(false)
const aiEnriching = ref(false)
const addingSource = ref(false)
const feedbackingId = ref('')
const error = ref('')
const addSourceResult = ref('')
const mediaUrl = ref('')
const mediaName = ref('')
const mediaSourceType = ref<'auto' | 'bilibili_video' | 'podcast_feed'>('auto')
const mediaTranscribe = ref(true)
const tagOverview = ref<TaggingOverview | null>(null)
const selectedTag = ref('')

const stages = [
  {
    key: 'collect',
    index: '01',
    name: '人定信息源',
    status: '已有基础',
    now: '微信公众号已经可抓取，并可同步成统一 ContentItem。',
    next: '外部信源从 external_sources.json 进入，不写入 name2fakeid.json。',
    output: 'SourceConfig、human_reason、source connector。',
  },
  {
    key: 'adapter',
    index: '02',
    name: '采集适配器',
    status: 'MVP 已接',
    now: '微信适配器稳定，GitHub、B 站视频和播客按信源连接器同步。',
    next: '继续补 RSS、手动链接和网页链接连接器。',
    output: 'FetchedItem、source_type、references。',
  },
  {
    key: 'pool',
    index: '03',
    name: '标准内容池',
    status: '已落盘',
    now: 'content_items.jsonl 承接公众号和外部源。',
    next: '基于 source_type、score、human_decision 做排序和筛选。',
    output: 'ContentItem、dedupe_key、references。',
  },
  {
    key: 'feedback',
    index: '04',
    name: '人机共调',
    status: '已回写',
    now: '收藏、删除和本页决策会写入 feedback_events.jsonl。',
    next: '让反馈影响下一轮来源权重、日报阈值和生成模板。',
    output: 'FeedbackSignal、human_decision、feedback_note。',
  },
]

const activeStageKey = ref(stages[0]!.key)
const activeStage = computed(() => stages.find((stage) => stage.key === activeStageKey.value) ?? stages[0]!)

const sourceTypeBreakdown = computed(() => Object.entries(overview.value?.source_types ?? {}))
const decisionBreakdown = computed(() => Object.entries(overview.value?.human_decisions ?? {}))
const tagBreakdown = computed(() => Object.entries(tagOverview.value?.tag_counts ?? overview.value?.tag_counts ?? {}))
const filteredItems = computed(() => {
  if (!selectedTag.value) return items.value
  return items.value.filter((item) => item.tags?.includes(selectedTag.value))
})

function sourceTypeLabel(type: string) {
  const labels: Record<string, string> = {
    wechat_article: '公众号',
    github_repo: 'GitHub',
    bilibili_video: 'B站视频',
    podcast_episode: '播客',
  }
  return labels[type] ?? type
}

function decisionLabel(decision: string) {
  const labels: Record<string, string> = {
    candidate: '候选',
    adopted: '采纳',
    rejected: '删除',
    rewrite: '改写',
    dig_deeper: '深挖',
    not_relevant: '不相关',
  }
  return labels[decision] ?? decision
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init)
  const data = (await res.json().catch(() => ({}))) as { detail?: string }
  if (!res.ok) {
    throw new Error(data.detail || '请求失败')
  }
  return data as T
}

async function loadAll() {
  loading.value = true
  error.value = ''
  try {
    const [overviewData, itemsData, sourcesData, tagsData] = await Promise.all([
      requestJson<ContentLoopOverview>('/api/content-loop/overview'),
      requestJson<ContentLoopItem[]>('/api/content-loop/items?limit=500'),
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
  tagging.value = true
  error.value = ''
  try {
    await requestJson<TaggingResult>('/api/content-loop/tagging', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    })
    await loadAll()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '打标签失败'
  } finally {
    tagging.value = false
  }
}

async function runAIEnrichment() {
  aiEnriching.value = true
  error.value = ''
  try {
    await requestJson('/api/content-loop/ai-enrich', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        limit: 30,
        only_missing: true,
        tag: selectedTag.value || null,
        max_chars: 3200,
      }),
    })
    await loadAll()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'AI 分类总结失败'
  } finally {
    aiEnriching.value = false
  }
}

async function syncWechatPool() {
  syncing.value = true
  error.value = ''
  try {
    await requestJson('/api/content-loop/sync-wechat', { method: 'POST' })
    await loadAll()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '同步失败'
  } finally {
    syncing.value = false
  }
}

async function syncExternalSources() {
  syncingExternal.value = true
  error.value = ''
  try {
    await requestJson('/api/content-loop/sync-external', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ use_example: true }),
    })
    await loadAll()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '同步外部信源失败'
  } finally {
    syncingExternal.value = false
  }
}

async function addMediaSource() {
  const url = mediaUrl.value.trim()
  if (!url) {
    error.value = '先粘贴 B站视频或播客 RSS 链接'
    return
  }
  addingSource.value = true
  error.value = ''
  addSourceResult.value = ''
  try {
    const result = await requestJson<ExternalSourceUpsertResult>('/api/content-loop/sources', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        url,
        source_type: mediaSourceType.value,
        name: mediaName.value.trim(),
        transcribe: mediaTranscribe.value,
        sync_now: true,
        enabled: true,
      }),
    })
    const errors = result.sync_result?.errors ?? []
    const synced = result.sync_result?.items_synced ?? 0
    addSourceResult.value = errors.length
      ? `已保存，转写/同步错误 ${errors.length} 个`
      : `${result.created ? '已新增' : '已更新'}：${result.source.name} · 同步 ${synced} 条`
    mediaUrl.value = ''
    mediaName.value = ''
    mediaSourceType.value = 'auto'
    await loadAll()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '新增外部信源失败'
  } finally {
    addingSource.value = false
  }
}

async function sendFeedback(item: ContentLoopItem, humanDecision: string, suggestedAction: string) {
  const note = window.prompt('人工备注（可留空）', '')
  if (note === null) return
  feedbackingId.value = item.id
  error.value = ''
  try {
    await requestJson('/api/content-loop/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        item_id: item.id,
        event: 'content_pool_reviewed',
        human_decision: humanDecision,
        feedback_note: note,
        suggested_action: suggestedAction,
      }),
    })
    await loadAll()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '反馈写入失败'
  } finally {
    feedbackingId.value = ''
  }
}

onMounted(loadAll)
</script>

<template>
  <div class="app-view-shell content-loop-shell h-full overflow-y-auto px-4 py-5 sm:px-6 sm:py-6">
    <div class="mx-auto grid max-w-[1500px] gap-5">
      <header class="content-loop-hero">
        <div class="min-w-0">
          <div class="flex items-center gap-3">
            <span class="content-loop-mark">
              <Workflow class="h-5 w-5" />
            </span>
            <p class="content-loop-kicker">Content Loop</p>
          </div>
          <h1>人机共创内容生成闭环</h1>
          <p>从“抓公众号”升级为本地内容驾驶舱：人定来源和判断，AI 负责采集整理，反馈写回下一轮。</p>
        </div>
        <div class="content-loop-actions">
          <button type="button" class="loop-btn loop-btn--ghost" :disabled="loading" @click="loadAll">
            <RefreshCw class="h-4 w-4" :class="loading ? 'animate-spin' : ''" />
            刷新
          </button>
          <button type="button" class="loop-btn" :disabled="syncing" @click="syncWechatPool">
            <Loader2 v-if="syncing" class="h-4 w-4 animate-spin" />
            <Database v-else class="h-4 w-4" />
            同步公众号
          </button>
          <button type="button" class="loop-btn loop-btn--accent" :disabled="syncingExternal" @click="syncExternalSources">
            <Loader2 v-if="syncingExternal" class="h-4 w-4 animate-spin" />
            <GitBranch v-else class="h-4 w-4" />
            同步外部信源
          </button>
          <button type="button" class="loop-btn loop-btn--tag" :disabled="tagging" @click="runTagging">
            <Loader2 v-if="tagging" class="h-4 w-4 animate-spin" />
            <Tag v-else class="h-4 w-4" />
            一键打标签
          </button>
          <button type="button" class="loop-btn loop-btn--ai" :disabled="aiEnriching" @click="runAIEnrichment">
            <Loader2 v-if="aiEnriching" class="h-4 w-4 animate-spin" />
            <Bot v-else class="h-4 w-4" />
            AI 分类总结
          </button>
        </div>
      </header>

      <div v-if="error" class="content-loop-alert">
        <XCircle class="h-4 w-4 shrink-0" />
        <span>{{ error }}</span>
      </div>

      <section class="content-loop-stats">
        <article class="stat-tile">
          <Database class="h-4 w-4" />
          <span>内容池</span>
          <strong>{{ overview?.content_items ?? 0 }}</strong>
        </article>
        <article class="stat-tile">
          <Repeat2 class="h-4 w-4" />
          <span>公众号候选</span>
          <strong>{{ overview?.wechat_candidates ?? 0 }}</strong>
        </article>
        <article class="stat-tile">
          <GitBranch class="h-4 w-4" />
          <span>启用外部信源</span>
          <strong>{{ overview?.enabled_external_sources ?? 0 }}</strong>
        </article>
        <article class="stat-tile">
          <MessageSquareText class="h-4 w-4" />
          <span>反馈事件</span>
          <strong>{{ overview?.feedback_events ?? 0 }}</strong>
        </article>
        <article class="stat-tile">
          <Tag class="h-4 w-4" />
          <span>已打标签</span>
          <strong>{{ overview?.tagged_items ?? tagOverview?.tagged_items ?? 0 }}</strong>
        </article>
        <article class="stat-tile">
          <Bot class="h-4 w-4" />
          <span>AI 摘要</span>
          <strong>{{ overview?.ai_summaries ?? 0 }}</strong>
        </article>
      </section>

      <main class="content-loop-grid">
        <aside class="loop-panel loop-rail">
          <p class="panel-label">North Star</p>
          <p class="north-star">人决定方向，AI 交付候选，人和 AI 一起调优。</p>
          <p class="muted">
            当前 MVP 已把公众号缓存、GitHub / B 站 / 播客外部信源、统一内容池和人工反馈写回接起来。
          </p>

          <div class="stage-list">
            <button
              v-for="stage in stages"
              :key="stage.key"
              type="button"
              class="stage-btn"
              :class="activeStageKey === stage.key ? 'stage-btn--active' : ''"
              @click="activeStageKey = stage.key"
            >
              <span class="stage-index">{{ stage.index }}</span>
              <span class="min-w-0">
                <span class="stage-name">{{ stage.name }}</span>
                <span class="stage-status">{{ stage.status }}</span>
              </span>
            </button>
          </div>
        </aside>

        <section class="grid min-w-0 gap-5">
          <section class="loop-panel loop-map-panel">
            <div class="loop-map">
              <div class="loop-center">
                <strong>闭环成立点</strong>
                <span>反馈写回后端，影响下一轮素材、评分、选题和模板。</span>
              </div>
              <div class="loop-node loop-node--top">人定来源</div>
              <div class="loop-node loop-node--right">统一内容池</div>
              <div class="loop-node loop-node--bottom">AI 草稿</div>
              <div class="loop-node loop-node--left">反馈调优</div>
            </div>
            <div class="stage-detail">
              <p class="panel-label">当前阶段</p>
              <h2>{{ activeStage.name }}</h2>
              <dl>
                <div>
                  <dt>现在</dt>
                  <dd>{{ activeStage.now }}</dd>
                </div>
                <div>
                  <dt>下一步</dt>
                  <dd>{{ activeStage.next }}</dd>
                </div>
                <div>
                  <dt>产物</dt>
                  <dd>{{ activeStage.output }}</dd>
                </div>
              </dl>
            </div>
          </section>

          <section class="content-loop-two-col">
            <article class="loop-panel">
              <div class="panel-head">
                <div>
                  <p class="panel-label">Content Pool</p>
                  <h2>统一内容池</h2>
                </div>
                <span class="file-chip">{{ overview?.content_items_file || 'data/content_items.jsonl' }}</span>
              </div>
              <div class="mini-breakdown">
                <span v-for="[type, count] in sourceTypeBreakdown" :key="type">
                  {{ sourceTypeLabel(type) }} · {{ count }}
                </span>
                <span v-if="sourceTypeBreakdown.length === 0">等待同步</span>
              </div>
            </article>

            <article class="loop-panel">
              <div class="panel-head">
                <div>
                  <p class="panel-label">Feedback</p>
                  <h2>人工反馈</h2>
                </div>
                <span class="file-chip">{{ overview?.feedback_events_file || 'data/feedback_events.jsonl' }}</span>
              </div>
              <div class="mini-breakdown">
                <span v-for="[decision, count] in decisionBreakdown" :key="decision">
                  {{ decisionLabel(decision) }} · {{ count }}
                </span>
                <span v-if="decisionBreakdown.length === 0">等待回写</span>
              </div>
            </article>
          </section>

          <section class="loop-panel source-intake-panel">
            <form class="source-intake" @submit.prevent="addMediaSource">
              <div class="source-intake-main">
                <div class="panel-head">
                  <div>
                    <p class="panel-label">Add Source</p>
                    <h2>新增视频/播客</h2>
                  </div>
                  <span class="file-chip">data/external_sources.json</span>
                </div>
                <label class="source-field source-field--wide">
                  <span>链接</span>
                  <span class="source-input-wrap">
                    <Link2 class="h-4 w-4" />
                    <input
                      v-model="mediaUrl"
                      type="url"
                      inputmode="url"
                      placeholder="https://www.bilibili.com/video/BV... 或 RSS"
                      autocomplete="off"
                    />
                  </span>
                </label>
                <label class="source-field">
                  <span>名称</span>
                  <input v-model="mediaName" type="text" placeholder="可留空" autocomplete="off" />
                </label>
              </div>
              <div class="source-intake-side">
                <div class="source-type-tabs" role="group" aria-label="信源类型">
                  <button
                    type="button"
                    :class="mediaSourceType === 'auto' ? 'source-type-btn--active' : ''"
                    @click="mediaSourceType = 'auto'"
                  >
                    <Search class="h-4 w-4" />
                    自动
                  </button>
                  <button
                    type="button"
                    :class="mediaSourceType === 'bilibili_video' ? 'source-type-btn--active' : ''"
                    @click="mediaSourceType = 'bilibili_video'"
                  >
                    <Video class="h-4 w-4" />
                    B站
                  </button>
                  <button
                    type="button"
                    :class="mediaSourceType === 'podcast_feed' ? 'source-type-btn--active' : ''"
                    @click="mediaSourceType = 'podcast_feed'"
                  >
                    <Radio class="h-4 w-4" />
                    播客
                  </button>
                </div>
                <label class="source-check-row">
                  <input v-model="mediaTranscribe" type="checkbox" />
                  <span>云端转写</span>
                </label>
                <button type="submit" class="loop-btn loop-btn--accent" :disabled="addingSource">
                  <Loader2 v-if="addingSource" class="h-4 w-4 animate-spin" />
                  <Link2 v-else class="h-4 w-4" />
                  保存并同步
                </button>
                <p v-if="addSourceResult" class="source-result">{{ addSourceResult }}</p>
              </div>
            </form>
          </section>

          <section class="loop-panel">
            <div class="panel-head">
              <div>
                <p class="panel-label">Topic Tags</p>
                <h2>主题标签</h2>
              </div>
              <span class="file-chip">
                {{ tagOverview?.using_example_taxonomy ? '使用 example 词表' : '使用正式词表' }}
              </span>
            </div>
            <div class="tag-filter-row">
              <button
                type="button"
                class="tag-filter-btn"
                :class="selectedTag === '' ? 'tag-filter-btn--active' : ''"
                @click="selectedTag = ''"
              >
                全部
                <span>{{ items.length }}</span>
              </button>
              <button
                v-for="[tagName, count] in tagBreakdown"
                :key="tagName"
                type="button"
                class="tag-filter-btn"
                :class="selectedTag === tagName ? 'tag-filter-btn--active' : ''"
                @click="selectedTag = selectedTag === tagName ? '' : tagName"
              >
                {{ tagName }}
                <span>{{ count }}</span>
              </button>
              <span v-if="tagBreakdown.length === 0" class="muted">
                还没有标签，点击“一键打标签”先跑一版。
              </span>
            </div>
          </section>

          <section class="loop-panel">
            <div class="panel-head">
              <div>
                <p class="panel-label">Recent Items</p>
                <h2>{{ selectedTag ? `「${selectedTag}」候选素材` : '最近候选素材' }}</h2>
              </div>
              <span v-if="overview?.last_content_pool_update" class="file-chip">
                更新于 {{ overview.last_content_pool_update }}
              </span>
            </div>

            <div v-if="loading" class="empty-state">
              <Loader2 class="h-5 w-5 animate-spin" />
              加载内容池...
            </div>
            <div v-else-if="filteredItems.length === 0" class="empty-state">
              <Search class="h-5 w-5" />
              {{ items.length === 0 ? '还没有 ContentItem，先点击“同步公众号”。' : '当前标签下还没有候选素材。' }}
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
                  <p v-if="item.ai_rationale" class="ai-rationale">{{ item.ai_rationale }}</p>
                  <div v-if="item.tags?.length" class="item-tags">
                    <span v-for="tagName in item.tags.slice(0, 5)" :key="tagName">
                      {{ tagName }}
                    </span>
                  </div>
                  <a v-if="item.url" :href="item.url" target="_blank" rel="noopener noreferrer" class="item-link">
                    <ExternalLink class="h-3.5 w-3.5" />
                    原始来源
                  </a>
                </div>
                <div class="item-actions">
                  <button
                    type="button"
                    class="decision-btn decision-btn--keep"
                    :disabled="feedbackingId === item.id"
                    @click="sendFeedback(item, 'adopted', 'raise_item_score')"
                  >
                    <CheckCircle2 class="h-3.5 w-3.5" />
                    采纳
                  </button>
                  <button
                    type="button"
                    class="decision-btn"
                    :disabled="feedbackingId === item.id"
                    @click="sendFeedback(item, 'rewrite', 'adjust_generation_template')"
                  >
                    <PenLine class="h-3.5 w-3.5" />
                    改写
                  </button>
                  <button
                    type="button"
                    class="decision-btn decision-btn--dig"
                    :disabled="feedbackingId === item.id"
                    @click="sendFeedback(item, 'dig_deeper', 'raise_topic_priority')"
                  >
                    <Search class="h-3.5 w-3.5" />
                    深挖
                  </button>
                  <button
                    type="button"
                    class="decision-btn decision-btn--reject"
                    :disabled="feedbackingId === item.id"
                    @click="sendFeedback(item, 'not_relevant', 'lower_item_score')"
                  >
                    <XCircle class="h-3.5 w-3.5" />
                    不相关
                  </button>
                </div>
              </article>
            </div>
          </section>

          <section class="loop-panel">
            <div class="panel-head">
              <div>
                <p class="panel-label">External Sources</p>
                <h2>外部信源配置</h2>
              </div>
              <span class="file-chip">
                {{ sourceConfig?.using_example ? '使用 example' : '使用正式配置' }}
              </span>
            </div>
            <div class="source-list">
              <article v-for="source in sourceConfig?.sources ?? []" :key="source.id" class="source-row">
                <div class="source-icon">
                  <GitBranch class="h-4 w-4" />
                </div>
                <div class="min-w-0">
                  <h3>{{ source.name }}</h3>
                  <p>{{ source.type }} · {{ source.url }}</p>
                  <p v-if="source.human_reason" class="source-reason">{{ source.human_reason }}</p>
                </div>
                <span class="source-state" :class="source.enabled ? 'source-state--on' : ''">
                  {{ source.enabled ? '启用' : '停用' }}
                </span>
              </article>
              <div v-if="(sourceConfig?.sources ?? []).length === 0" class="empty-state">
                <GitBranch class="h-5 w-5" />
                尚未配置外部信源。
              </div>
            </div>
          </section>
        </section>
      </main>
    </div>
  </div>
</template>

<style scoped>
.content-loop-shell {
  --loop-bg: #f6f4ef;
  --loop-paper: rgba(255, 253, 248, 0.88);
  --loop-ink: #20221f;
  --loop-muted: #62665e;
  --loop-line: rgba(92, 84, 70, 0.2);
  --loop-green: #0f7b65;
  --loop-blue: #225c9d;
  --loop-coral: #b64a3b;
  --loop-amber: #9f6b16;
  background:
    linear-gradient(90deg, rgba(34, 35, 31, 0.04) 1px, transparent 1px),
    linear-gradient(180deg, rgba(34, 35, 31, 0.04) 1px, transparent 1px),
    var(--loop-bg);
  background-size: 28px 28px;
  color: var(--loop-ink);
}

.dark .content-loop-shell {
  --loop-bg: oklch(13% 0.025 264);
  --loop-paper: rgba(24, 26, 34, 0.86);
  --loop-ink: oklch(93% 0.01 264);
  --loop-muted: oklch(72% 0.02 264);
  --loop-line: rgba(255, 255, 255, 0.13);
}

.content-loop-hero,
.loop-panel,
.stat-tile {
  border: 1px solid var(--loop-line);
  border-radius: 8px;
  background: var(--loop-paper);
  box-shadow: 0 14px 34px rgba(42, 38, 29, 0.08);
  backdrop-filter: blur(18px);
}

.content-loop-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 18px;
  padding: 22px;
}

.content-loop-hero h1 {
  margin-top: 8px;
  font-size: 26px;
  font-weight: 760;
  line-height: 1.2;
  letter-spacing: 0;
}

.content-loop-hero p {
  margin-top: 6px;
  color: var(--loop-muted);
  font-size: 13px;
  line-height: 1.5;
}

.content-loop-kicker,
.panel-label {
  color: var(--loop-muted);
  font-size: 12px;
  font-weight: 760;
  letter-spacing: 0;
  text-transform: uppercase;
}

.content-loop-mark {
  display: grid;
  width: 36px;
  height: 36px;
  place-items: center;
  border: 1px solid rgba(15, 123, 101, 0.35);
  border-radius: 50%;
  background: rgba(15, 123, 101, 0.12);
  color: var(--loop-green);
}

.content-loop-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.loop-btn,
.decision-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  border-radius: 8px;
  border: 1px solid rgba(15, 123, 101, 0.24);
  background: rgba(15, 123, 101, 0.1);
  color: var(--loop-green);
  font-size: 12px;
  font-weight: 720;
  line-height: 1;
  transition: transform 0.16s ease, background 0.16s ease;
}

.loop-btn {
  min-height: 36px;
  padding: 0 13px;
}

.loop-btn:hover,
.decision-btn:hover {
  transform: translateY(-1px);
}

.loop-btn:disabled,
.decision-btn:disabled {
  cursor: not-allowed;
  opacity: 0.55;
  transform: none;
}

.loop-btn--ghost {
  border-color: var(--loop-line);
  background: transparent;
  color: var(--loop-muted);
}

.loop-btn--accent {
  border-color: rgba(34, 92, 157, 0.26);
  background: rgba(34, 92, 157, 0.12);
  color: var(--loop-blue);
}

.loop-btn--tag {
  border-color: rgba(159, 107, 22, 0.28);
  background: rgba(159, 107, 22, 0.12);
  color: var(--loop-amber);
}

.loop-btn--ai {
  border-color: rgba(110, 87, 153, 0.28);
  background: rgba(110, 87, 153, 0.12);
  color: #6e5799;
}

.content-loop-alert {
  display: flex;
  align-items: center;
  gap: 8px;
  border: 1px solid rgba(182, 74, 59, 0.24);
  border-radius: 8px;
  background: rgba(182, 74, 59, 0.1);
  color: var(--loop-coral);
  padding: 12px 14px;
  font-size: 13px;
}

.content-loop-stats {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 12px;
}

.stat-tile {
  display: grid;
  gap: 6px;
  padding: 15px;
}

.stat-tile svg {
  color: var(--loop-green);
}

.stat-tile span {
  color: var(--loop-muted);
  font-size: 12px;
}

.stat-tile strong {
  font-size: 28px;
  line-height: 1;
}

.content-loop-grid {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  gap: 18px;
  align-items: start;
}

.loop-panel {
  padding: 18px;
}

.loop-rail {
  position: sticky;
  top: 18px;
  display: grid;
  gap: 16px;
}

.north-star {
  margin-top: 6px;
  font-size: 21px;
  font-weight: 760;
  line-height: 1.22;
}

.muted {
  color: var(--loop-muted);
  font-size: 13px;
  line-height: 1.5;
}

.stage-list {
  display: grid;
  gap: 8px;
}

.stage-btn {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr);
  gap: 10px;
  align-items: center;
  width: 100%;
  border: 1px solid var(--loop-line);
  border-radius: 8px;
  background: rgba(255, 253, 248, 0.64);
  padding: 10px;
  text-align: left;
  transition: border-color 0.16s ease, background 0.16s ease, transform 0.16s ease;
}

.dark .stage-btn {
  background: rgba(255, 255, 255, 0.04);
}

.stage-btn--active,
.stage-btn:hover {
  border-color: rgba(15, 123, 101, 0.42);
  background: rgba(15, 123, 101, 0.1);
  transform: translateY(-1px);
}

.stage-index {
  display: grid;
  width: 30px;
  height: 30px;
  place-items: center;
  border-radius: 50%;
  background: var(--loop-ink);
  color: var(--loop-bg);
  font-size: 12px;
  font-weight: 760;
}

.stage-name,
.stage-status {
  display: block;
}

.stage-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
  font-weight: 740;
}

.stage-status {
  margin-top: 2px;
  color: var(--loop-muted);
  font-size: 11px;
}

.loop-map-panel {
  display: grid;
  grid-template-columns: minmax(360px, 0.9fr) minmax(0, 1fr);
  gap: 18px;
  align-items: stretch;
}

.loop-map {
  position: relative;
  min-height: 340px;
  border: 1px dashed rgba(34, 35, 31, 0.24);
  border-radius: 50%;
  background:
    radial-gradient(circle at 28% 24%, rgba(15, 123, 101, 0.12), transparent 33%),
    radial-gradient(circle at 78% 72%, rgba(34, 92, 157, 0.1), transparent 31%);
}

.loop-center {
  position: absolute;
  left: 50%;
  top: 50%;
  display: grid;
  width: 190px;
  min-height: 190px;
  place-items: center;
  transform: translate(-50%, -50%);
  border: 2px solid var(--loop-ink);
  border-radius: 50%;
  background: var(--loop-paper);
  padding: 22px;
  text-align: center;
}

.loop-center strong {
  font-size: 21px;
  line-height: 1.12;
}

.loop-center span {
  margin-top: 8px;
  color: var(--loop-muted);
  font-size: 12px;
  line-height: 1.4;
}

.loop-node {
  position: absolute;
  min-width: 112px;
  border: 1px solid var(--loop-line);
  border-radius: 8px;
  background: var(--loop-paper);
  padding: 10px 12px;
  text-align: center;
  font-size: 13px;
  font-weight: 740;
}

.loop-node--top {
  left: 50%;
  top: 18px;
  transform: translateX(-50%);
  border-top: 4px solid var(--loop-green);
}

.loop-node--right {
  right: 10px;
  top: 50%;
  transform: translateY(-50%);
  border-top: 4px solid var(--loop-blue);
}

.loop-node--bottom {
  bottom: 18px;
  left: 50%;
  transform: translateX(-50%);
  border-top: 4px solid var(--loop-coral);
}

.loop-node--left {
  left: 10px;
  top: 50%;
  transform: translateY(-50%);
  border-top: 4px solid var(--loop-amber);
}

.stage-detail h2,
.panel-head h2 {
  margin-top: 4px;
  font-size: 18px;
  font-weight: 760;
}

.stage-detail dl {
  display: grid;
  gap: 10px;
  margin-top: 14px;
}

.stage-detail dl div {
  display: grid;
  grid-template-columns: 70px minmax(0, 1fr);
  gap: 10px;
  border: 1px solid var(--loop-line);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.34);
  padding: 11px;
}

.dark .stage-detail dl div {
  background: rgba(255, 255, 255, 0.04);
}

.stage-detail dt {
  color: var(--loop-muted);
  font-size: 12px;
  font-weight: 730;
}

.stage-detail dd {
  min-width: 0;
  font-size: 13px;
  line-height: 1.48;
}

.content-loop-two-col {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.source-intake {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 260px;
  gap: 16px;
  align-items: end;
}

.source-intake-main {
  display: grid;
  gap: 12px;
}

.source-intake-side {
  display: grid;
  gap: 10px;
}

.source-field {
  display: grid;
  gap: 6px;
  min-width: 0;
}

.source-field span:first-child,
.source-check-row {
  color: var(--loop-muted);
  font-size: 12px;
  font-weight: 720;
}

.source-field input,
.source-input-wrap {
  width: 100%;
  min-width: 0;
  min-height: 38px;
  border: 1px solid var(--loop-line);
  border-radius: 8px;
  background: rgba(255, 253, 248, 0.62);
  color: var(--loop-ink);
  font-size: 13px;
}

.dark .source-field input,
.dark .source-input-wrap {
  background: rgba(255, 255, 255, 0.04);
}

.source-field input {
  padding: 0 11px;
  outline: none;
}

.source-input-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 11px;
}

.source-input-wrap svg {
  flex: none;
  color: var(--loop-muted);
}

.source-input-wrap input {
  min-height: auto;
  border: 0;
  background: transparent;
  padding: 0;
}

.source-type-tabs {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 6px;
}

.source-type-tabs button {
  display: inline-flex;
  min-width: 0;
  min-height: 34px;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border: 1px solid var(--loop-line);
  border-radius: 8px;
  background: rgba(255, 253, 248, 0.52);
  color: var(--loop-muted);
  font-size: 12px;
  font-weight: 720;
}

.dark .source-type-tabs button {
  background: rgba(255, 255, 255, 0.04);
}

.source-type-tabs .source-type-btn--active {
  border-color: rgba(34, 92, 157, 0.32);
  background: rgba(34, 92, 157, 0.1);
  color: var(--loop-blue);
}

.source-check-row {
  display: inline-flex;
  min-height: 28px;
  align-items: center;
  gap: 8px;
}

.source-check-row input {
  width: 15px;
  height: 15px;
  accent-color: var(--loop-blue);
}

.source-result {
  min-height: 18px;
  color: var(--loop-green);
  font-size: 12px;
  font-weight: 720;
}

.panel-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.file-chip,
.source-state {
  border: 1px solid var(--loop-line);
  border-radius: 999px;
  padding: 5px 9px;
  color: var(--loop-muted);
  font-size: 11px;
  white-space: nowrap;
}

.mini-breakdown {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 16px;
}

.mini-breakdown span {
  border-radius: 999px;
  background: rgba(34, 92, 157, 0.1);
  color: var(--loop-blue);
  padding: 6px 9px;
  font-size: 12px;
}

.tag-filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 16px;
}

.tag-filter-btn {
  display: inline-flex;
  min-height: 30px;
  align-items: center;
  gap: 7px;
  border: 1px solid var(--loop-line);
  border-radius: 999px;
  background: rgba(255, 253, 248, 0.54);
  color: var(--loop-muted);
  padding: 0 10px;
  font-size: 12px;
  font-weight: 700;
  transition: border-color 0.16s ease, color 0.16s ease, background 0.16s ease;
}

.dark .tag-filter-btn {
  background: rgba(255, 255, 255, 0.04);
}

.tag-filter-btn span {
  color: inherit;
  opacity: 0.72;
}

.tag-filter-btn--active,
.tag-filter-btn:hover {
  border-color: rgba(15, 123, 101, 0.35);
  background: rgba(15, 123, 101, 0.1);
  color: var(--loop-green);
}

.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 120px;
  color: var(--loop-muted);
  font-size: 13px;
}

.item-list,
.source-list {
  display: grid;
  gap: 10px;
  margin-top: 16px;
}

.content-item,
.source-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 14px;
  align-items: start;
  border: 1px solid var(--loop-line);
  border-radius: 8px;
  background: rgba(255, 253, 248, 0.58);
  padding: 14px;
}

.dark .content-item,
.dark .source-row {
  background: rgba(255, 255, 255, 0.04);
}

.item-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  color: var(--loop-muted);
  font-size: 11px;
}

.content-item h3,
.source-row h3 {
  margin-top: 6px;
  overflow-wrap: anywhere;
  font-size: 15px;
  font-weight: 750;
  line-height: 1.35;
}

.content-item p,
.source-row p {
  margin-top: 6px;
  color: var(--loop-muted);
  font-size: 12px;
  line-height: 1.5;
}

.item-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-top: 8px;
  color: var(--loop-blue);
  font-size: 12px;
  font-weight: 730;
}

.ai-summary-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 7px;
  color: #6e5799;
  font-size: 11px;
  font-weight: 730;
}

.ai-rationale {
  color: var(--loop-ink) !important;
  font-size: 11px !important;
}

.item-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.item-tags span {
  border-radius: 999px;
  background: rgba(159, 107, 22, 0.1);
  color: var(--loop-amber);
  padding: 4px 8px;
  font-size: 11px;
  font-weight: 720;
  line-height: 1.2;
}

.item-actions {
  display: grid;
  grid-template-columns: repeat(2, minmax(74px, 1fr));
  gap: 7px;
}

.decision-btn {
  min-height: 31px;
  padding: 0 9px;
}

.decision-btn--keep {
  border-color: rgba(15, 123, 101, 0.26);
  background: rgba(15, 123, 101, 0.1);
  color: var(--loop-green);
}

.decision-btn--dig {
  border-color: rgba(34, 92, 157, 0.26);
  background: rgba(34, 92, 157, 0.1);
  color: var(--loop-blue);
}

.decision-btn--reject {
  border-color: rgba(182, 74, 59, 0.24);
  background: rgba(182, 74, 59, 0.1);
  color: var(--loop-coral);
}

.source-row {
  grid-template-columns: 38px minmax(0, 1fr) auto;
  align-items: center;
}

.source-icon {
  display: grid;
  width: 34px;
  height: 34px;
  place-items: center;
  border-radius: 50%;
  background: rgba(34, 92, 157, 0.1);
  color: var(--loop-blue);
}

.source-reason {
  color: var(--loop-ink) !important;
}

.source-state--on {
  border-color: rgba(15, 123, 101, 0.3);
  background: rgba(15, 123, 101, 0.1);
  color: var(--loop-green);
}

@media (max-width: 1180px) {
  .content-loop-hero,
  .content-loop-grid,
  .loop-map-panel {
    grid-template-columns: 1fr;
  }

  .loop-rail {
    position: static;
  }

  .stage-list,
  .content-loop-stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 760px) {
  .content-loop-actions,
  .content-loop-two-col,
  .source-intake,
  .content-loop-stats,
  .stage-list,
  .content-item,
  .source-row {
    grid-template-columns: 1fr;
  }

  .content-loop-actions {
    justify-content: stretch;
  }

  .loop-btn,
  .item-actions {
    width: 100%;
  }

  .loop-map {
    display: grid;
    min-height: auto;
    gap: 10px;
    border-radius: 8px;
    padding: 12px;
  }

  .loop-center,
  .loop-node {
    position: static;
    width: 100%;
    min-height: auto;
    transform: none;
    border-radius: 8px;
  }
}
</style>
