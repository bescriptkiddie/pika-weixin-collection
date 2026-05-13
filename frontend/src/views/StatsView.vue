<script setup lang="ts">
import { computed } from 'vue'
import { BarChart3, TrendingUp, Activity, Users, Loader2, AlertCircle } from 'lucide-vue-next'
import { useArticlesStore } from '@/stores/articles'

const articlesStore = useArticlesStore()

function formatDateKey(date: Date) {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

function buildRecentDateKeys(days: number) {
  return Array.from({ length: days }, (_, index) => {
    const date = new Date()
    date.setHours(0, 0, 0, 0)
    date.setDate(date.getDate() - (days - index - 1))
    return formatDateKey(date)
  })
}

const dateCounts = computed(() => {
  const counts = new Map<string, number>()
  for (const article of articlesStore.allArticles) {
    const key = article.create_time.slice(0, 10)
    counts.set(key, (counts.get(key) ?? 0) + 1)
  }
  return counts
})

const last7Keys = computed(() => buildRecentDateKeys(7))
const last14Keys = computed(() => buildRecentDateKeys(14))
const last30Keys = computed(() => buildRecentDateKeys(30))

const totalArticles7d = computed(() => last7Keys.value.reduce((sum, key) => sum + (dateCounts.value.get(key) ?? 0), 0))
const totalArticles30d = computed(() => last30Keys.value.reduce((sum, key) => sum + (dateCounts.value.get(key) ?? 0), 0))

const publishTrend = computed(() => {
  return last14Keys.value.map((key) => ({
    key,
    label: key.slice(5),
    count: dateCounts.value.get(key) ?? 0,
  }))
})

const publishTrendMax = computed(() => Math.max(...publishTrend.value.map((item) => item.count), 1))

const growthSeries = computed(() => {
  const keys = Array.from(dateCounts.value.keys()).sort().slice(-30)
  let total = 0
  return keys.map((key) => {
    total += dateCounts.value.get(key) ?? 0
    return { key, total }
  })
})

const growthPath = computed(() => {
  const points = growthSeries.value
  if (points.length === 0) return ''
  const width = 100
  const height = 36
  const max = Math.max(...points.map((point) => point.total), 1)
  return points
    .map((point, index) => {
      const x = points.length === 1 ? width / 2 : (index / (points.length - 1)) * width
      const y = height - (point.total / max) * height
      return `${index === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)}`
    })
    .join(' ')
})

const accountActivity = computed(() => {
  const stats = new Map<string, { count7: number; count30: number; days7: Set<string>; days30: Set<string> }>()
  const last7 = new Set(last7Keys.value)
  const last30 = new Set(last30Keys.value)

  for (const article of articlesStore.allArticles) {
    const day = article.create_time.slice(0, 10)
    const current = stats.get(article.account) ?? { count7: 0, count30: 0, days7: new Set<string>(), days30: new Set<string>() }
    if (last30.has(day)) {
      current.count30 += 1
      current.days30.add(day)
    }
    if (last7.has(day)) {
      current.count7 += 1
      current.days7.add(day)
    }
    stats.set(article.account, current)
  }

  return Array.from(stats.entries())
    .map(([account, stat]) => ({
      account,
      count7: stat.count7,
      count30: stat.count30,
      activeDays7: stat.days7.size,
      activeDays30: stat.days30.size,
    }))
    .filter((item) => item.count30 > 0)
    .sort((a, b) => b.count30 - a.count30 || b.count7 - a.count7)
    .slice(0, 10)
})
</script>

<template>
  <div class="app-view-shell flex h-full flex-col overflow-hidden">
    <div class="shrink-0 border-b border-[var(--color-border)] bg-[var(--color-background)]/80 px-6 py-5 backdrop-blur-sm">
      <div class="flex items-center gap-3">
        <div class="flex h-9 w-9 items-center justify-center rounded-xl bg-[var(--color-primary)]/10">
          <BarChart3 class="h-5 w-5 text-[var(--color-primary)]" />
        </div>
        <div>
          <h1 class="text-lg font-semibold text-[var(--color-foreground)]">统计图表</h1>
          <p class="text-sm text-[var(--color-muted-foreground)]">查看发文趋势、总量增长和近 7/30 天活跃度</p>
        </div>
      </div>
    </div>

    <div class="flex-1 overflow-y-auto px-6 py-6">
      <div v-if="articlesStore.loading" class="flex items-center justify-center gap-3 py-24">
        <Loader2 class="h-5 w-5 animate-spin text-[var(--color-primary)]" />
        <span class="text-sm text-[var(--color-muted-foreground)]">加载中...</span>
      </div>

      <div v-else-if="articlesStore.error" class="flex flex-col items-center justify-center gap-3 py-24">
        <AlertCircle class="h-10 w-10 text-[var(--color-destructive)]" />
        <p class="text-sm font-medium text-[var(--color-foreground)]">统计数据加载失败</p>
        <p class="text-xs text-[var(--color-muted-foreground)]">{{ articlesStore.error }}</p>
      </div>

      <div v-else class="space-y-6">
        <div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <div class="rounded-2xl border border-[var(--color-border)] bg-[var(--color-card)] p-4">
            <div class="mb-2 flex items-center gap-2 text-xs text-[var(--color-muted-foreground)]">
              <Users class="h-4 w-4 text-[var(--color-primary)]" />公众号总数
            </div>
            <p class="text-2xl font-bold text-[var(--color-foreground)]">{{ articlesStore.stats.totalAccounts }}</p>
          </div>
          <div class="rounded-2xl border border-[var(--color-border)] bg-[var(--color-card)] p-4">
            <div class="mb-2 flex items-center gap-2 text-xs text-[var(--color-muted-foreground)]">
              <BarChart3 class="h-4 w-4 text-[var(--color-primary)]" />文章总数
            </div>
            <p class="text-2xl font-bold text-[var(--color-foreground)]">{{ articlesStore.stats.totalArticles }}</p>
          </div>
          <div class="rounded-2xl border border-[var(--color-border)] bg-[var(--color-card)] p-4">
            <div class="mb-2 flex items-center gap-2 text-xs text-[var(--color-muted-foreground)]">
              <Activity class="h-4 w-4 text-emerald-500" />近 7 天发文
            </div>
            <p class="text-2xl font-bold text-[var(--color-foreground)]">{{ totalArticles7d }}</p>
          </div>
          <div class="rounded-2xl border border-[var(--color-border)] bg-[var(--color-card)] p-4">
            <div class="mb-2 flex items-center gap-2 text-xs text-[var(--color-muted-foreground)]">
              <TrendingUp class="h-4 w-4 text-orange-500" />近 30 天发文
            </div>
            <p class="text-2xl font-bold text-[var(--color-foreground)]">{{ totalArticles30d }}</p>
          </div>
        </div>

        <div class="grid gap-6 xl:grid-cols-[1.4fr_1fr]">
          <section class="rounded-2xl border border-[var(--color-border)] bg-[var(--color-card)] p-5">
            <div class="mb-4 flex items-center justify-between gap-3">
              <div>
                <h2 class="text-sm font-semibold text-[var(--color-foreground)]">公众号发文频率趋势</h2>
                <p class="text-xs text-[var(--color-muted-foreground)]">最近 14 天每日发文量</p>
              </div>
              <span class="text-xs text-[var(--color-muted-foreground)]">峰值 {{ publishTrendMax }}</span>
            </div>
            <div class="grid h-56 grid-cols-14 items-end gap-2">
              <div v-for="item in publishTrend" :key="item.key" class="flex h-full flex-col justify-end gap-2">
                <div class="flex-1 rounded-t-xl bg-[var(--color-primary)]/12 p-1 flex items-end">
                  <div class="w-full rounded-lg bg-[var(--color-primary)] transition-all" :style="{ height: `${Math.max((item.count / publishTrendMax) * 100, item.count > 0 ? 8 : 0)}%` }" />
                </div>
                <div class="text-center text-[10px] text-[var(--color-muted-foreground)]">{{ item.label.slice(5) }}</div>
                <div class="text-center text-[11px] font-medium text-[var(--color-foreground)]">{{ item.count }}</div>
              </div>
            </div>
          </section>

          <section class="rounded-2xl border border-[var(--color-border)] bg-[var(--color-card)] p-5">
            <div class="mb-4">
              <h2 class="text-sm font-semibold text-[var(--color-foreground)]">总文章增长曲线</h2>
              <p class="text-xs text-[var(--color-muted-foreground)]">最近 30 个有发文记录的日期累计总量</p>
            </div>
            <div class="rounded-xl bg-[var(--color-muted)]/35 p-4">
              <svg viewBox="0 0 100 40" class="h-44 w-full overflow-visible">
                <path d="M 0 36 H 100" stroke="currentColor" class="text-[var(--color-border)]" stroke-width="0.8" fill="none" />
                <path v-if="growthPath" :d="growthPath" stroke="currentColor" class="text-[var(--color-primary)]" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round" />
              </svg>
              <div v-if="growthSeries.length" class="mt-3 flex items-center justify-between text-xs text-[var(--color-muted-foreground)]">
                <span>{{ growthSeries[0]?.key }}</span>
                <span>{{ growthSeries[growthSeries.length - 1]?.key }}</span>
              </div>
            </div>
          </section>
        </div>

        <section class="rounded-2xl border border-[var(--color-border)] bg-[var(--color-card)] p-5">
          <div class="mb-4">
            <h2 class="text-sm font-semibold text-[var(--color-foreground)]">近 7 / 30 天活跃度</h2>
            <p class="text-xs text-[var(--color-muted-foreground)]">按近 30 天发文量排序的前 10 个公众号</p>
          </div>
          <div class="overflow-x-auto">
            <table class="min-w-full text-sm">
              <thead>
                <tr class="border-b border-[var(--color-border)] text-left text-[var(--color-muted-foreground)]">
                  <th class="py-2 pr-4 font-medium">公众号</th>
                  <th class="py-2 pr-4 font-medium">7 天发文</th>
                  <th class="py-2 pr-4 font-medium">30 天发文</th>
                  <th class="py-2 pr-4 font-medium">7 天活跃天数</th>
                  <th class="py-2 font-medium">30 天活跃天数</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in accountActivity" :key="item.account" class="border-b border-[var(--color-border)] last:border-0">
                  <td class="py-3 pr-4 font-medium text-[var(--color-foreground)]">{{ item.account }}</td>
                  <td class="py-3 pr-4 text-[var(--color-foreground)]">{{ item.count7 }}</td>
                  <td class="py-3 pr-4 text-[var(--color-foreground)]">{{ item.count30 }}</td>
                  <td class="py-3 pr-4 text-[var(--color-muted-foreground)]">{{ item.activeDays7 }}</td>
                  <td class="py-3 text-[var(--color-muted-foreground)]">{{ item.activeDays30 }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>
