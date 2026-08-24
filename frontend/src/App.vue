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

  // 乐观更新：先显示用户消息
  messages.value.push({ role: 'user', content: text, images })
  try {
    const result = await api.chat({
      conversation_id: activeId.value,
      message: text,
      images,
    })
    // 新会话时绑定返回的会话 id
    if (result.conversation_id !== activeId.value) {
      activeId.value = result.conversation_id
    }
    activeTitle.value = result.title
    messages.value.push({
      role: 'assistant',
      content: result.reply,
      intent: result.intent,
    })
    await refreshList()
  } catch (e) {
    messages.value.push({
      role: 'assistant',
      content: `出错了：${e.message}`,
      intent: '',
    })
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
