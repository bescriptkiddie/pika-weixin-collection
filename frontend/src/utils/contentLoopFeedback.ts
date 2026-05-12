export function wechatContentItemId(articleId: string) {
  return `wechat_article:${articleId}`
}

export async function recordContentFeedback(payload: {
  item_id: string
  event: string
  human_decision: string
  feedback_note?: string
  suggested_action?: string
  channel?: string
  weight?: number
}) {
  try {
    await fetch('/api/content-loop/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        channel: 'local_web',
        weight: 1,
        ...payload,
      }),
    })
  } catch {
    // 反馈回写不能阻塞阅读主路径；内容闭环页会暴露后端连接状态。
  }
}
