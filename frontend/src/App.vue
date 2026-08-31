<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import ConversationSidebar from './components/ConversationSidebar.vue'
import ChatWindow from './components/ChatWindow.vue'
import { api } from './api'

const conversations = ref([])
const activeId = ref(null)
const activeTitle = ref('新对话')
const messages = ref([])
const sending = ref(false)

async function refreshList() {
  conversations.value = await api.listConversations()
}

async function loadConversation(id) {
  const detail = await api.getConversation(id)
  activeTitle.value = detail.title
  messages.value = detail.messages
}

async function selectConversation(id) {
  if (id === activeId.value) return
  activeId.value = id
  try {
    await loadConversation(id)
  } catch (e) {
    ElMessage.error(e.message)
    await refreshList()
  }
}

async function createNew() {
  try {
    const conv = await api.createConversation()
    await refreshList()
    activeId.value = conv.id
    activeTitle.value = conv.title
    messages.value = []
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function removeConversation(id) {
  try {
    await ElMessageBox.confirm('确定删除这个对话吗？', '删除会话', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return // 用户取消
  }
  try {
    await api.deleteConversation(id)
    if (id === activeId.value) {
      activeId.value = null
      activeTitle.value = '新对话'
      messages.value = []
    }
    await refreshList()
    if (!conversations.value.length) {
      await createNew()
    }
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function handleSend({ text, images }) {
  if (sending.value) return
  sending.value = true

  // 乐观更新：先显示用户消息，再放一个流式占位气泡
  messages.value.push({ role: 'user', content: text, images })
  messages.value.push({ role: 'assistant', content: '', intent: '', streaming: true })
  // 必须通过 reactive 数组访问更新，直接改原始对象不会触发 Vue 响应式更新（文字会"卡在光标"）
  const lastIdx = messages.value.length - 1
  try {
    let full = ''
    let intent = 'chat'
    let gotMeta = false
    for await (const ev of api.streamChat({
      conversation_id: activeId.value,
      message: text,
      images,
    })) {
      if (ev.delta != null) {
        full += ev.delta
        messages.value[lastIdx].content = full
      } else if (ev.conversation_id != null) {
        gotMeta = true
        if (ev.conversation_id !== activeId.value) {
          activeId.value = ev.conversation_id // 新会话绑定返回的会话 id
        }
        if (ev.title) activeTitle.value = ev.title
      } else if (ev.done) {
        intent = ev.intent
      }
    }
    messages.value[lastIdx].streaming = false
    messages.value[lastIdx].intent = intent
    messages.value[lastIdx].content = full || '(空回复)'
    if (!gotMeta) {
      // 兜底：没收到元数据事件也刷新列表（会话已在服务端创建）
      activeId.value = null
    }
    await refreshList()
  } catch (e) {
    messages.value[lastIdx].streaming = false
    messages.value[lastIdx].content = `出错了：${e.message}`
    messages.value[lastIdx].intent = ''
  } finally {
    sending.value = false
  }
}

onMounted(async () => {
  try {
    await refreshList()
    if (conversations.value.length) {
      await selectConversation(conversations.value[0].id)
    } else {
      await createNew()
    }
  } catch (e) {
    ElMessage.error(e.message)
  }
})
</script>

<template>
  <div class="app-layout">
    <ConversationSidebar
      :conversations="conversations"
      :active-id="activeId"
      @new="createNew"
      @select="selectConversation"
      @remove="removeConversation"
    />
    <ChatWindow
      :title="activeTitle"
      :messages="messages"
      :sending="sending"
      @send="handleSend"
    />
  </div>
</template>
