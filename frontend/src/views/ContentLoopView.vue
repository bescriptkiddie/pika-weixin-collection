<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import {
  Bot,
  CheckCircle2,
  Database,
  ExternalLink,
  GitBranch,
  Loader2,
  MessageSquareText,
  PenLine,
  RefreshCw,
  Repeat2,
  Search,
  Tag,
  Workflow,
  XCircle,
} from 'lucide-vue-next'
import type { ExecutionReviewResolveResponse, KnowledgeApplyResult } from '@/types'
import { useContentItemsStore } from '@/stores/contentItems'

const contentItemsStore = useContentItemsStore()
const syncing = ref(false)
const syncingExternal = ref(false)
const projecting = ref(false)
const aiEnriching = ref(false)
const feedbackingId = ref('')
const selectedTag = ref('')
function recommendedActionBase(actionKey: string) {
  return actionKey.split(':')[0]
}

const selectedProjectedAction = ref('')

function recommendedActionKey(action: typeof recommendedProjectionActions.value[number]) {
  return action.action_key || action.action
}
const focusedProjectionItemIds = ref<string[]>([])
const focusedProjectionReason = ref('')
const showAllDownstreamLists = ref(false)
const focusedProjectionFilterMode = ref<'all' | 'ready' | 'blocked' | 'pending' | 'missing'>('all')
const focusedReviewPacketIds = ref<string[]>([])
const followUpEnabledPacketIds = ref<string[]>([])
const stages = [
  { key: 'collect', index: '01', name: '人定信息源', status: '已有基础' },
  { key: 'pool', index: '02', name: '标准内容池', status: '已落盘' },
  { key: 'knowledge', index: '03', name: '知识候选', status: '已接 execution' },
  { key: 'generation', index: '04', name: '生成链路', status: '后端已接' },
]

const activeStageKey = ref(stages[0]!.key)
const overview = computed(() => contentItemsStore.overview)
const items = computed(() => contentItemsStore.items)
const tagOverview = computed(() => contentItemsStore.tagOverview)
const loading = computed(() => contentItemsStore.loading)
const error = computed(() => contentItemsStore.error)
const latestRun = computed(() => contentItemsStore.latestRun?.run ?? null)
const lastReviewResolution = computed(() => contentItemsStore.lastReviewResolution)
const lastBatchReviewResolutions = ref<ExecutionReviewResolveResponse[]>([])
const lastReviewResolutionEntries = computed(() => {
  if (lastBatchReviewResolutions.value.length) {
    return lastBatchReviewResolutions.value
  }
  return lastReviewResolution.value ? [lastReviewResolution.value] : []
})
const primaryLastReviewResolution = computed(() => lastReviewResolutionEntries.value[lastReviewResolutionEntries.value.length - 1] ?? null)
const hasBatchReviewResolution = computed(() => lastReviewResolutionEntries.value.length > 1)
const reviewResultTitle = computed(() => hasBatchReviewResolution.value ? '最近一批人工闸门处理' : '最近一次人工闸门处理')
const reviewResultChip = computed(() => hasBatchReviewResolution.value ? `${lastReviewResolutionEntries.value.length} 项` : (primaryLastReviewResolution.value?.packet_id || ''))
const lastKnowledgeApplyResult = computed(() => contentItemsStore.lastKnowledgeApplyResult)
const lastKnowledgeApplyRun = computed(() => lastKnowledgeApplyResult.value?.run ?? null)
const lastKnowledgeApplyPayload = computed(() => lastKnowledgeApplyResult.value?.result ?? null)
const lastKnowledgeApplyRequestedCount = computed(() => (lastKnowledgeApplyPayload.value?.requested_ids.cards.length ?? 0) + (lastKnowledgeApplyPayload.value?.requested_ids.topics.length ?? 0))
const lastKnowledgeApplyAcceptedCount = computed(() => (lastKnowledgeApplyPayload.value?.accepted_ids.cards.length ?? 0) + (lastKnowledgeApplyPayload.value?.accepted_ids.topics.length ?? 0))
const lastKnowledgeApplyRejectedCount = computed(() => (lastKnowledgeApplyPayload.value?.rejected_ids.cards.length ?? 0) + (lastKnowledgeApplyPayload.value?.rejected_ids.topics.length ?? 0))

function reviewResolutionFollowUpRuns(resolution: ExecutionReviewResolveResponse) {
  if (Array.isArray(resolution.follow_up_results) && resolution.follow_up_results.length) {
    return resolution.follow_up_results.map((entry) => entry.run).filter(Boolean)
  }
  return resolution.follow_up_result?.run ? [resolution.follow_up_result.run] : []
}

function reviewResolutionLeadRun(resolution: ExecutionReviewResolveResponse) {
  const runs = reviewResolutionFollowUpRuns(resolution)
  return runs[runs.length - 1] ?? null
}

function reviewResolutionFollowUpErrorCount(resolution: ExecutionReviewResolveResponse) {
  return resolution.follow_up_errors?.length ?? 0
}

function reviewResolutionFollowUpAttemptCount(resolution: ExecutionReviewResolveResponse) {
  return reviewResolutionFollowUpRuns(resolution).length + reviewResolutionFollowUpErrorCount(resolution)
}

function reviewResolutionAttemptedFollowUp(resolution: ExecutionReviewResolveResponse) {
  return reviewResolutionFollowUpAttemptCount(resolution) > 0
}

function summarizeResolutionValues(values: string[]) {
  const counts = new Map<string, number>()
  for (const value of values) {
    if (!value) continue
    counts.set(value, (counts.get(value) || 0) + 1)
  }
  return Array.from(counts.entries())
    .map(([value, count]) => count > 1 ? `${value} ${count} 项` : value)
    .join(' · ')
}

const lastReviewKindSummary = computed(() => summarizeResolutionValues(lastReviewResolutionEntries.value.map((resolution) => reviewKindLabel(resolution.kind)).filter(Boolean)))
const lastReviewStatusSummary = computed(() => summarizeResolutionValues(lastReviewResolutionEntries.value.map((resolution) => executionStatusLabel(resolution.status)).filter(Boolean)))
const lastFollowUpRuns = computed(() => lastReviewResolutionEntries.value.flatMap((resolution) => reviewResolutionFollowUpRuns(resolution)))
const lastFollowUpRun = computed(() => lastFollowUpRuns.value[lastFollowUpRuns.value.length - 1] ?? null)
const lastFollowUpRunCount = computed(() => lastFollowUpRuns.value.length)
const lastFollowUpErrors = computed(() => lastReviewResolutionEntries.value.flatMap((resolution) => resolution.follow_up_errors ?? []))
const lastFollowUpErrorCount = computed(() => lastFollowUpErrors.value.length)
const lastResolutionAttemptedFollowUp = computed(() => lastFollowUpRunCount.value > 0 || lastFollowUpErrorCount.value > 0)
const followUpRunsForDisplay = computed(() => lastFollowUpRuns.value)
const openReviewPackets = computed(() => contentItemsStore.openReviewPackets?.review_packets ?? [])
const pendingTopicReviewPackets = computed(() => openReviewPackets.value.filter((packet: typeof openReviewPackets.value[number]) => packet.kind === 'topic_synthesis_review'))
const pendingKnowledgeReviewPackets = computed(() => openReviewPackets.value.filter((packet: typeof openReviewPackets.value[number]) => packet.kind === 'knowledge_candidates_review'))
const pendingBriefReviewPackets = computed(() => openReviewPackets.value.filter((packet: typeof openReviewPackets.value[number]) => packet.kind === 'generation_briefs_review'))
const pendingDraftReviewPackets = computed(() => openReviewPackets.value.filter((packet: typeof openReviewPackets.value[number]) => packet.kind === 'draft_review'))
const pendingGeoReviewPackets = computed(() => openReviewPackets.value.filter((packet: typeof openReviewPackets.value[number]) => packet.kind === 'geo_review'))
const highlightedReviewPacketId = ref('')
const visibleReviewPackets = computed(() => {
  if (!focusedReviewPacketIds.value.length) {
    return openReviewPackets.value
  }
  const focusedIds = new Set(focusedReviewPacketIds.value)
  return openReviewPackets.value.filter((packet: typeof openReviewPackets.value[number]) => focusedIds.has(packet.packet_id))
})

const allVisibleFollowUpEnabled = computed(() => {
  const packets = visibleReviewPackets.value.filter((packet: typeof visibleReviewPackets.value[number]) => Boolean(packet.follow_up?.action))
  if (!packets.length) return false
  return packets.every((packet: typeof packets[number]) => followUpEnabledPacketIds.value.includes(packet.packet_id))
})

const someVisibleFollowUpEnabled = computed(() => visibleReviewPackets.value.some((packet: typeof visibleReviewPackets.value[number]) => Boolean(packet.follow_up?.action) && followUpEnabledPacketIds.value.includes(packet.packet_id)))
const canResolveVisibleReviewPackets = computed(() => visibleReviewPackets.value.some((packet: typeof visibleReviewPackets.value[number]) => Boolean(packet.run_id && packet.packet_id)))
const visibleFollowUpPackets = computed(() => visibleReviewPackets.value.filter((packet: typeof visibleReviewPackets.value[number]) => Boolean(packet.follow_up?.action)))


function matchingKnowledgeReviewPackets(action: typeof recommendedProjectionActions.value[number]) {
  const rawPacketIds = 'pending_approval_packet_ids' in action && Array.isArray((action as { pending_approval_packet_ids?: unknown }).pending_approval_packet_ids)
    ? (action as { pending_approval_packet_ids?: unknown[] }).pending_approval_packet_ids ?? []
    : []
  const packetIds = rawPacketIds.map((value: unknown) => String(value)).filter(Boolean)
  if (packetIds.length) {
    const packetIdSet = new Set(packetIds)
    if (action.action === 'prepare_rewrite_brief') {
      const packetPool = [...pendingKnowledgeReviewPackets.value, ...pendingBriefReviewPackets.value, ...pendingDraftReviewPackets.value, ...pendingGeoReviewPackets.value]
      return packetPool.filter((packet: typeof packetPool[number]) => packetIdSet.has(packet.packet_id))
    }
    return pendingKnowledgeReviewPackets.value.filter((packet: typeof pendingKnowledgeReviewPackets.value[number]) => packetIdSet.has(packet.packet_id))
  }
  if (!action.pending_approval_card_ids.length) {
    return []
  }
  const cardIds = new Set(action.pending_approval_card_ids)
  return pendingKnowledgeReviewPackets.value.filter((packet: typeof pendingKnowledgeReviewPackets.value[number]) => {
    const packetCardIds = Array.isArray(packet.preview?.details?.card_ids)
      ? packet.preview?.details?.card_ids.map((value: unknown) => String(value))
      : []
    return packetCardIds.some((cardId: string) => cardIds.has(cardId))
  })
}

function matchingTopicReviewPackets(action: typeof recommendedProjectionActions.value[number]) {
  if (action.action !== 'build_topic_synthesis') {
    return []
  }
  const rawPacketIds = Array.isArray(action.pending_approval_packet_ids)
    ? action.pending_approval_packet_ids
    : []
  const packetIds = rawPacketIds.map((value: unknown) => String(value)).filter(Boolean)
  if (!packetIds.length) {
    return []
  }
  const packetIdSet = new Set(packetIds)
  return pendingTopicReviewPackets.value.filter((packet: typeof pendingTopicReviewPackets.value[number]) => packetIdSet.has(packet.packet_id))
}

function matchingActionReviewPackets(action: typeof recommendedProjectionActions.value[number]) {
  if (action.action === 'build_topic_synthesis') {
    return matchingTopicReviewPackets(action)
  }
  return matchingKnowledgeReviewPackets(action)
}

function activeActionReviewPackets(action: typeof recommendedProjectionActions.value[number]) {
  return scopedActionReviewPackets(action)
}

function firstMatchingActionReviewPacketId(action: typeof recommendedProjectionActions.value[number]) {
  return activeActionReviewPackets(action)[0]?.packet_id || ''
}

function matchingActionReviewPacketIds(action: typeof recommendedProjectionActions.value[number]) {
  return activeActionReviewPackets(action).map((packet: typeof openReviewPackets.value[number]) => packet.packet_id)
}

function matchingActionReviewPacketCount(action: typeof recommendedProjectionActions.value[number]) {
  return activeActionReviewPackets(action).length
}

function hasMatchingActionReviewPackets(action: typeof recommendedProjectionActions.value[number]) {
  return matchingActionReviewPacketCount(action) > 0
}

function hasSingleMatchingActionReviewPacket(action: typeof recommendedProjectionActions.value[number]) {
  return matchingActionReviewPacketCount(action) === 1
}

function actionFollowUpEnabled(action: typeof recommendedProjectionActions.value[number]) {
  const packets = activeActionReviewPackets(action)
  if (!packets.length) return false
  return packets.every((packet: typeof packets[number]) => Boolean(packet.follow_up?.action))
}

async function approveSingleMatchingActionReviewPacket(action: typeof recommendedProjectionActions.value[number]) {
  const packet = activeActionReviewPackets(action)[0]
  if (!packet?.run_id || !packet.packet_id) return
  lastBatchReviewResolutions.value = []
  const continueAfterResolve = Boolean(packet.follow_up?.action)
  await contentItemsStore.resolveReviewPacket(packet.run_id, packet.packet_id, 'approved', continueAfterResolve)
  syncProjectionFocusState()
}

async function approveMatchingActionReviewPackets(action: typeof recommendedProjectionActions.value[number]) {
  const packets = activeActionReviewPackets(action)
  const results: ExecutionReviewResolveResponse[] = []
  for (const packet of packets) {
    if (!packet.run_id || !packet.packet_id) continue
    const continueAfterResolve = Boolean(packet.follow_up?.action)
    const result = await contentItemsStore.resolveReviewPacket(packet.run_id, packet.packet_id, 'approved', continueAfterResolve)
    results.push(result)
  }
  lastBatchReviewResolutions.value = results
  syncProjectionFocusState()
}

const feedbackProjection = computed(() => contentItemsStore.feedbackProjection)
const knowledgeCandidates = computed(() => contentItemsStore.knowledgeCandidates?.cards ?? [])
const topicSynthesisCandidates = computed(() => contentItemsStore.knowledgeCandidates?.topics ?? [])
const nonTopicKnowledgeCandidates = computed(() =>
  knowledgeCandidates.value.filter((row: Record<string, unknown>) => String(row.projected_action || '') !== 'build_topic_synthesis')
)
const generationBriefs = computed(() => contentItemsStore.generationBriefs?.briefs ?? [])
const generationDrafts = computed(() => contentItemsStore.generationDrafts?.drafts ?? [])
const geoVariants = computed(() => contentItemsStore.geoVariants?.variants ?? [])
const filteredItems = computed(() => {
  let next = items.value
  if (selectedTag.value) {
    next = next.filter((item: typeof items.value[number]) => item.tags?.includes(selectedTag.value))
  }
  if (selectedProjectedAction.value) {
    const selectedEntry = selectedProjectedActionEntry.value
    if (selectedEntry?.item_ids?.length) {
      const selectedIds = new Set(selectedEntry.item_ids.map((value: string) => String(value)).filter(Boolean))
      next = next.filter((item: typeof items.value[number]) => selectedIds.has(String(item.id || '')))
    } else {
      next = next.filter((item: typeof items.value[number]) => item.projected_action === recommendedActionBase(selectedProjectedAction.value))
    }
  }
  if (focusedProjectionItemIds.value.length) {
    const focusedIds = new Set(focusedProjectionItemIds.value)
    next = next.filter((item: typeof items.value[number]) => focusedIds.has(String(item.id || '')))
  }
  return next
})
const tagBreakdown = computed(() => Object.entries(tagOverview.value?.tag_counts ?? overview.value?.tag_counts ?? {}))
const positiveProjectionRules = computed(() => feedbackProjection.value?.top_positive ?? [])
const negativeProjectionRules = computed(() => feedbackProjection.value?.top_negative ?? [])
const actionProjectionRules = computed(() => feedbackProjection.value?.top_actions ?? [])
const recommendedProjectionActions = computed(() => feedbackProjection.value?.recommended_actions ?? [])
const scopedProjectedItems = computed(() => {
  const source = hasActiveFilter.value ? filteredItems.value : items.value
  return [...source].sort((left: typeof items.value[number], right: typeof items.value[number]) => {
    const leftScore = Number(left.projected_score ?? left.score ?? 0)
    const rightScore = Number(right.projected_score ?? right.score ?? 0)
    return rightScore - leftScore
  })
})

const scopedTopProjectionItems = computed(() => scopedProjectedItems.value.slice(0, 5))
const scopedSummaryProjectionItems = computed(() => scopedProjectedItems.value.slice(0, 5).map((item: typeof items.value[number]) => ({
  id: String(item.id || ''),
  title: String(item.title || ''),
  source_name: String(item.source_name || item.source_id || ''),
  projected_score: Number(item.projected_score ?? item.score ?? 0),
  feedback_projection_delta: Number(item.feedback_projection_delta ?? 0),
  projected_action: String(item.projected_action || ''),
  projected_action_label: String(item.projected_action_label || ''),
  projected_action_reason: String(item.projected_action_reason || ''),
})))
const selectedProjectedActionEntry = computed(() => recommendedProjectionActions.value.find((row: typeof recommendedProjectionActions.value[number]) => recommendedActionKey(row) === selectedProjectedAction.value) ?? null)
const selectedProjectedActionLabel = computed(() => {
  const action = selectedProjectedActionEntry.value
  if (!action) return ''
  if (action.execution_kind === 'build_generation_draft') return '准备生成草稿'
  if (action.execution_kind === 'build_geo_variants') return '准备生成 GEO 变体'
  return action.label || ''
})

function missingFocusLabel(action: typeof recommendedProjectionActions.value[number] | null) {
  if (action?.fallback_execution_kind === 'ai_enrich') {
    return '待补标签项'
  }
  return '待生成项'
}

function missingFocusNotice(action: typeof recommendedProjectionActions.value[number] | null) {
  if (action?.fallback_execution_kind === 'ai_enrich') {
    return '当前聚焦的是待补标签条目，优先补 AI 分类总结。'
  }
  return '当前聚焦的是待生成条目，优先补齐上游候选。'
}

