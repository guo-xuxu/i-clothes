<script setup>
import { nextTick, ref, watch } from 'vue'
import ChatInput from './ChatInput.vue'
import MessageItem from './MessageItem.vue'

const props = defineProps({
  title: { type: String, default: '新对话' },
  messages: { type: Array, default: () => [] },
  sending: { type: Boolean, default: false },
})
const emit = defineEmits(['send'])

const listEl = ref(null)

watch(
  () => props.messages.length,
  async () => {
    await nextTick()
    if (listEl.value) {
      listEl.value.scrollTop = listEl.value.scrollHeight
    }
  }
)
</script>

<template>
  <section class="chat-panel">
    <header class="chat-header">
      <span class="chat-title">{{ title }}</span>
      <span class="chat-subtitle">拍照或文字描述，即可获得个性化穿搭建议；也可以随意闲聊</span>
    </header>

    <div ref="listEl" class="message-list">
      <div v-if="!messages.length" class="empty-state">
        <div class="empty-icon">🧥</div>
        <div class="empty-title">开始你的穿搭之旅</div>
        <div>可以上传照片，也可以直接告诉我你的需求，比如“帮我推荐上班通勤的穿搭”</div>
      </div>
      <MessageItem v-for="(m, i) in messages" :key="i" :message="m" />
    </div>

    <div class="chat-input-area">
      <ChatInput :sending="sending" @send="emit('send', $event)" />
    </div>
  </section>
</template>
