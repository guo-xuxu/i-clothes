<script setup>
import { computed } from 'vue'
import { MagicStick, User } from '@element-plus/icons-vue'

const props = defineProps({
  message: { type: Object, required: true },
})

const isUser = computed(() => props.message.role === 'user')
const showIntent = computed(
  () => !isUser.value && props.message.intent && props.message.intent.length > 0
)

function formatTime(ts) {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  const pad = (n) => String(n).padStart(2, '0')
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`
}
</script>

<template>
  <div class="message-row" :class="isUser ? 'user' : 'assistant'">
    <div class="message-avatar" :class="isUser ? 'user' : 'assistant'">
      <el-icon :size="17">
        <User v-if="isUser" />
        <MagicStick v-else />
      </el-icon>
    </div>
    <div class="message-body">
      <div v-if="message.images && message.images.length" class="message-images">
        <img
          v-for="(url, i) in message.images"
          :key="i"
          :src="url"
          alt="附件"
        />
      </div>
      <div class="message-bubble">{{ message.content }}</div>
      <div class="message-meta">
        <el-tag
          v-if="showIntent"
          :type="message.intent === 'recommend' ? 'primary' : 'info'"
          size="small"
          effect="light"
        >
          {{ message.intent === 'recommend' ? '穿搭模式' : '对话模式' }}
        </el-tag>
        <span>{{ formatTime(message.created_at) }}</span>
      </div>
    </div>
  </div>
</template>
