// 后端 API 封装
const BASE = '/api'

async function request(path, options = {}) {
  const resp = await fetch(`${BASE}${path}`, options)
  let data = null
  try {
    data = await resp.json()
  } catch {
    // 非 JSON 响应
  }
  if (!resp.ok) {
    throw new Error((data && data.detail) || `请求失败（${resp.status}）`)
  }
  return data
}

export const api = {
  // 会话
  listConversations: () => request('/conversations'),
  createConversation: () => request('/conversations', { method: 'POST' }),
  getConversation: (id) => request(`/conversations/${encodeURIComponent(id)}`),
  deleteConversation: (id) =>
    request(`/conversations/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  // 聊天
  chat: (payload) =>
    request('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
}