function missingFocusBlockedLabel(action: typeof recommendedProjectionActions.value[number] | null) {
  if (action?.fallback_execution_kind === 'ai_enrich') {
    return '待补标签阻塞'
  }
  return '待生成阻塞'
}

function missingFocusDisabledReason(action: typeof recommendedProjectionActions.value[number] | null, target: 'knowledge' | 'topic' | 'apply' | 'brief' | 'generation') {
  if (action?.fallback_execution_kind === 'ai_enrich') {
    if (target === 'topic') {
      return '待补标签条目需要先补 AI 分类总结后再生成主题综合'
    }
    return target === 'apply'
      ? '待补标签条目需要先补 AI 分类总结后再入库'
      : '待补标签条目需要先补 AI 分类总结'
  }
  if (target === 'knowledge') {
    return '待生成条目需要先补齐知识候选'
  }
  if (target === 'topic') {
    return '待生成条目需要先补齐知识候选，再生成主题综合'
  }
  return target === 'apply'
    ? '待生成条目需要先补齐候选后再入库'
    : '待生成条目需要先补齐知识候选'
}

function pendingFocusLabel(action: typeof recommendedProjectionActions.value[number] | null) {
  const explicitLabel = String(action?.pending_approval_label || '')
  if (explicitLabel) {
    return explicitLabel
  }
  if (action?.action === 'build_topic_synthesis') {
    return '待审批主题综合'
  }
  if (action?.execution_kind === 'build_geo_variants') {
    return '待审批 GEO'
  }
  if (action?.execution_kind === 'build_generation_draft') {
    return '待审批草稿'
  }
  if (action?.action === 'prepare_rewrite_brief') {
    return '待审批写作提纲'
  }
  return '待审批知识候选'
}

function pendingPacketKindsForLabel(label: string) {
  const mapping: Record<string, string[]> = {
    待审批知识候选: ['knowledge_candidates_review'],
    待审批主题综合: ['topic_synthesis_review'],
    待审批写作提纲: ['generation_briefs_review'],
    待审批草稿: ['draft_review'],
    待审批GEO: ['geo_review'],
    '待审批 GEO': ['geo_review'],
  }
  return mapping[label] ?? []
}

function focusedPendingReasonLabelForAction(action: typeof recommendedProjectionActions.value[number] | null) {
  if (!action) return ''
  if (selectedProjectedAction.value !== recommendedActionKey(action)) return ''
  return focusedProjectionReasonLabel.value.startsWith('待审批') ? focusedProjectionReasonLabel.value : ''
}

function currentPendingLabelForAction(action: typeof recommendedProjectionActions.value[number] | null) {
  return focusedPendingReasonLabelForAction(action) || pendingFocusLabel(action)
}

function scopedActionReviewPackets(action: typeof recommendedProjectionActions.value[number]) {
  const packets = matchingActionReviewPackets(action)
  if (!packets.length) return packets
  if (selectedProjectedAction.value !== recommendedActionKey(action)) {
    return packets
  }
  if (focusedReviewPacketIds.value.length) {
    const focusedIds = new Set(focusedReviewPacketIds.value)
    const focusedPackets = packets.filter((packet: typeof packets[number]) => focusedIds.has(packet.packet_id))
    if (focusedPackets.length) {
      return focusedPackets
    }
  }
  const focusedLabel = focusedPendingReasonLabelForAction(action)
  if (!focusedLabel || focusedLabel === '待审批生成结果') {
    return packets
  }
  const kinds = new Set(pendingPacketKindsForLabel(focusedLabel))
  if (!kinds.size) {
    return packets
  }
  const scopedPackets = packets.filter((packet: typeof packets[number]) => kinds.has(String(packet.kind || '')))
  return scopedPackets.length ? scopedPackets : packets
}

function pendingBlockedLabel(action: typeof recommendedProjectionActions.value[number] | null) {
  const label = currentPendingLabelForAction(action)
  if (label === '待审批生成结果') {
    return '待审批结果阻塞'
  }
  if (label === '待审批主题综合') {
    return '待审批主题阻塞'
  }
  if (label === '待审批写作提纲') {
    return '待审批提纲阻塞'
  }
  if (label === '待审批知识候选') {
    return '待审批知识阻塞'
  }
  return `${label}阻塞`
}

function pendingPacketLabel(action: typeof recommendedProjectionActions.value[number] | null, count: number) {
  const label = currentPendingLabelForAction(action)
  const baseLabel = label === '待审批生成结果'
    ? '待审批结果包'
    : label.replace(/^待审批/, '待审批') + '包'
  return count > 1 ? `${count} 个${baseLabel}` : baseLabel
}

function pendingFocusDisabledReason(action: typeof recommendedProjectionActions.value[number] | null, target: 'knowledge' | 'topic' | 'apply' | 'generation') {
  const label = currentPendingLabelForAction(action)
  if (target === 'topic') {
    if (label === '待审批生成结果') {
      return '待审批生成结果需要先在人工闸门中逐项处理后再继续'
    }
    return `${label}需要先在人工闸门中处理`
  }
  if (target === 'apply') {
    if (label === '待审批生成结果') {
      return '待审批生成结果需要先在人工闸门中逐项处理后再入库'
    }
    if (label === '待审批主题综合') {
      return '待审批主题综合需要先批准后再入库'
    }
    if (label === '待审批知识候选') {
      return '待审批知识候选需要先批准后再入库'
    }
    return `${label}需要先处理后再入库`
  }
  if (label === '待审批生成结果') {
    return '待审批生成结果需要先在人工闸门中逐项处理后再继续'
  }
  if (label === '待审批主题综合') {
    return '待审批主题综合需要先批准后再继续'
  }
  if (label === '待审批 GEO') {
    return target === 'generation'
      ? '待审批 GEO 需要先批准后再继续'
      : '待审批 GEO 需要先在人工闸门中处理'
  }
  if (label === '待审批草稿') {
    return target === 'generation'
      ? '待审批草稿需要先批准后再继续'
      : '待审批草稿需要先在人工闸门中处理'
  }
  if (label === '待审批写作提纲') {
    return target === 'generation'
      ? '待审批写作提纲需要先批准后再继续'
      : '待审批写作提纲需要先在人工闸门中处理'
  }
  if (label === '待审批知识候选') {
    if (target === 'knowledge') {
      return '待审批知识候选需要先在人工闸门中处理'
    }
    return '待审批知识候选需要先批准后再生成写作提纲'
  }
  if (action?.action === 'build_topic_synthesis') {
    return '待审批主题综合需要先批准后再继续'
  }
  if (action?.execution_kind === 'build_geo_variants') {
    return '待审批 GEO 需要先批准后再继续'
  }
  if (action?.execution_kind === 'build_generation_draft') {
    return '待审批草稿需要先批准后再继续'
  }
  if (action?.action === 'prepare_rewrite_brief') {
    return target === 'generation'
      ? '待审批写作提纲需要先批准后再继续'
      : '待审批写作提纲需要先在人工闸门中处理'
  }
  if (target === 'knowledge') {
    return '待审批知识候选需要先在人工闸门中处理'
  }
  return '待审批知识候选需要先批准后再生成写作提纲'
}

function currentPendingItemIdsForAction(action: typeof recommendedProjectionActions.value[number]) {
  const focusedLabel = focusedPendingReasonLabelForAction(action)
  if (!focusedLabel || focusedLabel === '待审批生成结果') {
    return Array.isArray(action.pending_approval_item_ids)
      ? action.pending_approval_item_ids.map((value: unknown) => String(value)).filter(Boolean)
      : []
  }
  return Object.entries(action.blocked_reason_by_item)
    .filter(([, reason]) => String(reason) === focusedLabel)
    .map(([itemId]) => itemId)
    .filter(Boolean)
}

function currentPendingItemsForAction(action: typeof recommendedProjectionActions.value[number]) {
  const itemIds = currentPendingItemIdsForAction(action)
  if (!itemIds.length) {
    return {
      count: 0,
      sampleTitles: [] as string[],
    }
  }
  const focusedLabel = focusedPendingReasonLabelForAction(action)
  if (!focusedLabel || focusedLabel === '待审批生成结果') {
    const sampleTitles = Array.isArray(action.pending_approval_sample_titles)
      ? action.pending_approval_sample_titles.map((value: unknown) => String(value)).filter(Boolean)
      : []
    return {
      count: Number(action.pending_approval_count || 0),
      sampleTitles,
    }
  }
  const titleByItemId = new Map(
    items.value.map((item: typeof items.value[number]) => [String(item.id || ''), String(item.title || '')]),
  )
  const sampleTitles = itemIds
    .map((itemId) => titleByItemId.get(itemId) || '')
    .filter(Boolean)
    .slice(0, 3)
  return {
    count: itemIds.length,
    sampleTitles,
  }
}


function pendingFollowUpLabel(action: typeof recommendedProjectionActions.value[number] | null) {
  const label = currentPendingLabelForAction(action)
  if (label === '待审批生成结果') {
    return '批准后继续链路'
  }
  if (label === '待审批主题综合') {
    return '批准主题后继续'
  }
  if (label === '待审批 GEO') {
    return '批准 GEO 后继续'
  }
  if (label === '待审批草稿') {
    return '批准草稿后继续'
  }
  if (label === '待审批写作提纲') {
    return '批准提纲后继续'
  }
  return '批准知识后继续'
}

function pendingFocusNotice(action: typeof recommendedProjectionActions.value[number] | null) {
  const label = currentPendingLabelForAction(action)
  if (label === '待审批生成结果') {
    return '当前聚焦的是待审批生成结果，优先去人工闸门逐项处理。'
  }
  if (label === '待审批主题综合') {
    return '当前聚焦的是待审批主题综合，优先去人工闸门处理。'
  }
  if (label === '待审批 GEO') {
    return '当前聚焦的是待审批 GEO，优先去人工闸门处理。'
  }
  if (label === '待审批草稿') {
    return '当前聚焦的是待审批草稿，优先去人工闸门处理。'
  }
  if (label === '待审批写作提纲') {
    return '当前聚焦的是待审批写作提纲，优先去人工闸门处理。'
  }
  return '当前聚焦的是待审批知识候选，优先去人工闸门处理。'
}

function directApproveActionLabel(action: typeof recommendedProjectionActions.value[number]) {
  return actionFollowUpEnabled(action) ? pendingFollowUpLabel(action) : '批准并结束'
}

function batchApproveActionLabel(action: typeof recommendedProjectionActions.value[number]) {
  const count = matchingActionReviewPacketCount(action)
  if (actionFollowUpEnabled(action)) {
    return `批量批准 ${pendingPacketLabel(action, count)}`
  }
  return `批量批准 ${count} 项`
}

function missingFocusAction(action: typeof recommendedProjectionActions.value[number] | null) {
  if (!action) return null
  if (selectedProjectedAction.value !== recommendedActionKey(action)) return null
  const reasonLabel = focusedProjectionReasonLabel.value
  if (projectionReasonMode(reasonLabel) === 'missing') {
    return action
  }
  if (focusedProjectionFilterMode.value === 'missing') {
    return action
  }
  return null
}

function blockedFocusAction(action: typeof recommendedProjectionActions.value[number] | null) {
  if (!action) return null
  if (selectedProjectedAction.value !== recommendedActionKey(action)) return null
  if (focusedProjectionReasonLabel.value && projectionReasonMode(focusedProjectionReasonLabel.value) === 'blocked') {
    return action
  }
  if (focusedProjectionFilterMode.value === 'blocked') {
    return action
  }
  return null
}

function pendingFocusAction(action: typeof recommendedProjectionActions.value[number] | null) {
  if (!action) return null
  const reasonLabel = focusedProjectionReasonLabel.value.startsWith('待审批') ? focusedProjectionReasonLabel.value : ''
  const label = reasonLabel || (focusedProjectionFilterMode.value === 'pending' ? currentPendingLabelForAction(action) : '')
  if (!label) return null
  return {
    ...action,
    pending_approval_label: label,
  }
}

const focusedProjectionFilterLabel = computed(() => {
  if (focusedProjectionReasonLabel.value.startsWith('待审批')) {
    return `${focusedProjectionReasonLabel.value}焦点`
  }
  if (focusedProjectionReasonLabel.value) {
    return `${focusedProjectionReasonLabel.value}焦点`
  }
  if (focusedProjectionFilterMode.value === 'ready') return '可执行项焦点'
  if (focusedProjectionFilterMode.value === 'blocked') return '阻塞项焦点'
  if (focusedProjectionFilterMode.value === 'pending') return `${currentPendingLabelForAction(selectedProjectedActionEntry.value)}焦点`
  if (focusedProjectionFilterMode.value === 'missing') return `${missingFocusLabel(selectedProjectedActionEntry.value)}焦点`
  return ''
})
const focusedProjectionReasonLabel = computed(() => focusedProjectionReason.value || '')
const recentItemsTitle = computed(() => {
  if (selectedTag.value && selectedProjectedActionLabel.value) {
    return `「${selectedTag.value}」· ${selectedProjectedActionLabel.value}`
  }
  if (selectedTag.value) {
    return `「${selectedTag.value}」候选素材`
  }
  if (selectedProjectedActionLabel.value) {
    if (focusedProjectionReasonLabel.value) return `${selectedProjectedActionLabel.value} · ${focusedProjectionReasonLabel.value}`
    if (focusedProjectionFilterMode.value === 'ready') return `${selectedProjectedActionLabel.value} · 可执行项`
    if (focusedProjectionFilterMode.value === 'blocked') return `${selectedProjectedActionLabel.value} · 阻塞项`
    if (focusedProjectionFilterMode.value === 'pending') return `${selectedProjectedActionLabel.value} · ${currentPendingLabelForAction(selectedProjectedActionEntry.value)}`
    if (focusedProjectionFilterMode.value === 'missing') return `${selectedProjectedActionLabel.value} · ${missingFocusLabel(selectedProjectedActionEntry.value)}`
    return selectedProjectedActionLabel.value
  }
  return '最近候选素材'
})
const selectedFilteredItemIds = computed(() => filteredItems.value.map((item: typeof filteredItems.value[number]) => String(item.id || '')).filter(Boolean))
const selectedFilteredKnowledgeCardIds = computed(() => {
  const itemIds = new Set(selectedFilteredItemIds.value)
  return knowledgeCandidates.value
    .filter((card: Record<string, unknown>) => {
      const status = String(card.status || '')
      return itemIds.has(String(card.source_item_id || '')) && (status === 'approved' || status === 'applied')
    })
    .map((card: Record<string, unknown>) => String(card.id || ''))
    .filter(Boolean)
})
const selectedFilteredTopicIds = computed(() => {
  const itemIds = new Set(selectedFilteredItemIds.value)
  return topicSynthesisCandidates.value
    .filter((topic: Record<string, unknown>) => {
      const status = String(topic.status || '')
      if (status !== 'approved' && status !== 'applied') return false
      const sourceItemIds = Array.isArray(topic.source_item_ids)
        ? topic.source_item_ids.map((value: unknown) => String(value)).filter(Boolean)
        : []
      const fallbackSourceItemId = String(topic.source_item_id || '')
      if (fallbackSourceItemId) sourceItemIds.push(fallbackSourceItemId)
      return sourceItemIds.some((itemId: string) => itemIds.has(itemId))
    })
    .map((topic: Record<string, unknown>) => String(topic.id || ''))
    .filter(Boolean)
})
const hasActiveFilter = computed(() => Boolean(selectedTag.value || selectedProjectedAction.value))
const useScopedDownstreamLists = computed(() => hasActiveFilter.value && !showAllDownstreamLists.value)
const downstreamScopeLabel = computed(() => useScopedDownstreamLists.value ? '当前范围' : '全量结果')
const selectedFilteredBriefIds = computed(() => {
  const knowledgeCardIds = new Set(selectedFilteredKnowledgeCardIds.value)
  return generationBriefs.value
    .filter((brief: Record<string, unknown>) => knowledgeCardIds.has(String(brief.knowledge_card_id || '')))
    .map((brief: Record<string, unknown>) => String(brief.id || ''))
    .filter(Boolean)
})
const selectedFilteredDraftIds = computed(() => {
  const briefIds = new Set(selectedFilteredBriefIds.value)
  return generationDrafts.value
    .filter((draft: Record<string, unknown>) => briefIds.has(String(draft.brief_id || '')))
    .map((draft: Record<string, unknown>) => String(draft.id || ''))
    .filter(Boolean)
})
const focusedProjectionItemIdSet = computed(() => new Set(focusedProjectionItemIds.value))
const focusedProjectionKnowledgeCardIdSet = computed(() => new Set(selectedFilteredKnowledgeCardIds.value))
const focusedProjectionBriefIdSet = computed(() => new Set(selectedFilteredBriefIds.value))
const focusedProjectionDraftIdSet = computed(() => new Set(selectedFilteredDraftIds.value))

