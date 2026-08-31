<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import anime from 'animejs/lib/anime.es.js'
import { api, setAuth } from '../api'

const emit = defineEmits(['success'])

const mode = ref('login') // 'login' | 'register'
const username = ref('')
const password = ref('')
const confirm = ref('')
const loading = ref(false)

const cardRef = ref(null)
const bodyRef = ref(null)
const logoRef = ref(null)

function switchMode(m) {
  if (mode.value === m) return
  mode.value = m
  confirm.value = ''
  // 切换时表单内容做一次淡入上移
  anime({
    targets: bodyRef.value,
    opacity: [0, 1],
    translateY: [12, 0],
    duration: 450,
    easing: 'easeOutCubic',
  })
}

async function submit() {
  const name = username.value.trim()
  if (!name || !password.value) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  if (mode.value === 'register' && password.value !== confirm.value) {
    ElMessage.warning('两次输入的密码不一致')
    return
  }
  loading.value = true
  try {
    if (mode.value === 'register') {
      await api.register(name, password.value)
      ElMessage.success('注册成功，正在登录…')
    }
    const resp = await api.login(name, password.value)
    setAuth(resp.token, resp.user)
    emit('success', resp.user)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  // 卡片入场：上移 + 淡入
  anime({
    targets: cardRef.value,
    translateY: [56, 0],
    opacity: [0, 1],
    duration: 1100,
    easing: 'easeOutCubic',
  })
  // 背景光斑缓慢漂浮
  anime({
    targets: '.blob',
    translateX: [0, 70],
    translateY: [0, -50],
    scale: [1, 1.18],
    duration: 16000,
    direction: 'alternate',
    loop: true,
    easing: 'easeInOutSine',
    delay: anime.stagger(300),
  })
  // logo 呼吸
  anime({
    targets: logoRef.value,
    scale: [1, 1.08, 1],
    duration: 3200,
    loop: true,
    easing: 'easeInOutSine',
  })
})
</script>

<template>
  <div class="login-page">
    <div class="bg-blobs">
      <span class="blob blob-1"></span>
      <span class="blob blob-2"></span>
      <span class="blob blob-3"></span>
    </div>

    <div ref="cardRef" class="login-card">
      <div class="login-brand">
        <div ref="logoRef" class="login-logo">
          <el-icon><MagicStick /></el-icon>
        </div>
        <div class="login-title">i-clothes</div>
        <div class="login-subtitle">智能穿搭助手</div>
      </div>

      <div class="mode-tabs">
        <button
          class="mode-tab"
          :class="{ active: mode === 'login' }"
          @click="switchMode('login')"
        >登录</button>
        <button
          class="mode-tab"
          :class="{ active: mode === 'register' }"
          @click="switchMode('register')"
        >注册</button>
      </div>

      <form ref="bodyRef" class="login-form" @submit.prevent="submit">
        <div class="field">
          <input
            v-model="username"
            type="text"
            placeholder=" "
            autocomplete="username"
          />
          <label>用户名</label>
          <span class="field-line"></span>
        </div>

        <div class="field">
          <input
            v-model="password"
            type="password"
            placeholder=" "
            autocomplete="current-password"
          />
          <label>密码</label>
          <span class="field-line"></span>
        </div>

        <div v-if="mode === 'register'" class="field">
          <input
            v-model="confirm"
            type="password"
            placeholder=" "
            autocomplete="new-password"
          />
          <label>确认密码</label>
          <span class="field-line"></span>
        </div>

        <button class="submit-btn" type="submit" :disabled="loading">
          {{ loading ? '请稍候…' : mode === 'login' ? '登录' : '注册并登录' }}
        </button>
      </form>

      <div class="login-hint">
        {{ mode === 'login' ? '还没有账号？点击上方「注册」' : '已有账号？点击上方「登录」' }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: radial-gradient(1200px 800px at 20% 10%, #fdfbf7 0%, #f7f1e9 55%, #efe8dd 100%);
  overflow: hidden;
}

.bg-blobs {
  position: absolute;
  inset: 0;
  overflow: hidden;
  pointer-events: none;
}

.blob {
  position: absolute;
  border-radius: 50%;
  filter: blur(90px);
  opacity: 0.55;
}

.blob-1 {
  width: 440px;
  height: 440px;
  background: #e8c9a8;
  top: -100px;
  left: -80px;
}

.blob-2 {
  width: 380px;
  height: 380px;
  background: #e3c4cd;
  bottom: -80px;
  right: -60px;
}

.blob-3 {
  width: 300px;
  height: 300px;
  background: #efe0cc;
  top: 42%;
  left: 62%;
  opacity: 0.38;
}

.login-card {
  position: relative;
  z-index: 1;
  width: 380px;
  max-width: calc(100vw - 40px);
  padding: 40px 36px 32px;
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.82);
  border: 1px solid #ede3d5;
  backdrop-filter: blur(22px);
  -webkit-backdrop-filter: blur(22px);
  box-shadow: 0 24px 60px rgba(150, 110, 70, 0.14);
}

