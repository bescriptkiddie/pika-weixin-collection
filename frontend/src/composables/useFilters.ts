// ─────────────────────────────────────────────────────────────────────────────
// useFilters — 文章筛选/排序/分组组合式函数（Composable）
//
// Vue 3 的 Composable 类似 React Hook：将相关的响应式逻辑封装成一个函数，
// 供多个组件复用，避免在组件中堆积大量逻辑。
//
// 使用方：FeedView.vue（负责将结果传给 FilterBar 和文章列表）
//
// 筛选流程：
//   allArticles（全部） → 公众号可见性过滤 → 关键词/账号/标签/日期过滤
//   → 已读状态过滤 → 排序 → 分组 → groupedArticles（最终结果）
// ─────────────────────────────────────────────────────────────────────────────

import { computed, reactive } from 'vue'
import { useArticlesStore } from '@/stores/articles'
import { useConfigStore } from '@/stores/config'
import { useReadingStore } from '@/stores/reading'
import type { FilterState, GroupBy } from '@/types'

function normalizeSemanticText(text: string) {
  return text
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .replace(/[“”‘’'"`~!@#$%^&*()_+\-=\[\]{};:,.<>/?\\|]+/g, ' ')
    .trim()
}

function buildSemanticTerms(text: string) {
  const normalized = normalizeSemanticText(text)
  if (!normalized) return []

  const words = normalized.split(' ').filter(Boolean)
  const joined = normalized.replace(/\s+/g, '')
  const grams: string[] = []
  for (let i = 0; i < joined.length - 1; i += 1) {
    grams.push(joined.slice(i, i + 2))
  }

  return [...words, ...grams]
}

function buildSemanticVector(text: string) {
  const counts = new Map<string, number>()
  for (const term of buildSemanticTerms(text)) {
    counts.set(term, (counts.get(term) ?? 0) + 1)
  }

  let sumSquares = 0
  counts.forEach((value) => {
    sumSquares += value * value
  })
  const norm = Math.sqrt(sumSquares) || 1

  const vector = new Map<string, number>()
  counts.forEach((value, key) => {
    vector.set(key, value / norm)
  })
  return vector
}

function cosineSimilarity(a: Map<string, number>, b: Map<string, number>) {
  let score = 0
  const smaller = a.size <= b.size ? a : b
  const larger = a.size <= b.size ? b : a
  smaller.forEach((value, key) => {
    score += value * (larger.get(key) ?? 0)
  })
  return score
}

export function useFilters() {
  const articlesStore = useArticlesStore()
  const configStore = useConfigStore()
  const readingStore = useReadingStore()

  // ── 筛选条件（reactive 使整个对象响应式，子字段变化都会触发重新计算） ──────
  const filters = reactive<FilterState>({
    keyword: '',         // 关键词（空=不过滤）
    accounts: [],        // 选中的公众号（空数组=全部）
    tags: [],            // 选中的标签（空数组=全部）
    dateFrom: '',        // 开始日期（空=不限）
    dateTo: '',          // 结束日期（空=不限）
    sortOrder: 'newest', // 默认最新优先
    groupBy: 'date',     // 默认按日期分组（最新日期在最前）
    readFilter: 'all',   // 默认显示全部
    excludeAds: true,    // 默认过滤广告标签
    semanticSearch: false,
  })

  const semanticArticles = computed(() => {
    return articlesStore.allArticles.map((article) => ({
      article,
      text: [
        article.title,
        article.summary || '',
        article.digest || '',
        article.tags?.join(' ') || '',
      ].join(' '),
    }))
  })

  // ── 筛选后的文章列表（核心计算属性） ─────────────────────────────────────────
  const filteredArticles = computed(() => {
    // 第一步：只保留配置中未被隐藏的公众号的文章
    let list = articlesStore.allArticles.filter((a) => configStore.isVisible(a.account))

    // 第二步：公众号筛选（FilterBar 中选中了具体公众号时生效）
    if (filters.accounts.length > 0) {
      list = list.filter((a) => filters.accounts.includes(a.account))
    }

    // 第三步：关键词搜索（同时匹配标题、摘要、AI 摘要，不区分大小写）
    if (filters.keyword.trim()) {
      const kw = filters.keyword.trim().toLowerCase()
      if (filters.semanticSearch) {
        const queryVector = buildSemanticVector(kw)
        list = semanticArticles.value
          .filter(({ article }) => list.some((candidate) => candidate.id === article.id))
          .map(({ article, text }) => {
            const similarity = cosineSimilarity(queryVector, buildSemanticVector(text))
            const literalBoost = article.title.toLowerCase().includes(kw) || (article.summary || '').toLowerCase().includes(kw) || article.digest.toLowerCase().includes(kw)
              ? 0.15
              : 0
            return { article, score: similarity + literalBoost }
          })
          .filter(({ score }) => score >= 0.08)
          .sort((a, b) => b.score - a.score || b.article.create_time.localeCompare(a.article.create_time))
          .map(({ article }) => article)
      } else {
        list = list.filter(
          (a) =>
            a.title.toLowerCase().includes(kw) ||
            a.digest.toLowerCase().includes(kw) ||
            (a.summary || '').toLowerCase().includes(kw),
        )
      }
    }

    // 第四步：广告过滤（默认过滤带“广告”标签的文章）
    if (filters.excludeAds) {
      list = list.filter((a) => !a.tags?.includes('广告'))
    }

    // 第五步：标签筛选（文章必须含有所有选中标签，即 AND 逻辑）
    if (filters.tags.length > 0) {
      list = list.filter((a) => filters.tags.every((t) => a.tags?.includes(t)))
    }

    // 第六步：日期范围过滤（create_time 格式为 "YYYY-MM-DD HH:MM"，字符串可直接比较）
    if (filters.dateFrom) {
      list = list.filter((a) => a.create_time >= filters.dateFrom)
    }
    if (filters.dateTo) {
      // dateTo 只有日期没有时间，补上 23:59 确保包含当天所有文章
      list = list.filter((a) => a.create_time <= filters.dateTo + ' 23:59')
    }

    // 第七步：已读/收藏状态过滤
    if (filters.readFilter === 'unread') {
      list = list.filter((a) => !readingStore.isRead(a.id))
    } else if (filters.readFilter === 'bookmarked') {
      list = list.filter((a) => readingStore.isBookmarked(a.id))
    }
    // 'all' 时不过滤

    // 第八步：排序（语义搜索开启且有关键词时保留召回排序）
    if (!(filters.semanticSearch && filters.keyword.trim())) {
      if (filters.sortOrder === 'oldest') {
        list = [...list].sort((a, b) => a.create_time.localeCompare(b.create_time))
      }
    }

    return list
  })

  // ── 分组后的文章列表（用于文章流按日期或公众号分组展示） ──────────────────
  const groupedArticles = computed(() => {
    const list = filteredArticles.value
    const groupBy: GroupBy = filters.groupBy

    // 不分组时，包装成统一格式（key/label 为空，articles 是全部）
    if (groupBy === 'none') {
      return [{ key: '', label: '', articles: list }]
    }

    // 按 key 分组（date → 取日期前 10 位；account → 取公众号名）
    const groups: Record<string, typeof list> = {}
    for (const article of list) {
      const key =
        groupBy === 'date'
          ? article.create_time.slice(0, 10)  // "YYYY-MM-DD"
          : article.account                   // 公众号名称

      if (!groups[key]) groups[key] = []
      groups[key].push(article)
    }

    // 按日期分组时倒序（最新日期在前）；按公众号分组时正序（字母序）
    return Object.entries(groups)
      .sort((a, b) => (groupBy === 'date' ? b[0].localeCompare(a[0]) : a[0].localeCompare(b[0])))
      .map(([key, articles]) => ({ key, label: key, articles }))
  })

  // ── 重置所有筛选条件 ──────────────────────────────────────────────────────
  function resetFilters() {
    filters.keyword = ''
    filters.accounts = []
    filters.tags = []
    filters.dateFrom = ''
    filters.dateTo = ''
    filters.sortOrder = 'newest'
    filters.excludeAds = true
    filters.semanticSearch = false
    // groupBy 不重置，用户通常希望保留分组偏好
  }

  /**
   * 当前激活的筛选条件数量（用于 FilterBar 上的"已筛选"徽标）。
   * readFilter 不计入（它有独立的 Tab 展示），groupBy 也不计入。
   */
  const activeFilterCount = computed(() => {
    let count = 0
    if (filters.keyword) count++
    if (filters.accounts.length) count++
    if (filters.tags.length) count++
    if (filters.excludeAds) count++
    if (filters.semanticSearch && filters.keyword.trim()) count++
    return count
  })

  return { filters, filteredArticles, groupedArticles, resetFilters, activeFilterCount }
}