const scopedKnowledgeCandidates = computed(() => {
  if (!hasActiveFilter.value) return nonTopicKnowledgeCandidates.value
  const itemIds = new Set(selectedFilteredItemIds.value)
  return nonTopicKnowledgeCandidates.value.filter((card: Record<string, unknown>) => itemIds.has(String(card.source_item_id || '')))
})
const scopedTopicSynthesisCandidates = computed(() => {
  if (!hasActiveFilter.value) return topicSynthesisCandidates.value
  const itemIds = new Set(selectedFilteredItemIds.value)
  return topicSynthesisCandidates.value.filter((topic: Record<string, unknown>) => {
    const sourceItemIds = Array.isArray(topic.source_item_ids)
      ? topic.source_item_ids.map((value: unknown) => String(value)).filter(Boolean)
      : []
    const fallbackSourceItemId = String(topic.source_item_id || '')
    if (fallbackSourceItemId) sourceItemIds.push(fallbackSourceItemId)
    return sourceItemIds.some((itemId: string) => itemIds.has(itemId))
  })
})
const scopedGenerationBriefs = computed(() => {
  if (!hasActiveFilter.value) return generationBriefs.value
  const knowledgeCardIds = new Set(selectedFilteredKnowledgeCardIds.value)
  return generationBriefs.value.filter((brief: Record<string, unknown>) => knowledgeCardIds.has(String(brief.knowledge_card_id || '')))
})
const scopedGenerationDrafts = computed(() => {
  if (!hasActiveFilter.value) return generationDrafts.value
  const briefIds = new Set(selectedFilteredBriefIds.value)
  return generationDrafts.value.filter((draft: Record<string, unknown>) => briefIds.has(String(draft.brief_id || '')))
})
const scopedGeoVariants = computed(() => {
  if (!hasActiveFilter.value) return geoVariants.value
  const draftIds = new Set(selectedFilteredDraftIds.value)
  return geoVariants.value.filter((geo: Record<string, unknown>) => draftIds.has(String(geo.draft_id || '')))
})
const displayKnowledgeCandidates = computed(() => useScopedDownstreamLists.value ? scopedKnowledgeCandidates.value : nonTopicKnowledgeCandidates.value)
const displayTopicSynthesisCandidates = computed(() => useScopedDownstreamLists.value ? scopedTopicSynthesisCandidates.value : topicSynthesisCandidates.value)
const displayGenerationBriefs = computed(() => useScopedDownstreamLists.value ? scopedGenerationBriefs.value : generationBriefs.value)
const displayGenerationDrafts = computed(() => useScopedDownstreamLists.value ? scopedGenerationDrafts.value : generationDrafts.value)
const displayGeoVariants = computed(() => useScopedDownstreamLists.value ? scopedGeoVariants.value : geoVariants.value)
const hasScopedItems = computed(() => selectedFilteredItemIds.value.length > 0)
const hasScopedKnowledgeCards = computed(() => selectedFilteredKnowledgeCardIds.value.length > 0)
const hasScopedTopics = computed(() => selectedFilteredTopicIds.value.length > 0)
const workflowHint = computed(() => {
  const scopeText = hasActiveFilter.value ? `当前筛选内容项 ${selectedFilteredItemIds.value.length} 条，知识卡片 ${selectedFilteredKnowledgeCardIds.value.length} 条。` : ''
  const currentAction = selectedProjectedActionEntry.value?.action || recommendedActionBase(selectedProjectedAction.value)
  const pendingAction = pendingFocusAction(selectedProjectedActionEntry.value)
  if (pendingAction) {
    return `${scopeText}${pendingFocusDisabledReason(pendingAction, currentAction === 'build_topic_synthesis' ? 'topic' : currentAction === 'build_knowledge_candidate' ? 'knowledge' : currentAction === 'prepare_rewrite_brief' ? 'generation' : 'apply')}`.trim()
  }
  const missingAction = missingFocusAction(selectedProjectedActionEntry.value)
  if (missingAction) {
    return `${scopeText}${missingFocusDisabledReason(missingAction, currentAction === 'build_topic_synthesis' ? 'topic' : currentAction === 'build_knowledge_candidate' ? 'knowledge' : currentAction === 'prepare_rewrite_brief' ? 'generation' : 'apply')}`.trim()
  }
  const blockedAction = blockedFocusAction(selectedProjectedActionEntry.value)
  if (blockedAction) {
    return `${scopeText}${focusedProjectionReasonLabel.value ? `当前聚焦的是${focusedProjectionReasonLabel.value}条目，先处理阻塞后再继续。` : '当前聚焦的是阻塞条目，先处理阻塞后再继续。'}`.trim()
  }
  switch (currentAction) {
    case 'build_knowledge_candidate':
      return `${scopeText}当前建议先生成知识候选。`.trim()
    case 'build_topic_synthesis':
      return `${scopeText}当前建议先生成知识候选，再进入主题综合。`.trim()
    case 'prepare_rewrite_brief':
      if (focusedProjectionReasonLabel.value === '已生成 GEO 变体') {
        return `${scopeText}当前范围已完成 GEO 变体。`.trim()
      }
      if (selectedProjectedActionEntry.value?.execution_kind === 'build_generation_draft') {
        return `${scopeText}${focusedProjectionFilterMode.value === 'ready' ? '当前范围已生成写作提纲，可继续生成草稿。' : '当前建议优先生成草稿。'}`.trim()
      }
      if (selectedProjectedActionEntry.value?.execution_kind === 'build_geo_variants') {
        return `${scopeText}${focusedProjectionFilterMode.value === 'ready' ? '当前范围已生成草稿，可继续生成 GEO 变体。' : '当前建议优先生成 GEO 变体。'}`.trim()
      }
      return `${scopeText}当前建议优先生成写作提纲。`.trim()
    case 'lower_priority':
      return `${scopeText}当前建议先降低优先级，暂不推进生成。`.trim()
    case 'drop_from_pipeline':
      return `${scopeText}当前建议暂时移出后续链路。`.trim()
    default:
      return scopeText || '前端可触发'
  }
})


const scopedListScopeSummary = computed(() => {
  if (!hasActiveFilter.value) return ''
  const parts: string[] = []
  if (selectedProjectedActionLabel.value) parts.push(`动作 ${selectedProjectedActionLabel.value}`)
  if (selectedTag.value) parts.push(`标签 ${selectedTag.value}`)
  if (focusedProjectionFilterLabel.value) parts.push(`焦点 ${focusedProjectionFilterLabel.value}`)
  if (focusedProjectionReasonLabel.value) parts.push(`原因 ${focusedProjectionReasonLabel.value}`)
  return parts.join(' · ')
})
const workflowFocusNotice = computed(() => {
  if (focusedProjectionReasonLabel.value) {
    if (focusedProjectionReasonLabel.value.startsWith('待审批')) {
      return `当前聚焦的是${focusedProjectionReasonLabel.value}，优先去人工闸门处理。`
    }
    if (projectionReasonMode(focusedProjectionReasonLabel.value) === 'missing') {
      return missingFocusNotice(selectedProjectedActionEntry.value)
    }
    return `当前聚焦原因：${focusedProjectionReasonLabel.value}`
  }
  if (focusedProjectionFilterMode.value === 'pending') {
    return pendingFocusNotice(selectedProjectedActionEntry.value)
  }
  if (focusedProjectionFilterMode.value === 'missing') {
    return missingFocusNotice(selectedProjectedActionEntry.value)
  }
  if (focusedProjectionFilterMode.value === 'blocked') {
    return '当前聚焦的是阻塞条目，先处理阻塞再继续执行。'
  }
  if (focusedProjectionFilterMode.value === 'ready') {
    return '当前聚焦的是本次会实际执行的条目。'
  }
  return ''
})

const workflowKnowledgeDisabledReason = computed(() => {
  const pendingAction = pendingFocusAction(selectedProjectedActionEntry.value)
  if (pendingAction) {
    return pendingFocusDisabledReason(pendingAction, 'knowledge')
  }
  if (focusedProjectionReasonLabel.value === '已存在知识沉淀') {
    return '这些条目已沉淀到知识库，无需重复生成知识候选'
  }
  return ''
})
const workflowTopicDisabledReason = computed(() => {
  const pendingAction = pendingFocusAction(selectedProjectedActionEntry.value)
  if (pendingAction) {
    return pendingFocusDisabledReason(pendingAction, 'topic')
  }
  if (focusedProjectionReasonLabel.value === '缺少主题标签') {
    return '缺少主题标签的条目需要先补标签或跑 AI 分类总结'
  }
  if (focusedProjectionReasonLabel.value === '已存在主题沉淀') {
    return '这些条目对应主题已沉淀，无需重复生成主题综合'
  }
  return ''
})

const workflowApplyDisabledReason = computed(() => {
  const pendingAction = pendingFocusAction(selectedProjectedActionEntry.value)
  if (pendingAction) {
    return pendingFocusDisabledReason(pendingAction, 'apply')
  }
  if (focusedProjectionFilterMode.value === 'missing') {
    return missingFocusDisabledReason(selectedProjectedActionEntry.value, 'apply')
  }
  if (focusedProjectionReasonLabel.value === '缺少主题标签') {
    return '缺少主题标签的条目还没有可入库主题，先补标签'
  }
  if (hasActiveFilter.value && !hasScopedKnowledgeCards.value && !hasScopedTopics.value) {
    return '当前筛选范围内没有已批准的知识卡片或主题综合'
  }
  return ''
})
const workflowBriefDisabledReason = computed(() => {
  const pendingAction = pendingFocusAction(selectedProjectedActionEntry.value)
  if (pendingAction) {
    return pendingFocusDisabledReason(pendingAction, 'generation')
  }
  if (focusedProjectionFilterMode.value === 'ready' && selectedProjectedActionEntry.value?.execution_kind === 'build_generation_draft') {
    return '当前范围已生成写作提纲，优先继续生成草稿'
  }
  if (focusedProjectionFilterMode.value === 'ready' && selectedProjectedActionEntry.value?.execution_kind === 'build_geo_variants') {
    return '当前范围已生成草稿，优先继续生成 GEO 变体'
  }
  if (focusedProjectionReasonLabel.value === '已生成 GEO 变体') {
    return '这些条目已生成 GEO 变体，无需重复执行'
  }
  if (focusedProjectionFilterMode.value === 'missing') {
    return missingFocusDisabledReason(selectedProjectedActionEntry.value, 'brief')
  }
  if (hasActiveFilter.value && !hasScopedKnowledgeCards.value) {
    return '当前筛选范围内没有已批准的知识卡片'
  }
  return ''
})
const workflowKnowledgeDisabled = computed(() => Boolean(workflowKnowledgeDisabledReason.value) || (hasActiveFilter.value && !hasScopedItems.value))
const workflowTopicDisabled = computed(() => Boolean(workflowTopicDisabledReason.value) || (hasActiveFilter.value && !hasScopedItems.value))
const workflowApplyDisabled = computed(() => Boolean(workflowApplyDisabledReason.value))
const workflowBriefDisabled = computed(() => Boolean(workflowBriefDisabledReason.value))
const canBuildScopedDrafts = computed(() => scopedGenerationBriefs.value.some((brief: Record<string, unknown>) => canBuildDraft(brief)))
const canBuildScopedGeoVariants = computed(() => scopedGenerationDrafts.value.some((draft: Record<string, unknown>) => canBuildGeo(draft)))
const workflowDraftDisabledReason = computed(() => {
  const pendingAction = pendingFocusAction(selectedProjectedActionEntry.value)
  if (pendingAction) {
    return pendingFocusDisabledReason(pendingAction, 'generation')
  }
  if (focusedProjectionFilterMode.value === 'missing') {
    return missingFocusDisabledReason(selectedProjectedActionEntry.value, 'generation')
  }
  if (focusedProjectionFilterMode.value === 'ready' && selectedProjectedActionEntry.value?.execution_kind === 'build_geo_variants') {
    return '当前范围已生成草稿，优先继续生成 GEO 变体'
  }
  if (focusedProjectionReasonLabel.value === '已生成 GEO 变体') {
    return '这些条目已生成 GEO 变体，无需重复执行'
  }
  if (hasActiveFilter.value && !selectedFilteredBriefIds.value.length) {
    return '当前筛选范围内没有写作提纲'
  }
  if (hasActiveFilter.value && !canBuildScopedDrafts.value) {
    return '当前筛选范围内没有已批准的写作提纲'
  }
  return ''
})
const workflowGeoDisabledReason = computed(() => {
  const pendingAction = pendingFocusAction(selectedProjectedActionEntry.value)
  if (pendingAction) {
    return pendingFocusDisabledReason(pendingAction, 'generation')
  }
  if (focusedProjectionFilterMode.value === 'missing') {
    return missingFocusDisabledReason(selectedProjectedActionEntry.value, 'generation')
  }
  if (focusedProjectionReasonLabel.value === '已生成 GEO 变体') {
    return '这些条目已生成 GEO 变体，无需重复执行'
  }
  if (focusedProjectionFilterMode.value === 'ready' && selectedProjectedActionEntry.value?.execution_kind === 'build_generation_draft') {
    return '当前范围已生成写作提纲，需先生成草稿'
  }
  if (hasActiveFilter.value && !selectedFilteredDraftIds.value.length) {
    return '当前筛选范围内没有草稿'
  }
  if (hasActiveFilter.value && !canBuildScopedGeoVariants.value) {
    return '当前筛选范围内没有已批准的草稿'
  }
  return ''
})
const workflowDraftDisabled = computed(() => Boolean(workflowDraftDisabledReason.value))
const workflowGeoDisabled = computed(() => Boolean(workflowGeoDisabledReason.value))
const workflowShortcut = computed(() => {
  const action = selectedProjectedActionEntry.value
  if (!action) return null
  const reviewFocused = focusedProjectionFilterMode.value === 'pending' || focusedProjectionReasonLabel.value.startsWith('待审批')
  if (reviewFocused && hasMatchingActionReviewPackets(action)) {
    if (hasSingleMatchingActionReviewPacket(action)) {
      return {
        kind: 'approve-single' as const,
        label: directApproveActionLabel(action),
      }
    }
    return {
      kind: 'approve-multi' as const,
      label: batchApproveActionLabel(action),
    }
  }
  if (focusedProjectionReasonLabel.value === '缺少主题标签' && selectedFilteredItemIds.value.length) {
    return {
      kind: 'ai-enrich' as const,
      label: '先补 AI 分类总结',
    }
  }
  if (focusedProjectionReasonLabel.value === '已存在知识沉淀' && scopedKnowledgeCandidates.value.length) {
    return {
      kind: 'jump-knowledge' as const,
      label: '查看对应知识卡片',
    }
  }
  if (focusedProjectionReasonLabel.value === '已存在主题沉淀' && scopedTopicSynthesisCandidates.value.length) {
    return {
      kind: 'jump-topic' as const,
      label: '查看对应主题综合',
    }
  }
  if (focusedProjectionFilterMode.value === 'ready' && action.execution_kind === 'build_generation_draft' && canBuildScopedDrafts.value) {
    return {
      kind: 'build-draft' as const,
      label: '继续生成草稿',
    }
  }
  if (focusedProjectionFilterMode.value === 'ready' && action.execution_kind === 'build_geo_variants' && canBuildScopedGeoVariants.value) {
    return {
      kind: 'build-geo' as const,
      label: '继续生成 GEO 变体',
    }
  }
  if (focusedProjectionReasonLabel.value === '已生成 GEO 变体' && scopedGeoVariants.value.length) {
    return {
      kind: 'jump-geo' as const,
      label: '查看对应 GEO 变体',
    }
  }
  const fallbackFocused = focusedProjectionFilterMode.value === 'missing' || projectionReasonMode(focusedProjectionReasonLabel.value) === 'missing'
  if (fallbackFocused && action.fallback_actionable) {
    return {
      kind: 'fallback' as const,
      label: action.fallback_execution_label || '先补上游候选',
    }
  }
  return null
})


function toggleDownstreamScopeMode() {
  showAllDownstreamLists.value = !showAllDownstreamLists.value
}

