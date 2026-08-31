// 后端 API 封装
const BASE = '/api'
const TOKEN_KEY = 'iclothes_token'
const USER_KEY = 'iclothes_user'

// ---- 认证态管理（token + 用户信息，存 localStorage）----
export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}
export function getStoredUser() {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY))
  } catch {
    return null
  }
}
export function setAuth(token, user) {
  localStorage.setItem(TOKEN_KEY, token)
  if (user) localStorage.setItem(USER_KEY, JSON.stringify(user))
}
export function clearAuth() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

// 401 统一回调：由 App 注册，用于跳回登录页
let onUnauthorized = null
export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn
}

async function request(path, options = {}) {
  const headers = { ...(options.headers || {}) }
  const token = getToken()
  if (token) headers['Authorization'] = `Bearer ${token}`
  const resp = await fetch(`${BASE}${path}`, { ...options, headers })
  let data = null
  try {
    data = await resp.json()
  } catch {
    // 非 JSON 响应
  }
  // 401：auth 接口的 401 属于"账密错误"，不触发全局跳转；其余接口视为登录失效
  if (resp.status === 401 && !path.startsWith('/auth/') && onUnauthorized) {
    onUnauthorized()
  }
  if (!resp.ok) {
    throw new Error((data && data.detail) || `请求失败（${resp.status}）`)
  }
  return data
}

export const api = {
  // 认证
  register: (username, password) =>
    request('/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    }),
  login: (username, password) =>
    request('/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    }),
  me: () => request('/auth/me'),

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

  /**
   * 流式聊天（SSE）：返回异步生成器，逐个产出事件对象：
   *   { delta }                      逐 token
   *   { conversation_id, title }     会话元数据（流结束前）
   *   { done: true, intent }         结束
   * 中途错误 throw Error(detail)。
   */
  async *streamChat(payload) {
    const headers = { 'Content-Type': 'application/json' }
    const token = getToken()
    if (token) headers['Authorization'] = `Bearer ${token}`
    const resp = await fetch(`${BASE}/chat/stream`, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    })
    if (resp.status === 401 && onUnauthorized) {
      onUnauthorized()
    }
    if (!resp.ok || !resp.body) {
      let detail = ''
      try {
        detail = (await resp.json()).detail || ''
      } catch {
        /* 非 JSON 响应 */
      }
      throw new Error(detail || `请求失败（${resp.status}）`)
    }
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    let sawDone = false
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      let idx
      while ((idx = buf.indexOf('\n\n')) !== -1) {
        const block = buf.slice(0, idx)
        buf = buf.slice(idx + 2)
        // 兼容 "data: {...}"（Python）与 "data:{...}"（Spring SseEmitter，无空格）
        const line = block.split('\n').find((l) => l.trimStart().startsWith('data:'))
        if (!line) continue
        let ev
        try {
          ev = JSON.parse(line.slice(line.indexOf(':') + 1).trim())
        } catch {
          continue
        }
        if (ev.delta != null) yield { delta: ev.delta }
        else if (ev.conversation_id != null) yield { conversation_id: ev.conversation_id, title: ev.title }
        else if (ev.done === true) {
          sawDone = true
          yield { done: true, intent: ev.intent }
        } else if (ev.error) throw new Error(ev.error)
      }
    }
    if (!sawDone) throw new Error('流式响应未正常结束')
  },
}
