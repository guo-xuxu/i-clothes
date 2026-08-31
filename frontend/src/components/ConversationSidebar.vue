<script setup>
import { computed } from 'vue'
import { Delete, MagicStick, Plus, SwitchButton } from '@element-plus/icons-vue'

const props = defineProps({
  conversations: { type: Array, default: () => [] },
  activeId: { type: String, default: null },
  user: { type: Object, default: null },
})
const emit = defineEmits(['new', 'select', 'remove', 'logout'])

const userInitial = computed(() => {
  const name = props.user && props.user.username
  return name ? name.charAt(0).toUpperCase() : '?'
})

function formatTime(ts) {
  if (!ts) return ''
  const diff = Date.now() - ts * 1000
  const min = Math.floor(diff / 60000)
  if (min < 1) return '刚刚'
  if (min < 60) return `${min} 分钟前`
  const hour = Math.floor(min / 60)
  if (hour < 24) return `${hour} 小时前`
  const day = Math.floor(hour / 24)
  if (day < 7) return `${day} 天前`
  const d = new Date(ts * 1000)
  return `${d.getMonth() + 1}月${d.getDate()}日`
}

const items = computed(() =>
  props.conversations.map((c) => ({ ...c, timeText: formatTime(c.updated_at) }))
)
</script>

<template>
  <aside class="sidebar">
    <div class="sidebar-brand">
      <div class="brand-logo">
        <el-icon><MagicStick /></el-icon>
      </div>
      <div>
        <div class="brand-title">i-clothes</div>
        <div class="brand-subtitle">智能穿搭助手</div>
      </div>
    </div>

    <el-button
      class="sidebar-new-btn"
      type="primary"
      :icon="Plus"
      @click="emit('new')"
    >
      新建对话
    </el-button>

    <div class="conversation-list">
      <div
        v-for="c in items"
        :key="c.id"
        class="conversation-item"
        :class="{ active: c.id === activeId }"
        @click="emit('select', c.id)"
      >
        <span class="conv-title" :title="c.preview || c.title">{{ c.title }}</span>
        <span class="conv-time">{{ c.timeText }}</span>
        <el-icon
          class="conv-delete"
          @click.stop="emit('remove', c.id)"
        >
          <Delete />
        </el-icon>
      </div>
    </div>

    <div class="sidebar-footer">
      <div class="user-info" :title="user && user.username">
        <div class="user-avatar">{{ userInitial }}</div>
        <span class="user-name">{{ user ? user.username : '' }}</span>
      </div>
      <el-icon class="logout-btn" title="退出登录" @click="emit('logout')">
        <SwitchButton />
      </el-icon>
    </div>
  </aside>
</template>