function sourceTypeLabel(type: string) {
  const labels: Record<string, string> = {
    wechat_article: '公众号',
    github_repo: 'GitHub',
    bilibili_video: 'B站视频',
    podcast_episode: '播客',
    podcast_feed: '播客',
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

function projectionReasonLabel(reason: string) {
  const labels: Record<string, string> = {
    raise_priority: '优先提高当前条目',
    raise_topic_priority: '优先补强对应主题',
    adjust_generation_template: '适合进入写作提纲',
    lower_priority: '建议降低优先级',
  }
  return labels[reason] ?? reason
}

function feedbackScopeLabel(scope: string) {
  const labels: Record<string, string> = {
    tag: '标签规则',
    source: '来源规则',
    action: '动作规则',
  }
  return labels[scope] ?? scope
}

function feedbackDecisionLabel(decision: string) {
  const labels: Record<string, string> = {
    adopted: '采纳偏好',
    rewrite: '改写偏好',
    dig_deeper: '深挖偏好',
    not_relevant: '降权信号',
    rejected: '删除信号',
    candidate: '候选阶段',
  }
  return labels[decision] ?? decisionLabel(decision)
}

function recommendedActionTitle(action: typeof recommendedProjectionActions.value[number]) {
  if (action.action === 'prepare_rewrite_brief') {
    if (action.execution_kind === 'build_generation_draft') return '准备生成草稿'
    if (action.execution_kind === 'build_geo_variants') return '准备生成 GEO 变体'
  }
  return action.label
}

function projectedActionStageLabel(item: Pick<typeof items.value[number], 'projected_action' | 'projected_action_label'>) {
  const action = String(item.projected_action || '')
  if (action !== 'prepare_rewrite_brief') {
    return String(item.projected_action_label || '')
  }
  if (selectedProjectedActionEntry.value?.execution_kind === 'build_generation_draft') {
    return '准备生成草稿'
  }
  if (selectedProjectedActionEntry.value?.execution_kind === 'build_geo_variants') {
    return '准备生成 GEO 变体'
  }
  return String(item.projected_action_label || '')
}

function recommendedActionSubtitle(action: typeof recommendedProjectionActions.value[number]) {
  if (selectedProjectedAction.value === recommendedActionKey(action) && pendingFocusAction(action)) {
    return pendingFocusNotice(action)
  }
  if (selectedProjectedAction.value === recommendedActionKey(action) && missingFocusAction(action)) {
    return missingFocusNotice(action)
  }
  if (selectedProjectedAction.value === recommendedActionKey(action) && blockedFocusAction(action)) {
    return focusedProjectionReasonLabel.value
      ? `当前聚焦的是${focusedProjectionReasonLabel.value}条目。`
      : '当前聚焦的是阻塞条目。'
  }
  if (action.action === 'prepare_rewrite_brief') {
    return executionIntentLabel(action.execution_kind || action.action)
  }
  return executionIntentLabel(action.action)
}

function projectionRuleKeyLabel(rule: { scope: string; key: string }) {
  if (rule.scope === 'action') {
    return executionIntentLabel(rule.key)
  }
  return rule.key
}
function reviewStatusLabel(status: string) {
  const labels: Record<string, string> = {
    open: '待审批',
    approved: '已批准',
    applied: '已应用',
    candidate: '候选',
    rejected: '已拒绝',
    edited: '编辑通过',
  }
  return labels[status] ?? status
}

function executionIntentLabel(intent: string) {
  const labels: Record<string, string> = {
    sync_wechat: '同步公众号',
    sync_external: '同步外部来源',
    tagging: '批量打标签',
    ai_enrich: 'AI 分类总结',
    export_wiki: '导出原始素材',
    build_knowledge: '生成知识候选',
    build_knowledge_candidate: '进入知识候选',
    build_knowledge_candidates: '生成知识候选',
    build_topic_synthesis: '生成主题综合',
    prepare_rewrite_brief: '准备生成写作提纲',
    apply_knowledge: '应用已批准知识',
    build_briefs: '生成写作提纲',
    build_generation_briefs: '生成写作提纲',
    build_draft: '生成草稿',
    build_generation_draft: '生成草稿',
    build_geo: '生成 GEO 变体',
    build_geo_variants: '生成 GEO 变体',
    keep_observing: '继续观察',
    lower_priority: '降低优先级',
    drop_from_pipeline: '移出后续链路',
  }
  return labels[intent] ?? intent
}

function executionStatusLabel(status: string) {
  const labels: Record<string, string> = {
    open: '待审批',
    pending: '待执行',
    queued: '排队中',
    running: '执行中',
    action_required: '待人工确认',
    completed: '已完成',
    failed: '失败',
    degraded: '降级完成',
    rejected: '已拒绝',
    approved: '已批准',
    applied: '已应用',
    candidate: '候选',
    edited: '编辑通过',
    waiting_human: '待人工确认',
    skipped: '已跳过',
  }
  return labels[status] ?? reviewStatusLabel(status)
}

function executionTriggerLabel(trigger: string) {
  const labels: Record<string, string> = {
    user: '手动触发',
    system: '系统续跑',
    scheduler: '定时触发',
    agent: 'Agent 触发',
  }
  return labels[trigger] ?? trigger
}

function reviewKindLabel(kind: string) {
  const labels: Record<string, string> = {
    knowledge_candidates_review: '知识候选审批',
    topic_synthesis_review: '主题综合审批',
    generation_briefs_review: '写作提纲审批',
    draft_review: '草稿审批',
    geo_review: 'GEO 审批',
  }
  return labels[kind] ?? kind
}

function downstreamKindLabel(kind: string) {
  const labels: Record<string, string> = {
    knowledge_card: '知识卡片',
    concept: '概念卡片',
    entity: '实体卡片',
    synthesis: '主题综合',
    topic_synthesis: '主题综合',
    brief: '写作提纲',
    draft: '草稿',
    geo_variant: 'GEO 变体',
  }
  return labels[kind] ?? kind
}

function downstreamStatusLabel(status: string) {
  return executionStatusLabel(status)
}



function recommendedActionPreconditionSummary(action: typeof recommendedProjectionActions.value[number]) {
  const statuses = Array.isArray(action.precondition_statuses) ? action.precondition_statuses : []
  return statuses.map((status: string) => reviewStatusLabel(status)).join(' / ')
}

function recommendedActionPreconditionState(action: typeof recommendedProjectionActions.value[number]) {
  if (selectedProjectedAction.value === recommendedActionKey(action) && pendingFocusAction(action)) {
    return '当前焦点仍待审批'
  }
  if (selectedProjectedAction.value === recommendedActionKey(action) && missingFocusAction(action)) {
    return '当前焦点仍缺上游候选'
  }
  if (selectedProjectedAction.value === recommendedActionKey(action) && blockedFocusAction(action)) {
    return '当前焦点仍有阻塞'
  }
  if (!Array.isArray(action.precondition_statuses) || !action.precondition_statuses.length) {
    return action.precondition_passed ? '当前可执行' : ''
  }
  return action.precondition_passed ? '前置状态已满足' : '前置状态未满足'
}

function isKnowledgeApplyResult(value: unknown): value is KnowledgeApplyResult {
  if (!value || typeof value !== 'object') return false
  const maybe = value as {
    requested_ids?: { cards?: unknown; topics?: unknown }
    accepted_ids?: { cards?: unknown; topics?: unknown }
    rejected_ids?: { cards?: unknown; topics?: unknown }
  }
  return Array.isArray(maybe.requested_ids?.cards)
    && Array.isArray(maybe.requested_ids?.topics)
    && Array.isArray(maybe.accepted_ids?.cards)
    && Array.isArray(maybe.accepted_ids?.topics)
    && Array.isArray(maybe.rejected_ids?.cards)
    && Array.isArray(maybe.rejected_ids?.topics)
}

function emptyKnowledgeApplyResult(): KnowledgeApplyResult {
  return {
    export_root: '',
    written_cards: 0,
    written_topics: 0,
    cards_index_file: '',
    topics_index_file: '',
    requested_ids: { cards: [], topics: [] },
    accepted_ids: { cards: [], topics: [] },
    rejected_ids: { cards: [], topics: [] },
    rejected_reasons: { cards: {}, topics: {} },
  }
}

function mergeUniqueIds(...groups: Array<string[] | undefined>) {
  return Array.from(new Set(groups.flatMap((group) => Array.isArray(group) ? group : []).filter(Boolean)))
}

const lastReviewKnowledgeApplyPayload = computed<KnowledgeApplyResult | null>(() => {
  const payloads = lastReviewResolutionEntries.value
    .map((resolution) => resolution.follow_up_result?.result)
    .filter(isKnowledgeApplyResult)
  if (!payloads.length) {
    return null
  }
  if (payloads.length === 1) {
    return payloads[0] ?? null
  }
  const merged = emptyKnowledgeApplyResult()
  for (const payload of payloads) {
    merged.export_root = merged.export_root || payload.export_root
    merged.cards_index_file = merged.cards_index_file || payload.cards_index_file
    merged.topics_index_file = merged.topics_index_file || payload.topics_index_file
    merged.written_cards += Number(payload.written_cards || 0)
    merged.written_topics += Number(payload.written_topics || 0)
    merged.requested_ids.cards = mergeUniqueIds(merged.requested_ids.cards, payload.requested_ids.cards)
    merged.requested_ids.topics = mergeUniqueIds(merged.requested_ids.topics, payload.requested_ids.topics)
    merged.accepted_ids.cards = mergeUniqueIds(merged.accepted_ids.cards, payload.accepted_ids.cards)
    merged.accepted_ids.topics = mergeUniqueIds(merged.accepted_ids.topics, payload.accepted_ids.topics)
    merged.rejected_ids.cards = mergeUniqueIds(merged.rejected_ids.cards, payload.rejected_ids.cards)
    merged.rejected_ids.topics = mergeUniqueIds(merged.rejected_ids.topics, payload.rejected_ids.topics)
    merged.rejected_reasons = merged.rejected_reasons || { cards: {}, topics: {} }
    merged.rejected_reasons.cards = {
      ...(merged.rejected_reasons.cards || {}),
      ...(payload.rejected_reasons?.cards || {}),
    }
    merged.rejected_reasons.topics = {
      ...(merged.rejected_reasons.topics || {}),
      ...(payload.rejected_reasons?.topics || {}),
    }
  }
  return merged
})
const lastReviewKnowledgeApplyRequestedCount = computed(() => (lastReviewKnowledgeApplyPayload.value?.requested_ids.cards.length ?? 0) + (lastReviewKnowledgeApplyPayload.value?.requested_ids.topics.length ?? 0))
const lastReviewKnowledgeApplyAcceptedCount = computed(() => (lastReviewKnowledgeApplyPayload.value?.accepted_ids.cards.length ?? 0) + (lastReviewKnowledgeApplyPayload.value?.accepted_ids.topics.length ?? 0))
const lastReviewKnowledgeApplyRejectedCount = computed(() => (lastReviewKnowledgeApplyPayload.value?.rejected_ids.cards.length ?? 0) + (lastReviewKnowledgeApplyPayload.value?.rejected_ids.topics.length ?? 0))

async function loadAll() {
  lastBatchReviewResolutions.value = []
  await contentItemsStore.loadAll()
}

async function rebuildFeedbackProjection() {
  projecting.value = true
  try {
    await contentItemsStore.rebuildFeedbackProjection()
    syncProjectionFocusState()
  } finally {
    projecting.value = false
  }
}

async function runAIEnrichment() {
  aiEnriching.value = true
  try {
    await contentItemsStore.runAIEnrichment({
      limit: hasActiveFilter.value ? selectedFilteredItemIds.value.length || 30 : 30,
      onlyMissing: true,
      tag: selectedTag.value || null,
      itemIds: hasActiveFilter.value ? selectedFilteredItemIds.value : null,
      maxChars: 3200,
    })
    syncProjectionFocusState()
  } finally {
    aiEnriching.value = false
  }
}

async function syncWechatPool() {
  syncing.value = true
  try {
    await contentItemsStore.syncWechatPool()
  } finally {
    syncing.value = false
  }
}

async function syncExternalSources() {
  syncingExternal.value = true
  try {
    await contentItemsStore.syncExternalSources({ useExample: true })
  } finally {
    syncingExternal.value = false
  }
}

async function sendFeedback(item: { id: string }, humanDecision: string, suggestedAction: string) {
  const note = window.prompt('人工备注（可留空）', '')
  if (note === null) return
  feedbackingId.value = item.id
  try {
    await contentItemsStore.sendFeedback({ itemId: item.id, humanDecision, feedbackNote: note, suggestedAction })
    syncProjectionFocusState()
  } finally {
    feedbackingId.value = ''
  }
}

function shouldContinueAfterResolve(packet: { packet_id: string; follow_up?: { action?: string } | null }, status: 'approved' | 'rejected' | 'edited') {
  if (status === 'rejected') return false
  if (!packet.follow_up?.action) return false
  return followUpEnabledPacketIds.value.includes(packet.packet_id)
}

function togglePacketFollowUp(packetId: string) {
  const packet = openReviewPackets.value.find((entry: typeof openReviewPackets.value[number]) => entry.packet_id === packetId)
  if (!packet?.follow_up?.action) return
  if (followUpEnabledPacketIds.value.includes(packetId)) {
    followUpEnabledPacketIds.value = followUpEnabledPacketIds.value.filter((value) => value !== packetId)
    return
  }
  followUpEnabledPacketIds.value = [...followUpEnabledPacketIds.value, packetId]
}

function toggleVisiblePacketFollowUp() {
  const visibleIds = visibleFollowUpPackets.value.map((packet: typeof visibleFollowUpPackets.value[number]) => packet.packet_id).filter(Boolean)
  if (!visibleIds.length) return
  if (allVisibleFollowUpEnabled.value) {
    const visibleIdSet = new Set(visibleIds)
    followUpEnabledPacketIds.value = followUpEnabledPacketIds.value.filter((value) => !visibleIdSet.has(value))
    return
  }
  const merged = new Set([...followUpEnabledPacketIds.value, ...visibleIds])
  followUpEnabledPacketIds.value = Array.from(merged)
}

async function approveVisibleReviewPackets() {
  if (!visibleReviewPackets.value.length) return
  const results: ExecutionReviewResolveResponse[] = []
  const processedIds: string[] = []
  for (const packet of visibleReviewPackets.value) {
    if (!packet.run_id || !packet.packet_id) continue
    const result = await contentItemsStore.resolveReviewPacket(packet.run_id, packet.packet_id, 'approved', shouldContinueAfterResolve(packet, 'approved'))
    results.push(result)
    processedIds.push(packet.packet_id)
  }
  if (results.length) {
    lastBatchReviewResolutions.value = results
  }
  if (processedIds.length) {
    const processedIdSet = new Set(processedIds)
    followUpEnabledPacketIds.value = followUpEnabledPacketIds.value.filter((value) => !processedIdSet.has(value))
    if (highlightedReviewPacketId.value && processedIdSet.has(highlightedReviewPacketId.value)) {
      clearFocusedHumanGate()
    }
  }
  syncProjectionFocusState()
}

async function rejectVisibleReviewPackets() {
  if (!visibleReviewPackets.value.length) return
  const results: ExecutionReviewResolveResponse[] = []
  const processedIds: string[] = []
  for (const packet of visibleReviewPackets.value) {
    if (!packet.run_id || !packet.packet_id) continue
    const result = await contentItemsStore.resolveReviewPacket(packet.run_id, packet.packet_id, 'rejected', false)
    results.push(result)
    processedIds.push(packet.packet_id)
  }
  if (results.length) {
    lastBatchReviewResolutions.value = results
  }
  if (processedIds.length) {
    const processedIdSet = new Set(processedIds)
    followUpEnabledPacketIds.value = followUpEnabledPacketIds.value.filter((value) => !processedIdSet.has(value))
    if (highlightedReviewPacketId.value && processedIdSet.has(highlightedReviewPacketId.value)) {
      clearFocusedHumanGate()
    }
  }
  syncProjectionFocusState()
}

async function resolveReviewPacket(packet: { run_id: string; packet_id: string }, status: 'approved' | 'rejected' | 'edited') {
  if (!packet.run_id || !packet.packet_id) return
  lastBatchReviewResolutions.value = []
  await contentItemsStore.resolveReviewPacket(packet.run_id, packet.packet_id, status, shouldContinueAfterResolve(packet, status))
  syncProjectionFocusState()
  followUpEnabledPacketIds.value = followUpEnabledPacketIds.value.filter((value) => value !== packet.packet_id)
  if (highlightedReviewPacketId.value === packet.packet_id) {
    clearFocusedHumanGate()
  }
}

async function buildKnowledgeCandidates() {
  if (hasActiveFilter.value && !hasScopedItems.value) return
  const payload = {
    projectedAction: selectedProjectedActionEntry.value?.action || recommendedActionBase(selectedProjectedAction.value) || undefined,
    itemIds: hasActiveFilter.value && selectedFilteredItemIds.value.length ? selectedFilteredItemIds.value : undefined,
  }
  const limit = hasActiveFilter.value ? selectedFilteredItemIds.value.length || 30 : 30
  await contentItemsStore.buildKnowledgeCandidates(limit, payload)
  syncProjectionFocusState()
}

async function applyReviewedKnowledge() {
  if (hasActiveFilter.value && !hasScopedKnowledgeCards.value && !hasScopedTopics.value) return
  await contentItemsStore.applyReviewedKnowledge({
    cardIds: hasActiveFilter.value && selectedFilteredKnowledgeCardIds.value.length ? selectedFilteredKnowledgeCardIds.value : undefined,
    topicIds: hasActiveFilter.value && selectedFilteredTopicIds.value.length ? selectedFilteredTopicIds.value : undefined,
  })
  syncProjectionFocusState()
}

async function buildGenerationBriefs() {
  if (hasActiveFilter.value && !hasScopedKnowledgeCards.value) return
  const payload = {
    projectedAction: selectedProjectedActionEntry.value?.action || recommendedActionBase(selectedProjectedAction.value) || undefined,
    knowledgeCardIds: hasActiveFilter.value && selectedFilteredKnowledgeCardIds.value.length ? selectedFilteredKnowledgeCardIds.value : undefined,
  }
  const limit = hasActiveFilter.value ? selectedFilteredKnowledgeCardIds.value.length || 10 : 10
  await contentItemsStore.buildGenerationBriefs(limit, payload)
  syncProjectionFocusState()
}

async function buildGenerationDraft(briefId: string) {
  await contentItemsStore.buildGenerationDraft(briefId)
  syncProjectionFocusState()
}

async function buildGeoVariants(draftId: string) {
  await contentItemsStore.buildGeoVariants(draftId)
  syncProjectionFocusState()
}

async function buildScopedGenerationDrafts() {
  const briefIds = scopedGenerationBriefs.value
    .filter((brief: Record<string, unknown>) => canBuildDraft(brief))
    .map((brief: Record<string, unknown>) => String(brief.id || ''))
    .filter(Boolean)
  if (!briefIds.length) return
  for (const briefId of briefIds) {
    await contentItemsStore.buildGenerationDraft(briefId)
  }
  syncProjectionFocusState()
}

async function buildScopedGeoVariants() {
  const draftIds = scopedGenerationDrafts.value
    .filter((draft: Record<string, unknown>) => canBuildGeo(draft))
    .map((draft: Record<string, unknown>) => String(draft.id || ''))
    .filter(Boolean)
  if (!draftIds.length) return
  for (const draftId of draftIds) {
    await contentItemsStore.buildGeoVariants(draftId)
  }
  syncProjectionFocusState()
}

async function buildTopicSynthesis() {
  if (hasActiveFilter.value && !hasScopedItems.value) return
  const payload = {
    itemIds: hasActiveFilter.value && selectedFilteredItemIds.value.length ? selectedFilteredItemIds.value : undefined,
  }
  const limit = hasActiveFilter.value ? selectedFilteredItemIds.value.length || 30 : 30
  await contentItemsStore.buildTopicSynthesis(limit, payload)
  syncProjectionFocusState()
}

function setSelectedTag(tagName = '') {
  selectedTag.value = tagName
  focusedProjectionItemIds.value = []
  focusedProjectionFilterMode.value = 'all'
  focusedProjectionReason.value = ''
  showAllDownstreamLists.value = false
}

function toggleSelectedTag(tagName: string) {
  selectedTag.value = selectedTag.value === tagName ? '' : tagName
  focusedProjectionItemIds.value = []
  focusedProjectionFilterMode.value = 'all'
  focusedProjectionReason.value = ''
  showAllDownstreamLists.value = false
}

function toggleProjectedAction(action: string) {
  selectedProjectedAction.value = selectedProjectedAction.value === action ? '' : action
  focusedProjectionItemIds.value = []
  focusedProjectionFilterMode.value = 'all'
  focusedProjectionReason.value = ''
  showAllDownstreamLists.value = false
}

async function runRecommendedAction(action: typeof recommendedProjectionActions.value[number]) {
  selectedProjectedAction.value = recommendedActionKey(action)
  const params = action.execution_params ?? {}
  if (action.execution_kind === 'build_knowledge_candidates') {
    const itemIds = Array.isArray(params.item_ids) ? params.item_ids.map((value: unknown) => String(value)).filter(Boolean) : []
    await contentItemsStore.buildKnowledgeCandidates(itemIds.length || 30, {
      projectedAction: typeof params.projected_action === 'string' ? params.projected_action : action.action,
      itemIds: itemIds.length ? itemIds : undefined,
    })
    syncProjectionFocusState()
    return
  }
  if (action.execution_kind === 'build_topic_synthesis') {
    const itemIds = Array.isArray(params.item_ids) ? params.item_ids.map((value: unknown) => String(value)).filter(Boolean) : []
    await contentItemsStore.buildTopicSynthesis(itemIds.length || 30, {
      itemIds: itemIds.length ? itemIds : undefined,
    })
    syncProjectionFocusState()
    return
  }
  if (action.execution_kind === 'build_generation_briefs') {
    const knowledgeCardIds = Array.isArray(params.knowledge_card_ids) ? params.knowledge_card_ids.map((value: unknown) => String(value)).filter(Boolean) : []
    await contentItemsStore.buildGenerationBriefs(knowledgeCardIds.length || 10, {
      projectedAction: typeof params.projected_action === 'string' ? params.projected_action : action.action,
      knowledgeCardIds: knowledgeCardIds.length ? knowledgeCardIds : undefined,
    })
    syncProjectionFocusState()
    return
  }
  if (action.execution_kind === 'build_generation_draft') {
    const briefIds = Array.isArray(params.brief_ids) ? params.brief_ids.map((value: unknown) => String(value)).filter(Boolean) : []
    for (const briefId of briefIds) {
      await contentItemsStore.buildGenerationDraft(briefId)
    }
    syncProjectionFocusState()
    return
  }
  if (action.execution_kind === 'build_geo_variants') {
    const draftIds = Array.isArray(params.draft_ids) ? params.draft_ids.map((value: unknown) => String(value)).filter(Boolean) : []
    for (const draftId of draftIds) {
      await contentItemsStore.buildGeoVariants(draftId)
    }
    syncProjectionFocusState()
  }
}

function recommendedActionButtonLabel(action: typeof recommendedProjectionActions.value[number]) {
  if (selectedProjectedAction.value === recommendedActionKey(action) && pendingFocusAction(action)) {
    return `先处理${currentPendingLabelForAction(action)}`
  }
  if (selectedProjectedAction.value === recommendedActionKey(action) && missingFocusAction(action)) {
    return `先处理${missingFocusLabel(action)}`
  }
  if (selectedProjectedAction.value === recommendedActionKey(action) && blockedFocusAction(action)) {
    return '先处理阻塞项'
  }
  if (!action.actionable) {
    return '当前不可执行'
  }
  return action.execution_label
}

function recommendedActionBlockedReason(action: typeof recommendedProjectionActions.value[number]) {
  const focusedPendingLabel = focusedPendingReasonLabelForAction(action)
  if (focusedPendingLabel) {
    const pendingAction = pendingFocusAction(action)
    if (!pendingAction) {
      return action.execution_blocked_reason || ''
    }
    return pendingFocusDisabledReason(pendingAction, action.action === 'build_topic_synthesis' ? 'topic' : action.action === 'build_knowledge_candidate' ? 'knowledge' : action.action === 'prepare_rewrite_brief' ? 'generation' : 'apply')
  }
  const focusedMissing = missingFocusAction(action)
  if (focusedMissing) {
    return missingFocusDisabledReason(focusedMissing, action.action === 'build_topic_synthesis' ? 'topic' : action.action === 'build_knowledge_candidate' ? 'knowledge' : action.action === 'prepare_rewrite_brief' ? 'generation' : 'apply')
  }
  const focusedBlocked = blockedFocusAction(action)
  if (focusedBlocked) {
    return focusedProjectionReasonLabel.value
      ? `当前聚焦的是${focusedProjectionReasonLabel.value}条目，先切回可执行项或查看对应结果`
      : '当前聚焦的是阻塞条目，先切回可执行项再执行'
  }
  return action.execution_blocked_reason || ''
}

function recommendedActionIsDisabled(action: typeof recommendedProjectionActions.value[number]) {
  if (selectedProjectedAction.value === recommendedActionKey(action) && pendingFocusAction(action)) {
    return true
  }
  if (selectedProjectedAction.value === recommendedActionKey(action) && missingFocusAction(action)) {
    return true
  }
  if (selectedProjectedAction.value === recommendedActionKey(action) && blockedFocusAction(action)) {
    return true
  }
  if (!action.actionable) {
    return true
  }
  const params = action.execution_params ?? {}
  if (action.execution_kind === 'build_knowledge_candidates' || action.execution_kind === 'build_topic_synthesis') {
    return !Array.isArray(params.item_ids) || params.item_ids.length === 0
  }
  if (action.execution_kind === 'build_generation_briefs') {
    return !Array.isArray(params.knowledge_card_ids) || params.knowledge_card_ids.length === 0
  }
  if (action.execution_kind === 'build_generation_draft') {
    return !Array.isArray(params.brief_ids) || params.brief_ids.length === 0
  }
  if (action.execution_kind === 'build_geo_variants') {
    return !Array.isArray(params.draft_ids) || params.draft_ids.length === 0
  }
  return false
}


async function runFallbackRecommendedAction(action: typeof recommendedProjectionActions.value[number]) {
  const params = action.fallback_execution_params ?? {}
  if (action.fallback_execution_kind === 'build_knowledge_candidates') {
    const itemIds = Array.isArray(params.item_ids) ? params.item_ids.map((value: unknown) => String(value)).filter(Boolean) : []
    await contentItemsStore.buildKnowledgeCandidates(itemIds.length || 30, {
      projectedAction: typeof params.projected_action === 'string' ? params.projected_action : action.action,
      itemIds: itemIds.length ? itemIds : undefined,
    })
    syncProjectionFocusState()
    return
  }
  if (action.fallback_execution_kind === 'ai_enrich') {
    const itemIds = Array.isArray(params.item_ids) ? params.item_ids.map((value: unknown) => String(value)).filter(Boolean) : []
    aiEnriching.value = true
    try {
      await contentItemsStore.runAIEnrichment({
        limit: itemIds.length || 30,
        onlyMissing: true,
        itemIds: itemIds.length ? itemIds : null,
        maxChars: 3200,
      })
      syncProjectionFocusState()
    } finally {
      aiEnriching.value = false
    }
  }
}


function fallbackRecommendedActionIsDisabled(action: typeof recommendedProjectionActions.value[number]) {
  if (!action.fallback_actionable) {
    return true
  }
  const params = action.fallback_execution_params ?? {}
  if (action.fallback_execution_kind === 'build_knowledge_candidates' || action.fallback_execution_kind === 'ai_enrich') {
    return !Array.isArray(params.item_ids) || params.item_ids.length === 0
  }
  return true
}
function focusHumanGate(packetId = '', packetIds: string[] = []) {
  highlightedReviewPacketId.value = packetId
  focusedReviewPacketIds.value = packetIds.filter(Boolean)
  const section = document.getElementById(packetId ? `review-packet-${packetId}` : 'human-gate-queue')
  section?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function syncFocusedHumanGateWithProjection(action: typeof recommendedProjectionActions.value[number] | null) {
  if (!action || !selectedProjectedAction.value) {
    clearFocusedHumanGate()
    return
  }
  const pendingFocused = focusedProjectionFilterMode.value === 'pending' || focusedProjectionReasonLabel.value.startsWith('待审批')
  if (!pendingFocused) {
    clearFocusedHumanGate()
    return
  }
  const basePackets = matchingActionReviewPackets(action)
  if (!basePackets.length) {
    clearFocusedHumanGate()
    return
  }
  const focusedLabel = focusedPendingReasonLabelForAction(action)
  const packetIds = (() => {
    if (!focusedLabel || focusedLabel === '待审批生成结果') {
      return basePackets.map((packet: typeof basePackets[number]) => packet.packet_id).filter(Boolean)
    }
    const kinds = new Set(pendingPacketKindsForLabel(focusedLabel))
    if (!kinds.size) {
      return basePackets.map((packet: typeof basePackets[number]) => packet.packet_id).filter(Boolean)
    }
    const filtered = basePackets
      .filter((packet: typeof basePackets[number]) => kinds.has(String(packet.kind || '')))
      .map((packet: typeof basePackets[number]) => packet.packet_id)
      .filter(Boolean)
    return filtered.length ? filtered : basePackets.map((packet: typeof basePackets[number]) => packet.packet_id).filter(Boolean)
  })()
  if (!packetIds.length) {
    clearFocusedHumanGate()
    return
  }
  focusedReviewPacketIds.value = packetIds
  if (!packetIds.includes(highlightedReviewPacketId.value)) {
    highlightedReviewPacketId.value = packetIds[0] || ''
  }
}

function clearFocusedHumanGate() {
  highlightedReviewPacketId.value = ''
  focusedReviewPacketIds.value = []
}

function handleRecommendedAction(action: typeof recommendedProjectionActions.value[number]) {
  if (!action.actionable) {
    return
  }
  return runRecommendedAction(action)
}

function canBuildDraft(brief: Record<string, unknown>) {
  const status = String(brief.status || '')
  return status === 'approved' || status === 'applied'
}

function canBuildGeo(draft: Record<string, unknown>) {
  const status = String(draft.status || '')
  return status === 'approved' || status === 'applied'
}

function generationTraceSummary(row: Record<string, unknown>) {
  const parts: string[] = []
  if (row.source_run_id) parts.push(`来源 run ${String(row.source_run_id)}`)
  if (row.source_task_id) parts.push(`task ${String(row.source_task_id)}`)
  if (row.source_packet_id) parts.push(`packet ${String(row.source_packet_id)}`)
  if (row.applied_run_id) parts.push(`批准 run ${String(row.applied_run_id)}`)
  if (row.applied_task_id) parts.push(`批准 task ${String(row.applied_task_id)}`)
  if (row.applied_packet_id) parts.push(`批准 packet ${String(row.applied_packet_id)}`)
  return parts.join(' · ')
}

function previewTraceSummary(details: Record<string, unknown> | undefined) {
  if (!details) return ''
  const parts: string[] = []
  if (details.source_run_id) parts.push(`来源 run ${String(details.source_run_id)}`)
  if (details.source_task_id) parts.push(`task ${String(details.source_task_id)}`)
  if (details.source_packet_id) parts.push(`packet ${String(details.source_packet_id)}`)
  if (details.applied_run_id) parts.push(`批准 run ${String(details.applied_run_id)}`)
  if (details.applied_task_id) parts.push(`批准 task ${String(details.applied_task_id)}`)
  if (details.applied_packet_id) parts.push(`批准 packet ${String(details.applied_packet_id)}`)
  return parts.join(' · ')
}

function reviewResolutionTraceSummary(resolution: ExecutionReviewResolveResponse) {
  return previewTraceSummary(resolution.candidate_payload)
}

function followUpRunContextSummary(run: { context?: Record<string, unknown> | null }) {
  const context = run.context || {}
  const parts: string[] = []
  if (context.source_run_id) parts.push(`来源 run ${String(context.source_run_id)}`)
  if (context.packet_id) parts.push(`packet ${String(context.packet_id)}`)
  if (Array.isArray(context.card_ids) && context.card_ids.length) parts.push(`cards ${context.card_ids.length} 项`)
  if (Array.isArray(context.topic_ids) && context.topic_ids.length) parts.push(`topics ${context.topic_ids.length} 项`)
  if (context.brief_id) parts.push(`brief ${String(context.brief_id)}`)
  if (context.draft_id) parts.push(`draft ${String(context.draft_id)}`)
  return parts.join(' · ')
}

function joinedIds(values: string[] | undefined) {
  return Array.isArray(values) && values.length ? values.join(' · ') : '无'
}

function joinedRejectedReasons(values: Record<string, string> | undefined) {
  const entries = values ? Object.entries(values).filter(([, reason]) => String(reason || '').trim()) : []
  return entries.length ? entries.map(([id, reason]) => `${id}：${reason}`).join(' · ') : '无'
}

function projectionReasonMode(reason: string) {
  if (reason.startsWith('待审批')) return 'pending'
  if (reason === '缺少知识候选' || reason === '缺少主题标签') return 'missing'
  return 'blocked'
}

function projectionFocusReason(itemId: string) {
  const action = selectedProjectedActionEntry.value
  if (!action) return ''
  const specificReason = action.blocked_reason_by_item[itemId]
  if (specificReason) return specificReason
  if (focusedProjectionFilterMode.value === 'pending' && action.pending_approval_item_ids.includes(itemId)) {
    return currentPendingLabelForAction(action)
  }
  if (focusedProjectionFilterMode.value === 'missing' && action.missing_candidate_item_ids.includes(itemId)) {
    return '缺少知识候选'
  }
  if (focusedProjectionFilterMode.value === 'blocked' && action.pending_approval_item_ids.includes(itemId)) {
    return pendingBlockedLabel(action)
  }
  if (focusedProjectionFilterMode.value === 'blocked' && action.missing_candidate_item_ids.includes(itemId)) {
    return missingFocusBlockedLabel(action)
  }
  if (focusedProjectionFilterMode.value === 'blocked' && action.blocked_item_ids.includes(itemId)) {
    return '已存在阻塞条件'
  }
  return ''
}

function clearFocusedProjectionItems() {
  focusedProjectionItemIds.value = []
  focusedProjectionFilterMode.value = 'all'
  focusedProjectionReason.value = ''
  showAllDownstreamLists.value = false
}

function focusProjectionReason(action: typeof recommendedProjectionActions.value[number], reason: string) {
  const itemIds = Object.entries(action.blocked_reason_by_item)
    .filter(([, value]) => value === reason)
    .map(([itemId]) => itemId)
  focusedProjectionItemIds.value = itemIds
  focusedProjectionFilterMode.value = projectionReasonMode(reason)
  focusedProjectionReason.value = reason
  selectedProjectedAction.value = recommendedActionKey(action)
  showAllDownstreamLists.value = false
  const topItemId = focusedProjectionItemIds.value[0]
  requestAnimationFrame(() => {
    const section = document.getElementById(topItemId ? `content-item-${topItemId}` : 'recent-items-panel')
    section?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  })
}

function focusPendingItems(action: typeof recommendedProjectionActions.value[number]) {
  focusedProjectionItemIds.value = currentPendingItemIdsForAction(action)
  focusedProjectionFilterMode.value = 'pending'
  focusedProjectionReason.value = focusedPendingReasonLabelForAction(action)
  selectedProjectedAction.value = recommendedActionKey(action)
  showAllDownstreamLists.value = false
  const topItemId = focusedProjectionItemIds.value[0]
  requestAnimationFrame(() => {
    const section = document.getElementById(topItemId ? `content-item-${topItemId}` : 'recent-items-panel')
    section?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  })
}

function focusProjectionItems(action: typeof recommendedProjectionActions.value[number], mode: 'ready' | 'blocked' | 'pending' | 'missing') {
  if (mode === 'pending') {
    focusPendingItems(action)
    return
  }
  let itemIds: string[] = []
  if (mode === 'ready') {
    const rawItemIds = Array.isArray(action.execution_params.item_ids) ? action.execution_params.item_ids : []
    itemIds = rawItemIds.map((value: unknown) => String(value)).filter(Boolean)
  }
  if (mode === 'blocked') itemIds = action.blocked_item_ids
  if (mode === 'missing') itemIds = action.missing_candidate_item_ids
  focusedProjectionItemIds.value = itemIds.map((value: string) => String(value)).filter(Boolean)
  focusedProjectionFilterMode.value = mode
  focusedProjectionReason.value = ''
  selectedProjectedAction.value = recommendedActionKey(action)
  showAllDownstreamLists.value = false
  const topItemId = focusedProjectionItemIds.value[0]
  requestAnimationFrame(() => {
    const section = document.getElementById(topItemId ? `content-item-${topItemId}` : 'recent-items-panel')
    section?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  })
}

async function runWorkflowShortcut() {
  const action = selectedProjectedActionEntry.value
  const shortcut = workflowShortcut.value
  if (!action || !shortcut) return
  if (shortcut.kind === 'approve-single') {
    await approveSingleMatchingActionReviewPacket(action)
    return
  }
  if (shortcut.kind === 'approve-multi') {
    await approveMatchingActionReviewPackets(action)
    return
  }
  if (shortcut.kind === 'jump-knowledge') {
    focusWorkflowPanel('knowledge-candidates-panel')
    return
  }
  if (shortcut.kind === 'jump-topic') {
    focusWorkflowPanel('topic-synthesis-panel')
    return
  }
  if (shortcut.kind === 'build-draft') {
    await buildScopedGenerationDrafts()
    return
  }
  if (shortcut.kind === 'build-geo') {
    await buildScopedGeoVariants()
    return
  }
  if (shortcut.kind === 'jump-geo') {
    focusWorkflowPanel('geo-variants-panel')
    return
  }
  if (shortcut.kind === 'ai-enrich') {
    aiEnriching.value = true
    try {
      await contentItemsStore.runAIEnrichment({
        limit: selectedFilteredItemIds.value.length || 30,
        onlyMissing: true,
        itemIds: selectedFilteredItemIds.value,
        maxChars: 3200,
      })
      syncProjectionFocusState()
    } finally {
      aiEnriching.value = false
    }
    return
  }
  await runFallbackRecommendedAction(action)
}

function focusWorkflowPanel(panelId: 'knowledge-candidates-panel' | 'topic-synthesis-panel' | 'generation-briefs-panel' | 'generation-drafts-panel' | 'geo-variants-panel') {
  showAllDownstreamLists.value = false
  requestAnimationFrame(() => {
    const section = document.getElementById(panelId)
    section?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  })
}

function syncProjectionFocusState() {
  const action = selectedProjectedActionEntry.value
  if (!selectedProjectedAction.value) {
    clearFocusedHumanGate()
    clearFocusedProjectionItems()
    return
  }
  if (!action) {
    selectedProjectedAction.value = ''
    clearFocusedHumanGate()
    clearFocusedProjectionItems()
    return
  }
  if (focusedProjectionReason.value) {
    const itemIds = Object.entries(action.blocked_reason_by_item)
      .filter(([, value]) => value === focusedProjectionReason.value)
      .map(([itemId]) => itemId)
    if (itemIds.length) {
      focusedProjectionItemIds.value = itemIds
      focusedProjectionFilterMode.value = projectionReasonMode(focusedProjectionReason.value)
      syncFocusedHumanGateWithProjection(action)
      return
    }
    if (action.ready_count && Array.isArray(action.execution_params.item_ids) && action.execution_params.item_ids.length) {
      const readyItemIds = action.execution_params.item_ids.map((value: unknown) => String(value)).filter(Boolean)
      focusedProjectionItemIds.value = readyItemIds
      focusedProjectionFilterMode.value = 'ready'
      focusedProjectionReason.value = ''
      syncFocusedHumanGateWithProjection(action)
      return
    }
    clearFocusedHumanGate()
    clearFocusedProjectionItems()
    return
  }
  if (focusedProjectionFilterMode.value === 'pending') {
    if (currentPendingItemIdsForAction(action).length) {
      focusedProjectionItemIds.value = currentPendingItemIdsForAction(action)
      syncFocusedHumanGateWithProjection(action)
      return
    }
    if (action.ready_count && Array.isArray(action.execution_params.item_ids) && action.execution_params.item_ids.length) {
      const readyItemIds = action.execution_params.item_ids.map((value: unknown) => String(value)).filter(Boolean)
      focusedProjectionItemIds.value = readyItemIds
      focusedProjectionFilterMode.value = 'ready'
      syncFocusedHumanGateWithProjection(action)
      return
    }
    clearFocusedHumanGate()
    clearFocusedProjectionItems()
    return
  }
  if (focusedProjectionFilterMode.value === 'missing') {
    if (action.missing_candidate_item_ids.length) {
      focusedProjectionItemIds.value = action.missing_candidate_item_ids
      syncFocusedHumanGateWithProjection(action)
      return
    }
    if (action.ready_count && Array.isArray(action.execution_params.item_ids) && action.execution_params.item_ids.length) {
      const readyItemIds = action.execution_params.item_ids.map((value: unknown) => String(value)).filter(Boolean)
      focusedProjectionItemIds.value = readyItemIds
      focusedProjectionFilterMode.value = 'ready'
      syncFocusedHumanGateWithProjection(action)
      return
    }
    clearFocusedHumanGate()
    clearFocusedProjectionItems()
    return
  }
  if (focusedProjectionFilterMode.value === 'blocked') {
    if (action.blocked_item_ids.length) {
      focusedProjectionItemIds.value = action.blocked_item_ids
      syncFocusedHumanGateWithProjection(action)
      return
    }
    if (action.ready_count && Array.isArray(action.execution_params.item_ids) && action.execution_params.item_ids.length) {
      const readyItemIds = action.execution_params.item_ids.map((value: unknown) => String(value)).filter(Boolean)
      focusedProjectionItemIds.value = readyItemIds
      focusedProjectionFilterMode.value = 'ready'
      syncFocusedHumanGateWithProjection(action)
      return
    }
    clearFocusedHumanGate()
    clearFocusedProjectionItems()
    return
  }
  if (focusedProjectionFilterMode.value === 'ready') {
    if (action.ready_count && Array.isArray(action.execution_params.item_ids) && action.execution_params.item_ids.length) {
      focusedProjectionItemIds.value = action.execution_params.item_ids.map((value: unknown) => String(value)).filter(Boolean)
      syncFocusedHumanGateWithProjection(action)
      return
    }
    clearFocusedHumanGate()
    clearFocusedProjectionItems()
  }
}


function isWorkflowRecommended(kind: 'knowledge' | 'topic' | 'brief' | 'draft' | 'geo') {
  if (kind === 'knowledge') {
    return selectedProjectedActionEntry.value?.action === 'build_knowledge_candidate'
  }
  if (kind === 'topic') {
    return selectedProjectedActionEntry.value?.action === 'build_topic_synthesis'
  }
  if (kind === 'brief') {
    return selectedProjectedActionEntry.value?.action === 'prepare_rewrite_brief' && selectedProjectedActionEntry.value?.execution_kind === 'build_generation_briefs'
  }
  if (kind === 'draft') {
    return selectedProjectedActionEntry.value?.action === 'prepare_rewrite_brief' && selectedProjectedActionEntry.value?.execution_kind === 'build_generation_draft'
  }
  if (kind === 'geo') {
    return selectedProjectedActionEntry.value?.action === 'prepare_rewrite_brief' && selectedProjectedActionEntry.value?.execution_kind === 'build_geo_variants'
  }
  return false
}

function syncHumanGateState() {
  const openPacketIds = new Set(openReviewPackets.value.map((packet: typeof openReviewPackets.value[number]) => packet.packet_id).filter(Boolean))
  if (highlightedReviewPacketId.value && !openPacketIds.has(highlightedReviewPacketId.value)) {
    highlightedReviewPacketId.value = ''
  }
  if (focusedReviewPacketIds.value.length) {
    focusedReviewPacketIds.value = focusedReviewPacketIds.value.filter((packetId) => openPacketIds.has(packetId))
  }
  if (followUpEnabledPacketIds.value.length) {
    followUpEnabledPacketIds.value = followUpEnabledPacketIds.value.filter((packetId) => openPacketIds.has(packetId))
  }
}

watch([selectedProjectedActionEntry, focusedProjectionFilterMode, focusedProjectionReasonLabel], ([action]) => {
  syncFocusedHumanGateWithProjection(action ?? null)
})

watch(openReviewPackets, () => {
  syncHumanGateState()
}, { deep: true })

watch(recommendedProjectionActions, () => {
  if (selectedProjectedAction.value || focusedProjectionFilterMode.value !== 'all' || focusedProjectionReason.value) {
    syncProjectionFocusState()
  }
})

onMounted(async () => {
  if (!items.value.length) {
    await loadAll()
  }
})
</script>

<template>
  <div class="content-loop-shell h-full overflow-y-auto px-4 py-5 sm:px-6 sm:py-6">
    <div class="mx-auto grid max-w-[1500px] gap-5">
      <header class="content-loop-hero">
        <div class="min-w-0">
          <div class="flex items-center gap-3">
            <span class="content-loop-mark"><Workflow class="h-5 w-5" /></span>
            <p class="content-loop-kicker">内容闭环</p>
          </div>
          <h1>人机共创内容生成闭环</h1>
          <p>把内容池、知识候选、写作提纲、草稿、GEO 统一到一个执行工作台里。</p>
        </div>
        <div class="content-loop-actions">
          <button type="button" class="loop-btn loop-btn--ghost" :disabled="loading" @click="loadAll"><RefreshCw class="h-4 w-4" :class="loading ? 'animate-spin' : ''" />刷新</button>
          <button type="button" class="loop-btn" :disabled="syncing" @click="syncWechatPool"><Loader2 v-if="syncing" class="h-4 w-4 animate-spin" /><Database v-else class="h-4 w-4" />同步公众号</button>
          <button type="button" class="loop-btn loop-btn--accent" :disabled="syncingExternal" @click="syncExternalSources"><Loader2 v-if="syncingExternal" class="h-4 w-4 animate-spin" /><GitBranch v-else class="h-4 w-4" />同步外部信源</button>
          <button type="button" class="loop-btn loop-btn--tag" :disabled="projecting" @click="rebuildFeedbackProjection"><Loader2 v-if="projecting" class="h-4 w-4 animate-spin" /><MessageSquareText v-else class="h-4 w-4" />重建反馈投影</button>
          <button type="button" class="loop-btn loop-btn--ai" :disabled="aiEnriching || (hasActiveFilter && !hasScopedItems)" @click="runAIEnrichment"><Loader2 v-if="aiEnriching" class="h-4 w-4 animate-spin" /><Bot v-else class="h-4 w-4" />AI 分类总结</button>
        </div>
      </header>

      <div v-if="error" class="content-loop-alert"><XCircle class="h-4 w-4 shrink-0" /><span>{{ error }}</span></div>

      <section class="content-loop-stats">
        <article class="stat-tile"><Database class="h-4 w-4" /><span>内容池</span><strong>{{ overview?.content_items ?? 0 }}</strong></article>
        <article class="stat-tile"><Repeat2 class="h-4 w-4" /><span>公众号候选</span><strong>{{ overview?.wechat_candidates ?? 0 }}</strong></article>
        <article class="stat-tile"><GitBranch class="h-4 w-4" /><span>启用外部信源</span><strong>{{ overview?.enabled_external_sources ?? 0 }}</strong></article>
        <article class="stat-tile"><MessageSquareText class="h-4 w-4" /><span>反馈事件</span><strong>{{ overview?.feedback_events ?? 0 }}</strong></article>
        <article class="stat-tile"><Tag class="h-4 w-4" /><span>已打标签</span><strong>{{ overview?.tagged_items ?? tagOverview?.tagged_items ?? 0 }}</strong></article>
        <article class="stat-tile"><MessageSquareText class="h-4 w-4" /><span>反馈规则</span><strong>{{ overview?.feedback_projection_rules ?? feedbackProjection?.rows ?? 0 }}</strong></article>
      </section>

      <section v-if="latestRun" class="loop-panel execution-panel">
        <div class="panel-head"><div><p class="panel-label">执行记录</p><h2>最近一次执行</h2></div><span class="file-chip">{{ latestRun.run_id }}</span></div>
        <div class="mini-breakdown"><span>意图 · {{ executionIntentLabel(latestRun.intent) }}</span><span>状态 · {{ executionStatusLabel(latestRun.status) }}</span><span>触发 · {{ executionTriggerLabel(latestRun.trigger) }}</span></div>
        <p class="muted mt-3">{{ latestRun.summary || '本次执行尚未生成摘要。' }}</p>
        <p v-if="latestRun.failure_state?.message" class="source-result mt-2">{{ latestRun.failure_state.message }}</p>
      </section>

      <section v-if="primaryLastReviewResolution" class="loop-panel execution-panel">
        <div class="panel-head"><div><p class="panel-label">审批结果</p><h2>{{ reviewResultTitle }}</h2></div><span class="file-chip">{{ reviewResultChip }}</span></div>
        <div class="mini-breakdown"><span>类型 · {{ lastReviewKindSummary || reviewKindLabel(primaryLastReviewResolution.kind) }}</span><span>处理结果 · {{ lastReviewStatusSummary || executionStatusLabel(primaryLastReviewResolution.status) }}</span><span>续跑 · {{ lastResolutionAttemptedFollowUp ? `已尝试 ${lastFollowUpRunCount + lastFollowUpErrorCount} 个` : '未触发' }}</span><span v-if="lastFollowUpErrorCount">失败 · {{ lastFollowUpErrorCount }} 个</span><span v-if="lastFollowUpRun">续跑意图 · {{ executionIntentLabel(lastFollowUpRun.intent) }}</span><span v-if="lastFollowUpRun">续跑状态 · {{ executionStatusLabel(lastFollowUpRun.status) }}</span></div>
        <p class="muted mt-3">{{ hasBatchReviewResolution ? `本次共处理 ${lastReviewResolutionEntries.length} 个审批包。` : primaryLastReviewResolution.reason }}</p>
        <div v-if="hasBatchReviewResolution" class="item-list mt-3">
          <article v-for="resolution in lastReviewResolutionEntries" :key="resolution.packet_id" class="content-item">
            <div class="min-w-0"><div class="item-meta"><span>{{ reviewKindLabel(resolution.kind) }}</span><span>{{ executionStatusLabel(resolution.status) }}</span><span>{{ resolution.packet_id }}</span><span v-if="reviewResolutionAttemptedFollowUp(resolution)">续跑 {{ reviewResolutionFollowUpAttemptCount(resolution) }} 个</span><span v-if="reviewResolutionLeadRun(resolution)">{{ executionIntentLabel(reviewResolutionLeadRun(resolution)?.intent || '') }}</span><span v-if="reviewResolutionLeadRun(resolution)">{{ reviewResolutionLeadRun(resolution)?.run_id }}</span></div><h3>{{ resolution.reason }}</h3><p v-if="reviewResolutionTraceSummary(resolution)" class="muted">{{ reviewResolutionTraceSummary(resolution) }}</p><p v-if="reviewResolutionLeadRun(resolution)?.summary" class="muted">{{ reviewResolutionLeadRun(resolution)?.summary }}</p></div>
          </article>
        </div>
        <p v-else-if="lastFollowUpRun?.summary" class="source-result mt-2">{{ lastFollowUpRun.summary }}</p>
        <div v-if="lastReviewKnowledgeApplyPayload" class="item-list mt-3">
          <article class="content-item">
            <div class="min-w-0"><div class="item-meta"><span>{{ executionIntentLabel('apply_knowledge') }}</span><span>请求 {{ lastReviewKnowledgeApplyRequestedCount }} 项</span><span>写入 {{ lastReviewKnowledgeApplyAcceptedCount }} 项</span><span v-if="lastReviewKnowledgeApplyRejectedCount">未写入 {{ lastReviewKnowledgeApplyRejectedCount }} 项</span></div><h3>{{ hasBatchReviewResolution ? '本批知识入库汇总' : '续跑知识入库明细' }}</h3><p class="muted">cards 请求：{{ joinedIds(lastReviewKnowledgeApplyPayload.requested_ids.cards) }}</p><p class="muted">topics 请求：{{ joinedIds(lastReviewKnowledgeApplyPayload.requested_ids.topics) }}</p><p class="muted">cards 写入：{{ joinedIds(lastReviewKnowledgeApplyPayload.accepted_ids.cards) }}</p><p class="muted">topics 写入：{{ joinedIds(lastReviewKnowledgeApplyPayload.accepted_ids.topics) }}</p><p v-if="lastReviewKnowledgeApplyRejectedCount" class="muted">未写入：cards {{ joinedIds(lastReviewKnowledgeApplyPayload.rejected_ids.cards) }} · topics {{ joinedIds(lastReviewKnowledgeApplyPayload.rejected_ids.topics) }}</p><p v-if="lastReviewKnowledgeApplyPayload.rejected_reasons?.cards && Object.keys(lastReviewKnowledgeApplyPayload.rejected_reasons.cards).length" class="muted">卡片原因：{{ joinedRejectedReasons(lastReviewKnowledgeApplyPayload.rejected_reasons.cards) }}</p><p v-if="lastReviewKnowledgeApplyPayload.rejected_reasons?.topics && Object.keys(lastReviewKnowledgeApplyPayload.rejected_reasons.topics).length" class="muted">主题原因：{{ joinedRejectedReasons(lastReviewKnowledgeApplyPayload.rejected_reasons.topics) }}</p></div>
          </article>
        </div>
        <p v-if="lastFollowUpRunCount > 1" class="muted mt-2">本次已连续触发 {{ lastFollowUpRunCount }} 个续跑任务。</p>
        <div v-if="followUpRunsForDisplay.length > 1" class="item-list mt-3">
          <article v-for="run in followUpRunsForDisplay" :key="run.run_id" class="content-item">
            <div class="min-w-0"><div class="item-meta"><span>{{ executionIntentLabel(run.intent) }}</span><span>{{ executionStatusLabel(run.status) }}</span><span>{{ executionTriggerLabel(run.trigger) }}</span></div><h3>{{ run.summary || run.run_id }}</h3><p v-if="followUpRunContextSummary(run)" class="muted">{{ followUpRunContextSummary(run) }}</p></div>
            <div class="item-actions"><span class="file-chip">{{ run.run_id }}</span></div>
          </article>
        </div>
        <div v-if="lastFollowUpErrors.length" class="item-list mt-3">
          <article v-for="entry in lastFollowUpErrors" :key="entry.target_id" class="content-item">
            <div class="min-w-0"><div class="item-meta"><span>续跑错误</span><span>{{ entry.target_id }}</span></div><h3>续跑失败</h3><p class="muted">{{ entry.error }}</p></div>
          </article>
        </div>
      </section>

      <section id="human-gate-queue" v-if="openReviewPackets.length" class="loop-panel">
        <div class="panel-head"><div><p class="panel-label">人工闸门</p><h2>待人工确认</h2></div><div class="item-actions"><span class="file-chip">{{ visibleReviewPackets.length }} / {{ openReviewPackets.length }} 项</span><button v-if="canResolveVisibleReviewPackets && visibleReviewPackets.length > 1" type="button" class="decision-btn decision-btn--keep" @click="approveVisibleReviewPackets()">当前列表全部批准</button><button v-if="canResolveVisibleReviewPackets && visibleReviewPackets.length > 1" type="button" class="decision-btn decision-btn--reject" @click="rejectVisibleReviewPackets()">当前列表全部拒绝</button><button v-if="visibleFollowUpPackets.length > 1" type="button" class="tag-filter-btn" @click="toggleVisiblePacketFollowUp()">{{ allVisibleFollowUpEnabled ? '当前列表关闭续跑' : someVisibleFollowUpEnabled ? '当前列表补齐续跑' : '当前列表开启续跑' }}</button><button v-if="focusedReviewPacketIds.length" type="button" class="tag-filter-btn" @click="clearFocusedHumanGate">查看全部</button></div></div>
        <div class="item-list">
          <article v-for="packet in visibleReviewPackets" :id="`review-packet-${packet.packet_id}`" :key="packet.packet_id" class="content-item" :class="highlightedReviewPacketId === packet.packet_id ? 'content-item--highlighted' : ''">
            <div class="min-w-0"><div class="item-meta"><span>{{ reviewKindLabel(packet.kind) }}</span><span>{{ executionStatusLabel(packet.status) }}</span><span>{{ executionIntentLabel(packet.run_intent) }}</span><span v-if="packet.preview?.label">{{ packet.preview.label }}</span></div><h3>{{ packet.reason }}</h3><p>{{ packet.preview?.summary || packet.run_summary || packet.suggested_action || '等待人工判断后继续执行。' }}</p><p v-if="packet.preview?.items?.length" class="muted">{{ packet.preview.items.join(' · ') }}</p><p v-if="typeof packet.preview?.details?.candidates === 'number' || typeof packet.preview?.details?.synthesis === 'number'" class="muted">候选 {{ Number(packet.preview?.details?.candidates || 0) }} 条 · 主题 {{ Number(packet.preview?.details?.synthesis || 0) }} 条</p><p v-if="typeof packet.preview?.details?.created === 'number' || typeof packet.preview?.details?.total_candidates === 'number'" class="muted">已创建 {{ Number(packet.preview?.details?.created || 0) }} 条 · 候选总数 {{ Number(packet.preview?.details?.total_candidates || 0) }} 条</p><p v-if="packet.preview?.details?.topic" class="muted">主题：{{ String(packet.preview.details.topic || '') }}</p><p v-if="typeof packet.preview?.details?.qa_count === 'number' || typeof packet.preview?.details?.faq_count === 'number'" class="muted">QA {{ Number(packet.preview?.details?.qa_count || 0) }} 条 · FAQ {{ Number(packet.preview?.details?.faq_count || 0) }} 条</p><p v-if="packet.preview?.details?.summary" class="muted">{{ String(packet.preview.details.summary || '') }}</p><p v-if="previewTraceSummary(packet.preview?.details as Record<string, unknown> | undefined)" class="muted">{{ previewTraceSummary(packet.preview?.details as Record<string, unknown> | undefined) }}</p></div>
            <div class="item-actions"><label v-if="packet.follow_up?.action" class="tag-filter-btn"><input type="checkbox" :checked="followUpEnabledPacketIds.includes(packet.packet_id)" @change="togglePacketFollowUp(packet.packet_id)" />{{ packet.follow_up?.label || '批准后继续' }}</label><span v-else class="file-chip">批准后结束</span><button type="button" class="decision-btn decision-btn--keep" @click="resolveReviewPacket(packet, 'approved')">{{ packet.follow_up?.label || '批准' }}</button><button type="button" class="decision-btn" @click="resolveReviewPacket(packet, 'edited')">编辑通过</button><button type="button" class="decision-btn decision-btn--reject" @click="resolveReviewPacket(packet, 'rejected')">拒绝</button></div>
          </article>
        </div>
      </section>

      <main class="content-loop-grid">
        <aside class="loop-panel loop-rail">
          <p class="panel-label">工作目标</p>
          <p class="north-star">人决定方向，AI 交付候选，人和 AI 一起调优。</p>
          <p class="muted">当前已把反馈投影、审批包、知识候选、写作提纲、草稿、GEO 后端链路接起来，并开始把结果列表接入前端。</p>
          <div class="stage-list">
            <button v-for="stage in stages" :key="stage.key" type="button" class="stage-btn" :class="activeStageKey === stage.key ? 'stage-btn--active' : ''" @click="activeStageKey = stage.key">
              <span class="stage-index">{{ stage.index }}</span>
              <span class="min-w-0"><span class="stage-name">{{ stage.name }}</span><span class="stage-status">{{ stage.status }}</span></span>
            </button>
          </div>
        </aside>

        <section class="grid min-w-0 gap-5">
          <section class="loop-panel">
            <div class="panel-head"><div><p class="panel-label">反馈投影</p><h2>反馈策略投影</h2></div><span class="file-chip">{{ overview?.feedback_projection_file || 'data/feedback_projection.jsonl' }}</span></div>
            <div class="mini-breakdown">
              <span>规则数 · {{ feedbackProjection?.rows ?? 0 }}</span>
              <span>标签 · {{ feedbackProjection?.scope_counts.tag ?? 0 }}</span>
              <span>来源 · {{ feedbackProjection?.scope_counts.source ?? 0 }}</span>
              <span>动作 · {{ feedbackProjection?.scope_counts.action ?? 0 }}</span>
              <span v-if="feedbackProjection?.updated_at">更新于 · {{ feedbackProjection.updated_at }}</span>
            </div>
            <div class="content-loop-grid mt-4">
              <section class="loop-panel">
                <div class="panel-head"><div><p class="panel-label">正向规则</p><h2>正向信号</h2></div></div>
                <div v-if="positiveProjectionRules.length" class="item-list">
                  <article v-for="rule in positiveProjectionRules" :key="`${rule.scope}-${rule.key}`" class="content-item">
                    <div class="min-w-0">
                      <div class="item-meta"><span>{{ feedbackScopeLabel(rule.scope) }}</span><span>{{ feedbackDecisionLabel(rule.dominant_decision) }}</span><span>反馈 {{ rule.total_feedback }}</span></div>
                      <h3>{{ projectionRuleKeyLabel(rule) }}</h3>
                    </div>
                    <div class="item-actions"><span class="file-chip">+{{ Number(rule.priority_delta || 0).toFixed(2) }}</span></div>
                  </article>
                </div>
                <div v-else class="empty-state">暂无正向规则。</div>
              </section>
              <section class="loop-panel">
                <div class="panel-head"><div><p class="panel-label">负向规则</p><h2>负向信号</h2></div></div>
                <div v-if="negativeProjectionRules.length" class="item-list">
                  <article v-for="rule in negativeProjectionRules" :key="`${rule.scope}-${rule.key}`" class="content-item">
                    <div class="min-w-0">
                      <div class="item-meta"><span>{{ feedbackScopeLabel(rule.scope) }}</span><span>{{ feedbackDecisionLabel(rule.dominant_decision) }}</span><span>反馈 {{ rule.total_feedback }}</span></div>
                      <h3>{{ projectionRuleKeyLabel(rule) }}</h3>
                    </div>
                    <div class="item-actions"><span class="file-chip">{{ Number(rule.priority_delta || 0).toFixed(2) }}</span></div>
                  </article>
                </div>
                <div v-else class="empty-state">暂无负向规则。</div>
              </section>
            </div>
            <section class="loop-panel mt-4">
              <div class="panel-head"><div><p class="panel-label">动作提示</p><h2>动作提示</h2></div></div>
              <div v-if="actionProjectionRules.length" class="item-list">
                <article v-for="rule in actionProjectionRules" :key="rule.key" class="content-item">
                  <div class="min-w-0"><div class="item-meta"><span>动作规则</span><span>{{ feedbackDecisionLabel(rule.dominant_decision) }}</span><span>反馈 {{ rule.total_feedback }}</span></div><h3>{{ projectionRuleKeyLabel(rule) }}</h3><p>{{ rule.strategy_hint || '暂无动作建议。' }}</p></div>
                </article>
              </div>
              <div v-else class="empty-state">暂无动作提示。</div>
            </section>
            <section class="loop-panel mt-4">
              <div class="panel-head"><div><p class="panel-label">下一步建议</p><h2>下一步建议</h2></div></div>
              <div v-if="recommendedProjectionActions.length" class="item-list">
                <article v-for="action in recommendedProjectionActions" :key="recommendedActionKey(action)" class="content-item">
                  <div class="min-w-0"><div class="item-meta"><span>动作建议</span><span>{{ action.count }} 条</span><span>可执行 {{ action.ready_count }} 条</span><span v-if="action.blocked_count">阻塞 {{ action.blocked_count }} 条</span><span>最高 {{ Number(action.top_score).toFixed(2) }}</span></div><h3>{{ recommendedActionTitle(action) }}</h3><p>{{ recommendedActionSubtitle(action) }}</p><p v-if="action.sample_titles.length" class="muted">{{ action.sample_titles.join(' · ') }}</p><p class="muted">分数区间：{{ Number(action.score_range.min).toFixed(2) }} - {{ Number(action.score_range.max).toFixed(2) }}</p><p v-if="recommendedActionPreconditionSummary(action)" class="muted">前置状态：{{ recommendedActionPreconditionSummary(action) }} · {{ recommendedActionPreconditionState(action) }}</p><p v-if="action.blocked_reason_breakdown.length" class="muted">阻塞分布：<button v-for="entry in action.blocked_reason_breakdown" :key="`${recommendedActionKey(action)}-${entry.reason}`" type="button" class="tag-filter-btn" :class="selectedProjectedAction === recommendedActionKey(action) && focusedProjectionReasonLabel === entry.reason ? 'tag-filter-btn--active' : ''" @click="focusProjectionReason(action, entry.reason)">{{ entry.reason }} {{ entry.count }} 条</button></p><p v-if="currentPendingItemsForAction(action).count" class="muted">{{ currentPendingLabelForAction(action) }} {{ currentPendingItemsForAction(action).count }} 条 · {{ currentPendingItemsForAction(action).sampleTitles.join(' · ') }}</p><p v-if="action.missing_candidate_count" class="muted">{{ missingFocusLabel(action) }} {{ action.missing_candidate_count }} 条 · {{ action.missing_candidate_sample_titles.join(' · ') }}</p><p v-if="action.pending_approval_count && hasMatchingActionReviewPackets(action)" class="muted">Human Gate 中匹配到 {{ pendingPacketLabel(action, matchingActionReviewPacketCount(action)) }}。</p></div>
                  <div class="item-actions"><button type="button" class="tag-filter-btn" :class="selectedProjectedAction === recommendedActionKey(action) && focusedProjectionFilterMode === 'all' ? 'tag-filter-btn--active' : ''" @click="toggleProjectedAction(recommendedActionKey(action))">{{ selectedProjectedAction === recommendedActionKey(action) && focusedProjectionFilterMode === 'all' ? '取消筛选' : '筛选条目' }}</button><button v-if="action.ready_count && Array.isArray(action.execution_params.item_ids) && action.execution_params.item_ids.length" type="button" class="tag-filter-btn" :class="selectedProjectedAction === recommendedActionKey(action) && focusedProjectionFilterMode === 'ready' ? 'tag-filter-btn--active' : ''" @click="focusProjectionItems(action, 'ready')">查看可执行项</button><button v-if="action.blocked_count && action.blocked_item_ids.length" type="button" class="tag-filter-btn" :class="selectedProjectedAction === recommendedActionKey(action) && focusedProjectionFilterMode === 'blocked' ? 'tag-filter-btn--active' : ''" @click="focusProjectionItems(action, 'blocked')">查看阻塞项</button><button v-if="action.pending_approval_count && action.pending_approval_item_ids.length" type="button" class="tag-filter-btn" :class="selectedProjectedAction === recommendedActionKey(action) && focusedProjectionFilterMode === 'pending' ? 'tag-filter-btn--active' : ''" @click="focusProjectionItems(action, 'pending')">查看{{ currentPendingLabelForAction(action) }}</button><button v-if="action.missing_candidate_count && action.missing_candidate_item_ids.length" type="button" class="tag-filter-btn" :class="selectedProjectedAction === recommendedActionKey(action) && focusedProjectionFilterMode === 'missing' ? 'tag-filter-btn--active' : ''" @click="focusProjectionItems(action, 'missing')">查看{{ missingFocusLabel(action) }}</button><button type="button" class="decision-btn" :disabled="recommendedActionIsDisabled(action)" :title="recommendedActionBlockedReason(action)" @click="handleRecommendedAction(action)">{{ recommendedActionButtonLabel(action) }}</button><button v-if="hasSingleMatchingActionReviewPacket(action)" type="button" class="decision-btn decision-btn--keep" :title="actionFollowUpEnabled(action) ? '' : '该审批包没有后续续跑动作，批准后会结束当前链路'" @click="approveSingleMatchingActionReviewPacket(action)">{{ directApproveActionLabel(action) }}</button><button v-else-if="action.pending_approval_count > 1 && hasMatchingActionReviewPackets(action)" type="button" class="decision-btn decision-btn--keep" :title="actionFollowUpEnabled(action) ? `批量批准 ${pendingPacketLabel(action, matchingActionReviewPacketCount(action))}` : '匹配到的审批包里没有可续跑动作，批准后会结束当前链路'" @click="approveMatchingActionReviewPackets(action)">{{ batchApproveActionLabel(action) }}</button><button v-else-if="action.pending_approval_count && hasMatchingActionReviewPackets(action)" type="button" class="decision-btn" :title="`匹配 ${pendingPacketLabel(action, matchingActionReviewPacketCount(action))}`" @click="focusHumanGate(firstMatchingActionReviewPacketId(action), matchingActionReviewPacketIds(action))">去对应审批</button><button v-if="action.fallback_actionable" type="button" class="decision-btn" :disabled="fallbackRecommendedActionIsDisabled(action)" @click="runFallbackRecommendedAction(action)">{{ action.fallback_execution_label }}</button></div>

                </article>
              </div>
              <div v-else class="empty-state">暂无下一步建议。</div>
            </section>
            <section class="loop-panel mt-4">
              <div class="panel-head"><div><p class="panel-label">优先级快照</p><h2>高优先级条目快照</h2></div><div class="item-actions"><span class="file-chip">{{ scopedSummaryProjectionItems.length }} 条</span><span v-if="hasActiveFilter" class="file-chip">当前范围</span></div></div>
              <div v-if="hasActiveFilter && scopedListScopeSummary" class="mini-breakdown mt-3"><span>{{ scopedListScopeSummary }}</span></div>
              <div v-if="scopedSummaryProjectionItems.length" class="item-list">
                <article v-for="item in scopedSummaryProjectionItems" :key="item.id" class="content-item">
                  <div class="min-w-0"><div class="item-meta"><span>{{ item.source_name }}</span><span>{{ projectedActionStageLabel(item) }}</span></div><h3>{{ item.title }}</h3><p v-if="item.projected_action_reason" class="muted">{{ projectionReasonLabel(item.projected_action_reason) }}</p></div>
                  <div class="item-actions"><span class="file-chip">{{ Number(item.projected_score).toFixed(2) }}</span></div>
                </article>
              </div>
              <div v-else class="empty-state">{{ hasActiveFilter && scopedListScopeSummary ? `${scopedListScopeSummary} 下暂无高优先级条目。` : '暂无高优先级条目。' }}</div>
            </section>
            <section class="loop-panel mt-4">
              <div class="panel-head"><div><p class="panel-label">投影队列</p><h2>当前投影优先级</h2></div><div class="item-actions"><span class="file-chip">{{ scopedTopProjectionItems.length }} 条</span><span v-if="hasActiveFilter" class="file-chip">当前范围</span></div></div>
              <div v-if="hasActiveFilter && scopedListScopeSummary" class="mini-breakdown mt-3"><span>{{ scopedListScopeSummary }}</span></div>
              <div v-if="scopedTopProjectionItems.length" class="item-list">
                <article v-for="item in scopedTopProjectionItems" :key="item.id" class="content-item">
                  <div class="min-w-0">
                    <div class="item-meta"><span>{{ sourceTypeLabel(item.source_type) }}</span><span>{{ item.source_name }}</span><span>{{ decisionLabel(item.human_decision || 'candidate') }}</span></div>
                    <h3>{{ item.title }}</h3>
                    <p>{{ item.ai_summary || item.summary || item.content_preview }}</p>
                    <p v-if="item.projected_action_label" class="muted">建议动作：{{ projectedActionStageLabel(item) }}<span v-if="item.projected_action_reason"> · {{ projectionReasonLabel(item.projected_action_reason) }}</span></p>
                  </div>
                  <div class="item-actions"><span class="file-chip">{{ Number(item.projected_score || item.score || 0).toFixed(2) }}</span></div>
                </article>
              </div>
              <div v-else class="empty-state">{{ hasActiveFilter && scopedListScopeSummary ? `${scopedListScopeSummary} 下暂无投影排序结果。` : '暂无投影排序结果。' }}</div>
            </section>
          </section>

          <section v-if="lastKnowledgeApplyResult && lastKnowledgeApplyPayload" class="loop-panel execution-panel">
            <div class="panel-head"><div><p class="panel-label">知识入库</p><h2>最近一次知识入库</h2></div><span class="file-chip">{{ lastKnowledgeApplyRun?.run_id || '手动执行' }}</span></div>
            <div class="mini-breakdown"><span>状态 · {{ executionStatusLabel(lastKnowledgeApplyRun?.status || 'completed') }}</span><span>请求 · {{ lastKnowledgeApplyRequestedCount }} 项</span><span>写入 · {{ lastKnowledgeApplyAcceptedCount }} 项</span><span v-if="lastKnowledgeApplyRejectedCount">未写入 · {{ lastKnowledgeApplyRejectedCount }} 项</span></div>
            <p class="muted mt-3">{{ lastKnowledgeApplyRun?.summary || '最近一次知识入库结果。' }}</p>
            <div class="item-list mt-3">
              <article class="content-item">
                <div class="min-w-0"><div class="item-meta"><span>请求范围</span><span>卡片 {{ lastKnowledgeApplyPayload.requested_ids.cards.length }}</span><span>主题 {{ lastKnowledgeApplyPayload.requested_ids.topics.length }}</span></div><h3>请求入库范围</h3><p class="muted">卡片：{{ joinedIds(lastKnowledgeApplyPayload.requested_ids.cards) }}</p><p class="muted">主题：{{ joinedIds(lastKnowledgeApplyPayload.requested_ids.topics) }}</p></div>
              </article>
              <article class="content-item">
                <div class="min-w-0"><div class="item-meta"><span>实际写入</span><span>卡片 {{ lastKnowledgeApplyPayload.accepted_ids.cards.length }}</span><span>主题 {{ lastKnowledgeApplyPayload.accepted_ids.topics.length }}</span></div><h3>实际写入</h3><p class="muted">卡片：{{ joinedIds(lastKnowledgeApplyPayload.accepted_ids.cards) }}</p><p class="muted">主题：{{ joinedIds(lastKnowledgeApplyPayload.accepted_ids.topics) }}</p></div>
              </article>
              <article class="content-item">
                <div class="min-w-0"><div class="item-meta"><span>未写入</span><span>卡片 {{ lastKnowledgeApplyPayload.rejected_ids.cards.length }}</span><span>主题 {{ lastKnowledgeApplyPayload.rejected_ids.topics.length }}</span></div><h3>未写入</h3><p class="muted">卡片：{{ joinedIds(lastKnowledgeApplyPayload.rejected_ids.cards) }}</p><p class="muted">主题：{{ joinedIds(lastKnowledgeApplyPayload.rejected_ids.topics) }}</p><p v-if="lastKnowledgeApplyPayload.rejected_reasons?.cards && Object.keys(lastKnowledgeApplyPayload.rejected_reasons.cards).length" class="muted">卡片原因：{{ joinedRejectedReasons(lastKnowledgeApplyPayload.rejected_reasons.cards) }}</p><p v-if="lastKnowledgeApplyPayload.rejected_reasons?.topics && Object.keys(lastKnowledgeApplyPayload.rejected_reasons.topics).length" class="muted">主题原因：{{ joinedRejectedReasons(lastKnowledgeApplyPayload.rejected_reasons.topics) }}</p></div>
              </article>
            </div>
          </section>

          <section class="loop-panel">
            <div class="panel-head"><div><p class="panel-label">链路动作</p><h2>生成链路动作</h2></div><span class="file-chip">{{ workflowHint }}</span></div>
            <div v-if="selectedProjectedActionLabel || selectedTag || workflowFocusNotice" class="mini-breakdown"><span>当前筛选动作 · {{ selectedProjectedActionLabel || '未选' }}</span><span v-if="selectedTag">标签 · {{ selectedTag }}</span><span>内容项 · {{ selectedFilteredItemIds.length }}</span><span>知识卡片 · {{ selectedFilteredKnowledgeCardIds.length }}</span><span>主题综合 · {{ selectedFilteredTopicIds.length }}</span><span v-if="workflowFocusNotice">{{ workflowFocusNotice }}</span><span v-if="hasActiveFilter">下游结果 · {{ downstreamScopeLabel }}</span></div>
            <div class="item-actions">
              <button type="button" class="decision-btn" @click="contentItemsStore.exportWikiSources()">导出原始素材</button>
              <button v-if="hasActiveFilter" type="button" class="tag-filter-btn" @click="toggleDownstreamScopeMode()">{{ showAllDownstreamLists ? '回到当前范围' : '查看全量结果' }}</button>
              <button v-if="workflowShortcut" type="button" class="decision-btn decision-btn--keep" @click="runWorkflowShortcut()">{{ workflowShortcut.label }}</button>
              <button type="button" class="decision-btn" :class="isWorkflowRecommended('knowledge') ? 'tag-filter-btn--active' : ''" :disabled="workflowKnowledgeDisabled" :title="workflowKnowledgeDisabledReason || (hasActiveFilter && !hasScopedItems ? '当前筛选范围内没有可处理内容项' : '')" @click="buildKnowledgeCandidates()">生成知识候选</button>
              <button type="button" class="decision-btn" :class="isWorkflowRecommended('topic') ? 'tag-filter-btn--active' : ''" :disabled="workflowTopicDisabled" :title="workflowTopicDisabledReason || (hasActiveFilter && !hasScopedItems ? '当前筛选范围内没有可处理内容项' : '')" @click="buildTopicSynthesis()">生成主题综合</button>
              <button type="button" class="decision-btn" :disabled="workflowApplyDisabled" :title="workflowApplyDisabledReason" @click="applyReviewedKnowledge()">应用已批准知识</button>
              <button type="button" class="decision-btn" :class="isWorkflowRecommended('brief') ? 'tag-filter-btn--active' : ''" :disabled="workflowBriefDisabled" :title="workflowBriefDisabledReason" @click="buildGenerationBriefs()">生成写作提纲</button>
              <button type="button" class="decision-btn" :class="isWorkflowRecommended('draft') ? 'tag-filter-btn--active' : ''" :disabled="workflowDraftDisabled" :title="workflowDraftDisabledReason" @click="buildScopedGenerationDrafts()">批量生成草稿</button>
              <button type="button" class="decision-btn decision-btn--dig" :class="isWorkflowRecommended('geo') ? 'tag-filter-btn--active' : ''" :disabled="workflowGeoDisabled" :title="workflowGeoDisabledReason" @click="buildScopedGeoVariants()">批量生成 GEO</button>
            </div>
          </section>

          <section id="knowledge-candidates-panel" class="loop-panel">
            <div class="panel-head"><div><p class="panel-label">知识候选</p><h2>知识候选列表</h2></div><div class="item-actions"><span class="file-chip">{{ displayKnowledgeCandidates.length }} 条</span><span v-if="hasActiveFilter" class="file-chip">{{ downstreamScopeLabel }}</span></div></div>
            <div v-if="useScopedDownstreamLists && scopedListScopeSummary" class="mini-breakdown mt-3"><span>{{ scopedListScopeSummary }}</span></div>
            <div class="item-list" v-if="displayKnowledgeCandidates.length">
              <article v-for="card in displayKnowledgeCandidates.slice(0, 6)" :key="String(card.id)" class="content-item" :class="focusedProjectionItemIdSet.has(String(card.source_item_id || '')) ? 'content-item--highlighted' : ''">
                <div class="min-w-0"><div class="item-meta"><span>{{ downstreamKindLabel(String(card.kind || '')) }}</span><span>{{ downstreamStatusLabel(String(card.status || '')) }}</span><span v-if="card.projected_action_label">{{ String(card.projected_action_label || '') }}</span></div><h3>{{ String(card.title || '') }}</h3><p>{{ String(card.summary || '') }}</p><p v-if="card.projected_action_reason" class="muted">{{ projectionReasonLabel(String(card.projected_action_reason || '')) }}</p><p v-if="generationTraceSummary(card)" class="muted">{{ generationTraceSummary(card) }}</p></div>
              </article>
            </div>
            <div v-else class="empty-state">{{ useScopedDownstreamLists && scopedListScopeSummary ? `${scopedListScopeSummary} 下暂无知识候选。` : '暂无知识候选。' }}</div>
          </section>

          <section id="topic-synthesis-panel" class="loop-panel">
            <div class="panel-head"><div><p class="panel-label">主题综合</p><h2>主题综合候选</h2></div><div class="item-actions"><span class="file-chip">{{ displayTopicSynthesisCandidates.length }} 条</span><span v-if="hasActiveFilter" class="file-chip">{{ downstreamScopeLabel }}</span></div></div>
            <div v-if="useScopedDownstreamLists && scopedListScopeSummary" class="mini-breakdown mt-3"><span>{{ scopedListScopeSummary }}</span></div>
            <div class="item-list" v-if="displayTopicSynthesisCandidates.length">
              <article v-for="topic in displayTopicSynthesisCandidates.slice(0, 6)" :key="String(topic.id)" class="content-item" :class="(Array.isArray(topic.source_item_ids) ? topic.source_item_ids.map((value: unknown) => String(value)) : [String(topic.source_item_id || '')]).some((itemId: string) => focusedProjectionItemIdSet.has(itemId)) ? 'content-item--highlighted' : ''">
                <div class="min-w-0"><div class="item-meta"><span>{{ downstreamStatusLabel(String(topic.status || '')) }}</span><span>{{ String(topic.projected_action_label || '') }}</span></div><h3>{{ String(topic.title || '') }}</h3><p>{{ String(topic.summary || '') }}</p><p v-if="topic.projected_action_reason" class="muted">{{ projectionReasonLabel(String(topic.projected_action_reason || '')) }}</p><p v-if="generationTraceSummary(topic)" class="muted">{{ generationTraceSummary(topic) }}</p></div>
              </article>
            </div>
            <div v-else class="empty-state">{{ useScopedDownstreamLists && scopedListScopeSummary ? `${scopedListScopeSummary} 下暂无主题综合候选。` : '暂无主题综合候选。' }}</div>
          </section>

          <section id="generation-briefs-panel" class="loop-panel">
            <div class="panel-head"><div><p class="panel-label">写作提纲</p><h2>提纲列表</h2></div><div class="item-actions"><span class="file-chip">{{ displayGenerationBriefs.length }} 条</span><span v-if="hasActiveFilter" class="file-chip">{{ downstreamScopeLabel }}</span></div></div>
            <div v-if="useScopedDownstreamLists && scopedListScopeSummary" class="mini-breakdown mt-3"><span>{{ scopedListScopeSummary }}</span></div>
            <div class="item-list" v-if="displayGenerationBriefs.length">
              <article v-for="brief in displayGenerationBriefs.slice(0, 6)" :key="String(brief.id)" class="content-item" :class="focusedProjectionKnowledgeCardIdSet.has(String(brief.knowledge_card_id || '')) ? 'content-item--highlighted' : ''">
                <div class="min-w-0"><div class="item-meta"><span>{{ downstreamStatusLabel(String(brief.status || '')) }}</span><span>{{ String(brief.topic || '') }}</span><span v-if="brief.projected_action_label">{{ String(brief.projected_action_label || '') }}</span></div><h3>{{ String(brief.title || '') }}</h3><p>{{ String(brief.summary || '') }}</p><p v-if="brief.projected_action_reason" class="muted">{{ projectionReasonLabel(String(brief.projected_action_reason || '')) }}</p><p v-if="generationTraceSummary(brief)" class="muted">{{ generationTraceSummary(brief) }}</p></div>
                <div class="item-actions"><button type="button" class="decision-btn" :disabled="!canBuildDraft(brief)" :title="canBuildDraft(brief) ? '' : '写作提纲需要先在人工闸门中批准后再生成草稿'" @click="buildGenerationDraft(String(brief.id || ''))">生成草稿</button></div>
              </article>
            </div>
            <div v-else class="empty-state">{{ useScopedDownstreamLists && scopedListScopeSummary ? `${scopedListScopeSummary} 下暂无写作提纲。` : '暂无写作提纲。' }}</div>
          </section>

          <section id="generation-drafts-panel" class="loop-panel">
            <div class="panel-head"><div><p class="panel-label">草稿</p><h2>草稿列表</h2></div><div class="item-actions"><span class="file-chip">{{ displayGenerationDrafts.length }} 条</span><span v-if="hasActiveFilter" class="file-chip">{{ downstreamScopeLabel }}</span></div></div>
            <div v-if="useScopedDownstreamLists && scopedListScopeSummary" class="mini-breakdown mt-3"><span>{{ scopedListScopeSummary }}</span></div>
            <div class="item-list" v-if="displayGenerationDrafts.length">
              <article v-for="draft in displayGenerationDrafts.slice(0, 6)" :key="String(draft.id)" class="content-item" :class="focusedProjectionBriefIdSet.has(String(draft.brief_id || '')) ? 'content-item--highlighted' : ''">
                <div class="min-w-0"><div class="item-meta"><span>{{ downstreamStatusLabel(String(draft.status || '')) }}</span><span>{{ String(draft.topic || '') }}</span></div><h3>{{ String(draft.title || '') }}</h3><p>{{ String(draft.content || '').slice(0, 120) }}...</p><p v-if="generationTraceSummary(draft)" class="muted">{{ generationTraceSummary(draft) }}</p></div>
                <div class="item-actions"><button type="button" class="decision-btn decision-btn--dig" :disabled="!canBuildGeo(draft)" :title="canBuildGeo(draft) ? '' : '草稿需要先在人工闸门中批准后再生成 GEO 变体'" @click="buildGeoVariants(String(draft.id || ''))">生成 GEO 变体</button></div>
              </article>
            </div>
            <div v-else class="empty-state">{{ useScopedDownstreamLists && scopedListScopeSummary ? `${scopedListScopeSummary} 下暂无草稿。` : '暂无草稿。' }}</div>
          </section>

          <section id="geo-variants-panel" class="loop-panel">
            <div class="panel-head"><div><p class="panel-label">GEO 变体</p><h2>GEO 变体列表</h2></div><div class="item-actions"><span class="file-chip">{{ displayGeoVariants.length }} 条</span><span v-if="hasActiveFilter" class="file-chip">{{ downstreamScopeLabel }}</span></div></div>
            <div v-if="useScopedDownstreamLists && scopedListScopeSummary" class="mini-breakdown mt-3"><span>{{ scopedListScopeSummary }}</span></div>
            <div class="item-list" v-if="displayGeoVariants.length">
              <article v-for="geo in displayGeoVariants.slice(0, 6)" :key="String(geo.id)" class="content-item" :class="focusedProjectionDraftIdSet.has(String(geo.draft_id || '')) ? 'content-item--highlighted' : ''">
                <div class="min-w-0"><div class="item-meta"><span>{{ downstreamStatusLabel(String(geo.status || '')) }}</span><span>{{ String(geo.topic || '') }}</span></div><h3>{{ String(geo.title || '') }}</h3><p>问答 {{ Array.isArray(geo.qa_summary) ? geo.qa_summary.length : 0 }} 条 · 常见问题 {{ Array.isArray(geo.faq) ? geo.faq.length : 0 }} 条</p><p v-if="generationTraceSummary(geo)" class="muted">{{ generationTraceSummary(geo) }}</p></div>
              </article>
            </div>
            <div v-else class="empty-state">{{ useScopedDownstreamLists && scopedListScopeSummary ? `${scopedListScopeSummary} 下暂无 GEO 变体。` : '暂无 GEO 变体。' }}</div>
          </section>

          <section id="recent-items-panel" class="loop-panel">
            <div class="panel-head"><div><p class="panel-label">最近条目</p><h2>{{ recentItemsTitle }}</h2></div></div>
            <div class="tag-filter-row">
              <button type="button" class="tag-filter-btn" :class="selectedTag === '' ? 'tag-filter-btn--active' : ''" @click="setSelectedTag()">全部标签<span>{{ items.length }}</span></button>
              <button v-for="[tagName, count] in tagBreakdown" :key="tagName" type="button" class="tag-filter-btn" :class="selectedTag === tagName ? 'tag-filter-btn--active' : ''" @click="toggleSelectedTag(tagName)">{{ tagName }}<span>{{ count }}</span></button>
            </div>
            <div v-if="selectedProjectedActionLabel || selectedTag || focusedProjectionFilterLabel || focusedProjectionReasonLabel" class="mini-breakdown mt-3"><span v-if="selectedProjectedActionLabel">当前动作筛选 · {{ selectedProjectedActionLabel }}</span><span v-if="selectedTag">标签 · {{ selectedTag }}</span><span v-if="focusedProjectionFilterLabel">焦点模式 · {{ focusedProjectionFilterLabel }}</span><span v-if="focusedProjectionReasonLabel">具体原因 · {{ focusedProjectionReasonLabel }}</span><button v-if="focusedProjectionFilterMode !== 'all' || focusedProjectionReasonLabel" type="button" class="tag-filter-btn" @click="clearFocusedProjectionItems">清除焦点</button></div>
            <div v-if="loading" class="empty-state"><Loader2 class="h-5 w-5 animate-spin" />加载内容池...</div>
            <div v-else-if="filteredItems.length === 0" class="empty-state"><Search class="h-5 w-5" />{{ items.length === 0 ? '还没有 ContentItem，先点击“同步公众号”。' : '当前筛选条件下还没有候选素材。' }}</div>
            <div v-else class="item-list">
              <article v-for="item in filteredItems.slice(0, 8)" :id="`content-item-${item.id}`" :key="item.id" class="content-item">
                <div class="min-w-0"><div class="item-meta"><span>{{ sourceTypeLabel(item.source_type) }}</span><span>{{ item.source_name }}</span><span>{{ item.published_at || item.fetched_at || '未标时间' }}</span><span>{{ decisionLabel(item.human_decision || 'candidate') }}</span><span v-if="typeof item.feedback_projection_delta === 'number' && item.feedback_projection_delta !== 0">投影 {{ item.feedback_projection_delta > 0 ? '+' : '' }}{{ item.feedback_projection_delta }}</span><span v-if="projectionFocusReason(item.id)">{{ projectionFocusReason(item.id) }}</span></div><h3>{{ item.title }}</h3><p>{{ item.ai_summary || item.summary || item.content_preview }}</p><div v-if="item.tags?.length" class="item-tags"><span v-for="tagName in item.tags.slice(0, 5)" :key="tagName">{{ tagName }}</span></div><a v-if="item.url" :href="item.url" target="_blank" rel="noopener noreferrer" class="item-link"><ExternalLink class="h-3.5 w-3.5" />原始来源</a></div>
                <div class="item-actions"><button type="button" class="decision-btn decision-btn--keep" :disabled="feedbackingId === item.id" @click="sendFeedback(item, 'adopted', 'raise_item_score')"><CheckCircle2 class="h-3.5 w-3.5" />采纳</button><button type="button" class="decision-btn" :disabled="feedbackingId === item.id" @click="sendFeedback(item, 'rewrite', 'adjust_generation_template')"><PenLine class="h-3.5 w-3.5" />改写</button><button type="button" class="decision-btn decision-btn--dig" :disabled="feedbackingId === item.id" @click="sendFeedback(item, 'dig_deeper', 'raise_topic_priority')"><Search class="h-3.5 w-3.5" />深挖</button><button type="button" class="decision-btn decision-btn--reject" :disabled="feedbackingId === item.id" @click="sendFeedback(item, 'not_relevant', 'lower_item_score')"><XCircle class="h-3.5 w-3.5" />不相关</button></div>
              </article>
            </div>
          </section>
        </section>
      </main>
    </div>
  </div>
</template>

<style scoped>
.content-loop-shell { --loop-bg:#f6f4ef; --loop-paper:rgba(255,253,248,.88); --loop-ink:#20221f; --loop-muted:#62665e; --loop-line:rgba(92,84,70,.2); --loop-green:#0f7b65; --loop-blue:#225c9d; background:var(--loop-bg); color:var(--loop-ink); }
.content-loop-hero,.loop-panel,.stat-tile,.content-loop-alert { border:1px solid var(--loop-line); border-radius:8px; background:var(--loop-paper); box-shadow:0 14px 34px rgba(42,38,29,.08); }
.content-loop-hero { display:grid; grid-template-columns:minmax(0,1fr) auto; gap:18px; padding:22px; }
.content-loop-mark { display:grid; width:36px; height:36px; place-items:center; border:1px solid rgba(15,123,101,.35); border-radius:50%; background:rgba(15,123,101,.12); color:var(--loop-green); }
.content-loop-kicker,.panel-label { color:var(--loop-muted); font-size:12px; font-weight:760; text-transform:uppercase; }
.content-loop-hero h1,.panel-head h2 { margin-top:8px; font-size:24px; font-weight:760; line-height:1.2; }
.content-loop-hero p,.muted { color:var(--loop-muted); }
.content-loop-actions,.mini-breakdown,.item-meta,.item-actions,.tag-filter-row,.item-tags,.content-loop-stats { display:flex; flex-wrap:wrap; gap:10px; }
.content-loop-stats { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); }
.stat-tile,.loop-panel { padding:16px; }
.content-loop-grid { display:grid; grid-template-columns:280px minmax(0,1fr); gap:16px; }
.stage-list { display:grid; gap:8px; margin-top:12px; }
.stage-btn,.loop-btn,.tag-filter-btn,.decision-btn { border:1px solid var(--loop-line); border-radius:8px; background:#fff; padding:8px 12px; }
.stage-btn--active,.tag-filter-btn--active { background:rgba(15,123,101,.12); border-color:rgba(15,123,101,.35); }
.loop-btn,.decision-btn,.tag-filter-btn { display:inline-flex; align-items:center; gap:6px; }
.item-list { display:grid; gap:12px; }
.content-item { display:grid; grid-template-columns:minmax(0,1fr) auto; gap:12px; padding:12px 0; border-top:1px solid var(--loop-line); }
.content-item:first-child { border-top:none; }
.item-tags span,.file-chip,.stage-index { border:1px solid var(--loop-line); border-radius:999px; padding:2px 8px; font-size:12px; }
.empty-state { display:flex; align-items:center; gap:8px; color:var(--loop-muted); }
.item-link { display:inline-flex; align-items:center; gap:6px; color:var(--loop-blue); }
.content-item--highlighted { background: rgba(15,123,101,.10); border-radius: 8px; padding-inline: 12px; }
</style>
