<script setup lang="ts">
import { ref, computed } from 'vue'
import { Search, X, SlidersHorizontal, LayoutGrid, List, Bookmark, BookmarkCheck, Circle, Download } from 'lucide-vue-next'
import { useArticlesStore } from '@/stores/articles'
import { useReadingStore } from '@/stores/reading'
import type { FilterState, SortOrder, GroupBy, ReadFilter, ExportFormat } from '@/types'
import Dropdown from '@/components/ui/Dropdown.vue'
import DateRangePicker from '@/components/ui/DateRangePicker.vue'

const props = withDefaults(
  defineProps<{
    filters: FilterState
    activeCount: number
    viewMode: 'grid' | 'list'
    /** 文章 Feed 玻璃拟态样式（仅 FeedView 使用） */
    glass?: boolean
  }>(),
  { glass: false },
)

const emit = defineEmits<{
  'update:filters': [value: FilterState]
  'update:viewMode': [value: 'grid' | 'list']
  export: [value: ExportFormat]
  reset: []
}>()

const articlesStore = useArticlesStore()
const readingStore = useReadingStore()
const showAdvanced = ref(false)

const readTabs: { value: ReadFilter; label: string; icon: unknown }[] = [
  { value: 'all',        label: '全部',   icon: Circle },
  { value: 'unread',     label: '未读',   icon: Circle },
  { value: 'bookmarked', label: '收藏',   icon: Bookmark },
]

function update<K extends keyof FilterState>(key: K, value: FilterState[K]) {
  emit('update:filters', { ...props.filters, [key]: value })
}

function toggleAccount(name: string) {
  const accounts = props.filters.accounts.includes(name)
    ? props.filters.accounts.filter((a) => a !== name)
    : [...props.filters.accounts, name]
  update('accounts', accounts)
}

function toggleTag(tag: string) {
  const tags = props.filters.tags.includes(tag)
    ? props.filters.tags.filter((t) => t !== tag)
    : [...props.filters.tags, tag]
  update('tags', tags)
}

const sortOptions = [
  { value: 'newest' as SortOrder, label: '最新优先' },
  { value: 'oldest' as SortOrder, label: '最旧优先' },
]

const groupOptions = [
  { value: 'none' as GroupBy, label: '不分组' },
  { value: 'date' as GroupBy, label: '按日期' },
  { value: 'account' as GroupBy, label: '按公众号' },
]

const exportOptions = [
  { value: 'markdown' as ExportFormat, label: '导出 Markdown' },
  { value: 'csv' as ExportFormat, label: '导出 CSV' },
  { value: 'json' as ExportFormat, label: '导出 JSON' },
]

const exportMenuOpen = ref(false)

function handleExport(format: string) {
  emit('export', format as ExportFormat)
  exportMenuOpen.value = false
}

const activeFilters = computed(() => {
  const list: { label: string; remove: () => void }[] = []
  if (props.filters.keyword) {
    list.push({ label: `"${props.filters.keyword}"`, remove: () => update('keyword', '') })
  }
  if (props.filters.excludeAds) {
    list.push({ label: '已过滤广告', remove: () => update('excludeAds', false) })
  }
  if (props.filters.semanticSearch && props.filters.keyword.trim()) {
    list.push({ label: '语义搜索', remove: () => update('semanticSearch', false) })
  }
  props.filters.accounts.forEach((acc) => {
    list.push({ label: acc, remove: () => toggleAccount(acc) })
  })
  props.filters.tags.forEach((tag) => {
    list.push({ label: `#${tag}`, remove: () => toggleTag(tag) })
  })
  return list
})
</script>

