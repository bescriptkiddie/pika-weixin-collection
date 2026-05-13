<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Menu } from 'lucide-vue-next'
import AppSidebar from '@/components/layout/AppSidebar.vue'
import { useArticlesStore } from '@/stores/articles'
import { useConfigStore } from '@/stores/config'
import { useContentItemsStore } from '@/stores/contentItems'

const articlesStore = useArticlesStore()
const configStore = useConfigStore()
const contentItemsStore = useContentItemsStore()

const sidebarCollapsed = ref(false)
const mobileSidebarOpen = ref(false)
const selectedAccount = ref('')
const selectedSourceType = ref('')

onMounted(async () => {
  configStore.initTheme()
  await Promise.all([
    articlesStore.loadData(),
    contentItemsStore.loadAll(),
  ])
})
</script>

<template>
  <div class="flex h-screen overflow-hidden bg-[var(--color-background)] text-[var(--color-foreground)]">
    <div
      v-if="mobileSidebarOpen"
      class="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm md:hidden"
      @click="mobileSidebarOpen = false"
    />

    <div
      class="fixed inset-y-0 left-0 z-50 md:relative md:z-auto md:block transition-transform duration-300"
      :class="mobileSidebarOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'"
    >
      <AppSidebar
        v-model:collapsed="sidebarCollapsed"
        v-model:selectedAccount="selectedAccount"
        v-model:selectedSourceType="selectedSourceType"
        @click.stop
      />
    </div>

    <main class="flex-1 overflow-hidden flex flex-col min-w-0">
      <div class="flex md:hidden h-12 shrink-0 items-center gap-3 border-b border-[var(--color-border)] px-4">
        <button
          @click="mobileSidebarOpen = true"
          class="flex h-8 w-8 items-center justify-center rounded-lg text-[var(--color-muted-foreground)] hover:bg-[var(--color-accent)] hover:text-[var(--color-foreground)] transition-colors"
        >
          <Menu class="h-5 w-5" />
        </button>
        <span class="text-sm font-semibold text-[var(--color-foreground)]">内容中枢</span>
      </div>

      <router-view
        :selected-account="selectedAccount"
        :selected-source-type="selectedSourceType"
        @update:selectedAccount="selectedAccount = $event"
        @update:selectedSourceType="selectedSourceType = $event"
        class="flex-1 overflow-hidden"
      />
    </main>
  </div>
</template>
