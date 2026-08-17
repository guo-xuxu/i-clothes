<script setup>
import { ref } from 'vue'
import { Picture, Promotion } from '@element-plus/icons-vue'

const props = defineProps({
  sending: { type: Boolean, default: false },
})
const emit = defineEmits(['send'])

const MAX_FILES = 3
const MAX_SIZE_MB = 5

const text = ref('')
const images = ref([]) // data URL 列表
const fileInput = ref(null)

function autoResize(e) {
  const el = e.target
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 120) + 'px'
}

function onPickImage() {
  fileInput.value?.click()
}

function onFileChange(e) {
  const files = Array.from(e.target.files || [])
  e.target.value = ''
  for (const file of files) {
    if (images.value.length >= MAX_FILES) break
    if (!['image/jpeg', 'image/png'].includes(file.type)) {
      continue
    }
    if (file.size > MAX_SIZE_MB * 1024 * 1024) {
      continue
    }
    const reader = new FileReader()
    reader.onload = () => images.value.push(reader.result)
    reader.readAsDataURL(file)
  }
}

function removeImage(index) {
  images.value.splice(index, 1)
}

function send() {
  const content = text.value.trim()
  if ((!content && !images.value.length) || props.sending) return
  emit('send', { text: content, images: [...images.value] })
  text.value = ''
  images.value = []
}
</script>

<template>
  <div class="chat-input-box">
    <textarea
      v-model="text"
      placeholder="输入消息，Enter 发送，Shift+Enter 换行；可附加照片获取穿搭建议"
      rows="1"
      @input="autoResize"
      @keydown.enter.exact.prevent="send"
    ></textarea>
    <div class="input-toolbar">
      <div class="input-attach">
        <el-button
          text
          :icon="Picture"
          title="添加照片（最多 3 张，JPG/PNG）"
          @click="onPickImage"
        />
        <input
          ref="fileInput"
          type="file"
          accept="image/jpeg,image/png"
          multiple
          hidden
          @change="onFileChange"
        />
        <div class="attach-thumbs">
          <div
            v-for="(url, i) in images"
            :key="i"
            class="attach-thumb"
          >
            <img :src="url" alt="待发送图片" />
            <span class="remove-thumb" @click="removeImage(i)">×</span>
          </div>
        </div>
        <span v-if="images.length" class="input-hint">{{ images.length }}/{{ MAX_FILES }}</span>
      </div>
      <el-button
        type="primary"
        :icon="Promotion"
        :loading="sending"
        :disabled="(!text.trim() && !images.length) || sending"
        @click="send"
      >
        发送
      </el-button>
    </div>
  </div>
</template>