<template>
  <div class="space-y-2.5" :class="{ 'feed-filter-glass': glass }">
    <!-- Read filter tabs -->
    <div class="flex flex-wrap items-center gap-2">
      <button
        v-for="tab in readTabs"
        :key="tab.value"
        type="button"
        @click="update('readFilter', tab.value)"
        class="relative inline-flex items-center gap-1.5 text-sm font-medium transition-colors"
        :class="glass
          ? ['feed-pill', filters.readFilter === tab.value ? 'is-active' : '']
          : [
              'rounded-lg px-3 py-1.5',
              filters.readFilter === tab.value
                ? 'bg-[var(--color-accent)] text-[var(--color-foreground)]'
                : 'text-[var(--color-muted-foreground)] hover:text-[var(--color-foreground)] hover:bg-[var(--color-accent)]/60',
            ]"
      >
        <BookmarkCheck v-if="tab.value === 'bookmarked'" class="h-3.5 w-3.5" />
        <span
          v-else-if="tab.value === 'unread' && readingStore.unreadCount > 0"
          class="inline-flex h-5 min-w-5 shrink-0 items-center justify-center rounded-full bg-[var(--color-primary)] px-1.5 text-[10px] font-bold tabular-nums leading-none text-white"
        >{{ readingStore.unreadCount > 99 ? '99+' : readingStore.unreadCount }}</span>
        {{ tab.label }}
        <span
          v-if="tab.value === 'bookmarked' && readingStore.bookmarkCount > 0"
          class="rounded-full bg-[var(--color-primary)]/15 px-1.5 py-0.5 text-[10px] font-semibold text-[var(--color-primary)]"
        >{{ readingStore.bookmarkCount }}</span>
      </button>
    </div>

    <!-- Main toolbar row -->
    <div class="flex items-center gap-2">
      <!-- Search -->
      <div class="relative flex-1 min-w-0">
        <Search class="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--color-muted-foreground)] pointer-events-none" />
        <input
          :value="filters.keyword"
          @input="update('keyword', ($event.target as HTMLInputElement).value)"
          type="text"
          placeholder="搜索标题或内容..."
          class="w-full text-sm outline-none transition-colors"
          :class="glass
            ? 'feed-glass-input'
            : 'h-9 rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] pl-9 pr-8 text-[var(--color-foreground)] placeholder-[var(--color-muted-foreground)] focus:border-[var(--color-ring)] focus:ring-1 focus:ring-[var(--color-ring)]'"
        />
        <button
          v-if="filters.keyword"
          @click="update('keyword', '')"
          class="absolute right-2.5 top-1/2 -translate-y-1/2 rounded text-[var(--color-muted-foreground)] hover:text-[var(--color-foreground)] transition-colors"
        >
          <X class="h-3.5 w-3.5" />
        </button>
      </div>

      <!-- Date range picker -->
      <DateRangePicker
        class="hidden md:block"
        :class="glass ? 'feed-glass-dd' : ''"
        :date-from="filters.dateFrom"
        :date-to="filters.dateTo"
        @update:dateFrom="update('dateFrom', $event)"
        @update:dateTo="update('dateTo', $event)"
      />

      <!-- Sort dropdown -->
      <Dropdown
        class="hidden sm:block"
        :class="glass ? 'feed-glass-dd' : ''"
        :options="sortOptions"
        :model-value="filters.sortOrder"
        @update:modelValue="update('sortOrder', $event as SortOrder)"
      />

      <!-- Group dropdown -->
      <Dropdown
        class="hidden sm:block"
        :class="glass ? 'feed-glass-dd' : ''"
        :options="groupOptions"
        :model-value="filters.groupBy"
        @update:modelValue="update('groupBy', $event as GroupBy)"
      />

      <!-- Advanced toggle -->
      <button
        type="button"
        @click="showAdvanced = !showAdvanced"
        class="shrink-0 text-sm transition-colors"
        :class="glass
          ? [
              'feed-glass-tool',
              showAdvanced || activeCount > 0 ? 'is-active' : '',
            ]
          : [
              'flex h-9 items-center gap-1.5 rounded-lg border px-3',
              showAdvanced || activeCount > 0
                ? 'border-[var(--color-primary)] bg-[var(--color-primary)]/10 text-[var(--color-primary)]'
                : 'border-[var(--color-border)] bg-[var(--color-card)] text-[var(--color-muted-foreground)] hover:bg-[var(--color-accent)] hover:text-[var(--color-foreground)]',
            ]"
        :title="showAdvanced ? '收起筛选' : '展开筛选'"
      >
        <SlidersHorizontal class="h-4 w-4" />
        <span v-if="activeCount > 0" class="text-xs font-semibold tabular-nums">{{ activeCount }}</span>
      </button>

      <!-- Export -->
      <div class="relative hidden sm:block">
        <button
          type="button"
          @click="exportMenuOpen = !exportMenuOpen"
          class="shrink-0 text-sm transition-colors"
          :class="glass
            ? ['feed-glass-tool', exportMenuOpen ? 'is-active' : '']
            : 'flex h-9 items-center gap-1.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] px-3 text-[var(--color-muted-foreground)] hover:bg-[var(--color-accent)] hover:text-[var(--color-foreground)]'"
          title="导出当前筛选结果"
        >
          <Download class="h-4 w-4" />
          <span v-if="!glass">导出</span>
        </button>
        <Transition
          enter-active-class="transition duration-100 ease-out"
          enter-from-class="opacity-0 scale-95 translate-y-[-4px]"
          enter-to-class="opacity-100 scale-100 translate-y-0"
          leave-active-class="transition duration-75 ease-in"
          leave-from-class="opacity-100 scale-100 translate-y-0"
          leave-to-class="opacity-0 scale-95 translate-y-[-4px]"
        >
          <div
            v-if="exportMenuOpen"
            class="absolute right-0 top-full z-50 mt-1.5 min-w-[10rem] overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] py-1 shadow-lg shadow-black/10"
          >
            <button
              v-for="opt in exportOptions"
              :key="opt.value"
              type="button"
              @click="handleExport(opt.value)"
              class="flex w-full items-center gap-2 px-3 py-2 text-sm text-[var(--color-muted-foreground)] transition-colors hover:bg-[var(--color-accent)] hover:text-[var(--color-foreground)]"
            >
              <Download class="h-3.5 w-3.5 shrink-0 text-[var(--color-primary)]" />
              {{ opt.label }}
            </button>
          </div>
        </Transition>
      </div>

      <!-- View mode toggle -->
      <div
        class="hidden sm:flex shrink-0"
        :class="glass ? 'feed-view-toggle' : 'rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-0.5 gap-0.5'"
      >
        <button
          type="button"
          @click="emit('update:viewMode', 'grid')"
          title="网格视图"
          :class="glass
            ? ['flex items-center justify-center transition-colors', viewMode === 'grid' ? 'is-active' : '']
            : [
                'flex h-7 w-7 items-center justify-center rounded-md transition-colors',
                viewMode === 'grid'
                  ? 'bg-[var(--color-accent)] text-[var(--color-foreground)]'
                  : 'text-[var(--color-muted-foreground)] hover:text-[var(--color-foreground)]',
              ]"
        >
          <LayoutGrid class="h-[15px] w-[15px]" />
        </button>
        <button
          type="button"
          @click="emit('update:viewMode', 'list')"
          title="列表视图"
          :class="glass
            ? ['flex items-center justify-center transition-colors', viewMode === 'list' ? 'is-active' : '']
            : [
                'flex h-7 w-7 items-center justify-center rounded-md transition-colors',
                viewMode === 'list'
                  ? 'bg-[var(--color-accent)] text-[var(--color-foreground)]'
                  : 'text-[var(--color-muted-foreground)] hover:text-[var(--color-foreground)]',
              ]"
        >
          <List class="h-[15px] w-[15px]" />
        </button>
      </div>
    </div>

    <!-- Advanced filters panel -->
    <Transition
      enter-active-class="transition duration-150 ease-out"
      enter-from-class="opacity-0 -translate-y-1"
      enter-to-class="opacity-100 translate-y-0"
      leave-active-class="transition duration-100 ease-in"
      leave-from-class="opacity-100 translate-y-0"
      leave-to-class="opacity-0 -translate-y-1"
    >
      <div
        v-if="showAdvanced"
        class="p-4 space-y-4 rounded-xl"
        :class="glass ? 'feed-glass-advanced' : 'border border-[var(--color-border)] bg-[var(--color-card)]'"
      >
        <div>
          <p class="text-[11px] font-semibold uppercase tracking-wider text-[var(--color-muted-foreground)] mb-2">内容策略</p>
          <div class="space-y-3">
            <label class="flex items-center justify-between gap-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] px-3 py-2.5 text-sm text-[var(--color-foreground)]">
              <div>
                <p class="font-medium">默认过滤广告内容</p>
                <p class="text-xs text-[var(--color-muted-foreground)] mt-0.5">隐藏带有“广告”标签的文章，可手动关闭查看全部内容。</p>
              </div>
              <button
                type="button"
                @click="update('excludeAds', !filters.excludeAds)"
                class="inline-flex h-6 w-11 items-center rounded-full px-0.5 transition-colors"
                :class="filters.excludeAds ? 'bg-[var(--color-primary)]' : 'bg-[var(--color-muted)]'"
              >
                <span
                  class="h-5 w-5 rounded-full bg-white shadow transition-transform"
                  :class="filters.excludeAds ? 'translate-x-5' : 'translate-x-0'"
                />
              </button>
            </label>

            <label class="flex items-center justify-between gap-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] px-3 py-2.5 text-sm text-[var(--color-foreground)]">
              <div>
                <p class="font-medium">启用语义搜索</p>
                <p class="text-xs text-[var(--color-muted-foreground)] mt-0.5">输入关键词时按语义相关度召回与排序，不只依赖字面匹配。</p>
              </div>
              <button
                type="button"
                @click="update('semanticSearch', !filters.semanticSearch)"
                class="inline-flex h-6 w-11 items-center rounded-full px-0.5 transition-colors"
                :class="filters.semanticSearch ? 'bg-[var(--color-primary)]' : 'bg-[var(--color-muted)]'"
              >
                <span
                  class="h-5 w-5 rounded-full bg-white shadow transition-transform"
                  :class="filters.semanticSearch ? 'translate-x-5' : 'translate-x-0'"
                />
              </button>
            </label>
          </div>
        </div>

        <!-- Account filter -->
        <div v-if="articlesStore.accounts.length">
          <p class="text-[11px] font-semibold uppercase tracking-wider text-[var(--color-muted-foreground)] mb-2">公众号</p>
          <div class="flex flex-wrap gap-1.5">
            <button
              v-for="acc in articlesStore.accounts"
              :key="acc.name"
              type="button"
              @click="toggleAccount(acc.name)"
              class="rounded-full border px-2.5 py-1 text-xs transition-colors"
              :class="
                glass
                  ? filters.accounts.includes(acc.name)
                    ? 'feed-chip-active font-medium'
                    : 'feed-chip-idle hover:border-[var(--feed-accent-soft)]/40'
                  : filters.accounts.includes(acc.name)
                    ? 'border-[var(--color-primary)] bg-[var(--color-primary)]/10 text-[var(--color-primary)] font-medium'
                    : 'border-[var(--color-border)] text-[var(--color-muted-foreground)] hover:border-[var(--color-foreground)]/20 hover:text-[var(--color-foreground)]'
              "
            >
              {{ acc.name }}
              <span class="ml-1 opacity-50">{{ acc.article_count }}</span>
            </button>
          </div>
        </div>

        <!-- Tag filter -->
        <div v-if="articlesStore.allTags.length">
          <p class="text-[11px] font-semibold uppercase tracking-wider text-[var(--color-muted-foreground)] mb-2">标签</p>
          <div class="flex flex-wrap gap-1.5">
            <button
              v-for="tag in articlesStore.allTags"
              :key="tag"
              type="button"
              @click="toggleTag(tag)"
              class="rounded-full border px-2.5 py-1 text-xs transition-colors"
              :class="
                glass
                  ? filters.tags.includes(tag)
                    ? 'feed-chip-active font-medium'
                    : 'feed-chip-idle hover:border-[var(--feed-accent-soft)]/40'
                  : filters.tags.includes(tag)
                    ? 'border-[var(--color-primary)] bg-[var(--color-primary)]/10 text-[var(--color-primary)] font-medium'
                    : 'border-[var(--color-border)] text-[var(--color-muted-foreground)] hover:border-[var(--color-foreground)]/20 hover:text-[var(--color-foreground)]'
              "
            >
              #{{ tag }}
            </button>
          </div>
        </div>

        <!-- Mobile-only: date / sort / group -->
        <div class="md:hidden space-y-2">
          <p class="text-[11px] font-semibold uppercase tracking-wider text-[var(--color-muted-foreground)]">日期范围</p>
          <DateRangePicker
            :class="glass ? 'feed-glass-dd' : ''"
            :date-from="filters.dateFrom"
            :date-to="filters.dateTo"
            @update:dateFrom="update('dateFrom', $event)"
            @update:dateTo="update('dateTo', $event)"
          />
        </div>
        <div class="sm:hidden flex gap-2">
          <Dropdown
            class="flex-1"
            :class="glass ? 'feed-glass-dd' : ''"
            :options="sortOptions"
            :model-value="filters.sortOrder"
            @update:modelValue="update('sortOrder', $event as SortOrder)"
          />
          <Dropdown
            class="flex-1"
            :class="glass ? 'feed-glass-dd' : ''"
            :options="groupOptions"
            :model-value="filters.groupBy"
            @update:modelValue="update('groupBy', $event as GroupBy)"
          />
        </div>

        <!-- Reset -->
        <div class="flex justify-end pt-1">
          <button
            @click="emit('reset')"
            class="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs text-[var(--color-muted-foreground)] hover:text-[var(--color-foreground)] hover:bg-[var(--color-accent)] transition-colors"
          >
            <X class="h-3.5 w-3.5" />
            清除全部
          </button>
        </div>
      </div>
    </Transition>

    <!-- Active filter chips -->
    <div v-if="activeFilters.length" class="flex flex-wrap gap-1.5">
      <span
        v-for="(filter, i) in activeFilters"
        :key="i"
        class="flex items-center gap-1 rounded-full bg-[var(--color-primary)]/10 border border-[var(--color-primary)]/20 px-2.5 py-0.5 text-xs text-[var(--color-primary)]"
      >
        {{ filter.label }}
        <button @click="filter.remove()" class="ml-0.5 rounded-full hover:opacity-70 transition-opacity">
          <X class="h-3 w-3" />
        </button>
      </span>
    </div>
  </div>
</template>