.login-brand {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  margin-bottom: 26px;
}

.login-logo {
  width: 60px;
  height: 60px;
  border-radius: 18px;
  background: linear-gradient(135deg, #c0814f, #c48b9f);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 30px;
  color: #fff;
  box-shadow: 0 12px 30px rgba(192, 129, 79, 0.35);
  margin-bottom: 8px;
}

.login-title {
  font-size: 26px;
  font-weight: 700;
  color: #3f3429;
  letter-spacing: 0.5px;
}

.login-subtitle {
  font-size: 13px;
  color: #9c8878;
}

.mode-tabs {
  display: flex;
  margin-bottom: 24px;
  background: #f4eee6;
  border-radius: 10px;
  padding: 4px;
}

.mode-tab {
  flex: 1;
  padding: 9px 0;
  border: none;
  background: transparent;
  color: #8a7a6b;
  font-size: 14px;
  cursor: pointer;
  border-radius: 8px;
  transition: all 0.25s;
}

.mode-tab.active {
  background: linear-gradient(135deg, #c0814f, #c48b9f);
  color: #fff;
  font-weight: 600;
  box-shadow: 0 4px 14px rgba(192, 129, 79, 0.3);
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.field {
  position: relative;
}

.field input {
  width: 100%;
  padding: 22px 16px 10px;
  background: #fbf9f6;
  border: 1px solid #e5ddd2;
  border-radius: 12px;
  color: #3f3429;
  font-size: 15px;
  outline: none;
  transition: border-color 0.2s, background 0.2s;
}

.field input:focus {
  border-color: #c0814f;
  background: #fff;
}

.field label {
  position: absolute;
  left: 16px;
  top: 16px;
  color: #9c8878;
  font-size: 15px;
  pointer-events: none;
  transition: all 0.2s;
}

.field input:focus + label,
.field input:not(:placeholder-shown) + label {
  top: 7px;
  font-size: 11px;
  color: #c48b9f;
}

.field-line {
  position: absolute;
  bottom: 0;
  left: 50%;
  width: 76%;
  height: 2px;
  transform: translateX(-50%) scaleX(0);
  background: linear-gradient(90deg, #c0814f, #c48b9f);
  transition: transform 0.3s;
}

.field input:focus ~ .field-line {
  transform: translateX(-50%) scaleX(1);
}

.submit-btn {
  width: 100%;
  padding: 13px;
  border: none;
  border-radius: 12px;
  background: linear-gradient(135deg, #c0814f, #c48b9f);
  color: #fff;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  margin-top: 6px;
  transition: transform 0.15s, box-shadow 0.25s;
}

.submit-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 10px 28px rgba(192, 129, 79, 0.35);
}

.submit-btn:active:not(:disabled) {
  transform: translateY(0);
}

.submit-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.login-hint {
  margin-top: 20px;
  text-align: center;
  font-size: 12px;
  color: #9c8878;
}
</style>
