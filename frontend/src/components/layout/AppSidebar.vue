<script setup lang="ts">
import { computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { Database, Settings, ScrollText, ChevronLeft, ChevronRight, Workflow, Radio, BarChart3 } from 'lucide-vue-next'
import { useArticlesStore } from '@/stores/articles'
import { useConfigStore } from '@/stores/config'
import { useContentItemsStore } from '@/stores/contentItems'
import ThemeToggle from './ThemeToggle.vue'
import FeedThemePicker from './FeedThemePicker.vue'

const props = defineProps<{
  collapsed: boolean
  selectedAccount: string
  selectedSourceType?: string
}>()

const emit = defineEmits<{
  'update:collapsed': [value: boolean]
  'update:selectedAccount': [value: string]
  'update:selectedSourceType': [value: string]
}>()

const router = useRouter()
const route = useRoute()
const articlesStore = useArticlesStore()
const configStore = useConfigStore()
const contentItemsStore = useContentItemsStore()

const navItems = [
  { name: '内容池', icon: Database, path: '/' },
  { name: '公众号', icon: Radio, path: '/feed' },
  { name: '信源', icon: Radio, path: '/sources' },
  { name: '闭环', icon: Workflow, path: '/loop' },
  { name: '统计', icon: BarChart3, path: '/stats' },
  { name: '配置', icon: Settings, path: '/config' },
  { name: '日志', icon: ScrollText, path: '/logs' },
]

const visibleAccounts = computed(() =>
  articlesStore.accounts
    .filter((a) => configStore.isVisible(a.name))
    .sort((a, b) => b.latest_update_time.localeCompare(a.latest_update_time)),
)

const sourceTypeOptions = computed(() => Object.entries(contentItemsStore.sourceTypeCounts)
  .sort((a, b) => b[1] - a[1])
  .map(([type, count]) => ({ type, count })))

const sourceTypeLabels: Record<string, string> = {
  wechat_article: '公众号',
  github_repo: 'GitHub',
  bilibili_video: 'B站视频',
  podcast_episode: '播客单集',
  podcast_feed: '播客',
  rss_feed: 'RSS',
  manual_clip: '手动收藏',
}

function sourceTypeLabel(type: string) {
  return sourceTypeLabels[type] ?? type
}

function selectAccount(name: string) {
  const newVal = props.selectedAccount === name ? '' : name
  emit('update:selectedAccount', newVal)
  if (route.path !== '/feed') router.push('/feed')
}

function selectSourceType(type: string) {
  const newVal = props.selectedSourceType === type ? '' : type
  emit('update:selectedSourceType', newVal)
  if (route.path !== '/') router.push('/')
}
</script>

<template>
  <aside
    class="app-sidebar-shell flex h-full flex-col transition-[width] duration-300 ease-out"
    :class="collapsed ? 'w-14' : 'w-56'"
  >
    <div class="relative z-[1] flex h-full min-h-0 flex-col">
      <div
        class="app-sidebar-brand"
        :class="collapsed ? 'justify-center px-2' : ''"
      >
        <div class="app-sidebar-logo">
          <Database class="h-4 w-4" />
        </div>
        <span v-if="!collapsed" class="app-sidebar-title">内容中枢</span>
      </div>

      <nav class="app-sidebar-nav space-y-1">
        <router-link
          v-for="item in navItems"
          :key="item.path"
          :to="item.path"
          class="app-sidebar-link"
          :class="[
            route.path === item.path ? 'app-sidebar-link--active' : '',
            collapsed ? 'app-sidebar-link--collapsed' : '',
          ]"
          :title="collapsed ? item.name : ''"
        >
          <component :is="item.icon" class="h-4 w-4 shrink-0" />
          <span v-if="!collapsed">{{ item.name }}</span>
        </router-link>
      </nav>

      <div v-if="!collapsed && route.path === '/'" class="app-sidebar-accounts-wrap">
        <div class="app-sidebar-section-hd">
          <span class="app-sidebar-section-label">来源类型</span>
        </div>
        <div class="app-sidebar-accounts-scroll space-y-0.5">
          <button
            type="button"
            class="app-sidebar-acct-btn"
            :class="(props.selectedSourceType || '') === '' ? 'app-sidebar-acct-btn--active' : ''"
            @click="emit('update:selectedSourceType', '')"
          >
            <span class="min-w-0 flex-1 truncate">全部</span>
            <span class="app-sidebar-acct-count">{{ contentItemsStore.items.length }}</span>
          </button>
          <button
            v-for="option in sourceTypeOptions"
            :key="option.type"
            type="button"
            class="app-sidebar-acct-btn"
            :class="props.selectedSourceType === option.type ? 'app-sidebar-acct-btn--active' : ''"
            @click="selectSourceType(option.type)"
          >
            <span class="min-w-0 flex-1 truncate">{{ sourceTypeLabel(option.type) }}</span>
            <span class="app-sidebar-acct-count">{{ option.count }}</span>
          </button>
        </div>
      </div>

      <div v-else-if="!collapsed && route.path === '/feed'" class="app-sidebar-accounts-wrap">
        <div class="app-sidebar-section-hd">
          <span class="app-sidebar-section-label">公众号</span>
        </div>
        <div class="app-sidebar-accounts-scroll space-y-0.5">
          <button
            type="button"
            class="app-sidebar-acct-btn"
            :class="selectedAccount === '' ? 'app-sidebar-acct-btn--active' : ''"
            @click="emit('update:selectedAccount', '')"
          >
            <span class="min-w-0 flex-1 truncate">全部</span>
            <span class="app-sidebar-acct-count">{{ articlesStore.stats.totalArticles }}</span>
          </button>
          <button
            v-for="acc in visibleAccounts"
            :key="acc.name"
            type="button"
            class="app-sidebar-acct-btn"
            :class="selectedAccount === acc.name ? 'app-sidebar-acct-btn--active' : ''"
            @click="selectAccount(acc.name)"
          >
            <span class="min-w-0 flex-1 truncate">{{ acc.name }}</span>
            <span class="app-sidebar-acct-count">{{ acc.article_count }}</span>
          </button>
        </div>
      </div>

      <div v-else class="app-sidebar-spacer" />

      <div
        class="app-sidebar-footer"
        :class="collapsed ? 'flex-row justify-center gap-1' : 'flex-col gap-2'"
      >
        <FeedThemePicker v-if="!collapsed" />
        <div
          class="flex w-full gap-1"
          :class="collapsed ? 'justify-center' : 'justify-between'"
        >
          <ThemeToggle v-if="!collapsed" class="app-sidebar-icon-btn" />
          <button
            type="button"
            class="app-sidebar-icon-btn"
            :title="collapsed ? '展开侧栏' : '折叠侧栏'"
            @click="emit('update:collapsed', !collapsed)"
          >
            <ChevronLeft v-if="!collapsed" class="h-4 w-4" />
            <ChevronRight v-else class="h-4 w-4" />
          </button>
          <ThemeToggle v-if="collapsed" class="app-sidebar-icon-btn" />
        </div>
      </div>
    </div>
  </aside>
</template>
