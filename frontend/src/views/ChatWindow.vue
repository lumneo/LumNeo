<template>
  <div class="app-container" :class="[configStore.themeMode]">
    <!-- 移动端侧边栏遮罩 -->
    <div v-if="isMobile && sidebarOpen" class="sidebar-overlay" @click="sidebarCollapsed = true; sidebarOpen = false"></div>

    <!-- ========== 侧边栏（折叠式） ========== -->
     <Transition name="sidebar">
      <aside v-if="!sidebarCollapsed" class="sidebar-panel border-marquee-right" :class="{ collapsed: sidebarCollapsed, 'sidebar-open': sidebarOpen }">
        <div class="sidebar-header">
          <span class="logo-text"><m-svg name="star" style="position: absolute;left:120px;top:18px;"/>✨ LumNeo</span>
          <n-button v-if="!isMobile" text class="icon-btn" @click="sidebarCollapsed = true" title="收起侧栏">
            <template #icon>
              <n-icon :size="22">
                <m-svg name="expand"/>
              </n-icon>
            </template>
          </n-button>
        </div>
        <div class="btn-main">
          <n-button block strong secondary size="large" class="new-chat-btn" @click="createChat">
            <template #icon><m-svg name="add"/></template>
            创建新对话
          </n-button>
        </div>
        <n-scrollbar content-style="padding:0 16px" style="max-height: calc(100vh - 200px);">
          <n-list hoverable clickable :show-divider="false">
            <n-list-item v-for="chat in chatStore.chats" :key="chat.id"
              @click="openChat(chat.id)"
              :class="{ active: chat.id === chatStore.activeChatId }">
              <div class="chat-item-row">
                <div class="chat-title" v-if="renamingChatId !== chat.id">
                  {{ chat.title }}
                </div>
                <n-input v-else
                  v-model:value="renameText"
                  size="small"
                  autofocus
                  @blur="confirmRename(chat.id)"
                  @keydown.enter="confirmRename(chat.id)"
                  placeholder="请输入标题"
                />
                <div class="chat-actions" v-if="renamingChatId !== chat.id">
                  <n-button text size="tiny" @click.stop="startRename(chat)" title="重命名">
                    <template #icon><n-icon :size="16"><m-svg name="edit"/></n-icon></template>
                  </n-button>
                  <n-popconfirm
                    @positive-click="() => chatStore.deleteChat(chat.id)"
                    negative-text="取消"
                    positive-text="好的"
                    :negative-button-props="{size: 'tiny'}"
                    :positive-button-props="{size: 'tiny'}"
                  >
                    <template #trigger>
                      <n-button text size="tiny" @click.stop title="删除">
                        <template #icon><n-icon :size="16"><m-svg name="del"/></n-icon></template>
                      </n-button>
                    </template>
                    确定删除整个对话「{{ chat.title }}」吗？
                  </n-popconfirm>
                </div>
              </div>
            </n-list-item>
          </n-list>
        </n-scrollbar>
        <div class="sidebar-footer">
          <n-button text @click="showSettings = true">
            <template #icon>
              <n-icon><SettingsOutline /></n-icon>
            </template>
            系统设置
          </n-button>
        </div>
      </aside>
    </Transition>

    <!-- ========== 主区域 ========== -->
    <main
      class="main-stage"
      :style="{
        paddingLeft: (!isMobile && !sidebarCollapsed) ? '260px' : '0'
      }"
      @dragenter="onDragEnter($event, isLoading)"
      @dragover="onDragOver"
      @dragleave="onDragLeave"
      @drop="onDrop($event, chatStore.activeChatId, isLoading)"
    >
      <div v-if="isDragging && chatStore.activeChatId" class="drag-overlay">
        <div class="drag-hint"><n-icon><DocumentOutline /></n-icon> 释放文件以上传</div>
      </div>

      <!-- 顶部工具栏 -->
      <header v-if="chatStore.activeChatId" class="top-bar" :class="[sidebarCollapsed || isMobile ? 'border-marquee-center' : '']">
        <n-flex style="width:100%" justify="space-between">
          <n-flex>
            <n-button v-if="isMobile" text @click="sidebarOpen = !sidebarOpen; sidebarCollapsed = !sidebarCollapsed">
              <template #icon><n-icon><MenuOutline /></n-icon></template>
            </n-button>
            <n-button v-if="!isMobile && sidebarCollapsed" text class="icon-btn" @click="sidebarCollapsed = !sidebarCollapsed" title="展开侧栏">
              <template #icon>
                <n-icon :size="22">
                  <m-svg name="expand"/>
                </n-icon>
              </template>
            </n-button>
            <div class="model-badge">
              <n-select
                v-model:value="activeModelId"
                :options="modelOptions"
                size="small"
                style="width: 120px"
                placeholder="选择模型"
                @update:value="switchActiveModel"
              />
            </div>
            <div class="toolbar-right">
              <n-select
                v-if="chatStore.enableProfile"
                v-model:value="profileStore.activeProfileId"
                :options="profileOptions"
                size="small"
                placeholder="选择角色"
                style="width: 150px; margin-right: 12px;"
                clearable
              />
            </div>
          </n-flex>
          <n-popover
            v-if="showQRCode"
            placement="bottom"
            trigger="hover"
          >
            <template #trigger>
              <n-button text>
                <template #icon>
                  <n-icon><QrCodeOutline /></n-icon>
                </template>
              </n-button>
            </template>
            <div style="text-align:center;font-size:14px;">
              <n-qr-code :value="qrCodeUrl" />
              <div style="margin-top:4px">移动设备扫码开启对话</div>
            </div>
          </n-popover>
        </n-flex>
      </header>

      <!-- 消息列表组件 -->
      <MessageList
        ref="messageListRef"
        v-if="chatStore.activeChatId"
        :chat-id="chatStore.activeChatId"
        :messages="currentMessages"
        :is-mobile="isMobile"
        :is-loading="isLoading"
        :streaming-content="streamingContent"
        :regenerating-msg="regeneratingMsg"
        :is-dark="isDark"
        :show-welcome="showWelcome"
        :copy-svg-name="copySvgName"
        @copy="copyContent"
        @regenerate="handleRegenerateResponse"
        @edit="startEditMessage"
        @delete="chatStore.deleteMessage"
      />

      <!-- 无对话时的引导页 -->
      <div v-else class="introduction">
        <Introduction v-if="isRender" @click="sidebarOpen=true;sidebarCollapsed=false" />
      </div>

      <!-- 聊天输入框组件 -->
      <ChatInput
        v-if="chatStore.activeChatId"
        v-model="currentInput"
        v-model:selected="selected"
        v-model:file-list="uploadFileList"
        :is-loading="isLoading"
        :disabled="isLoading || !chatStore.activeChatId || !activeModelId"
        :uploaded-files="uploadedFiles"
        :show-scroll-btn="messageListRef?.showScrollBtn"
        :show-regenerate-hint="!isLoading && currentMessages.length >= 1 && currentMessages[currentMessages.length - 1]?.role === 'user'"
        :show-deep-think="configStore.activeModel?.type === 'online'"
        :max-files="fileConfig.max"
        :file-accept="fileConfig.accept"
        :before-upload="onBeforeUpload"
        @send="onSendMessage"
        @stop="stopGeneration"
        @scroll-bottom="messageListRef?.scrollToLatestSmooth()"
        @remove-file="removeFile"
        @regenerate-current="onRegenerateFromCurrentHistory"
        @files-paste="handlePasteFiles"
        @upload-change="handleFileUpload"
      />
    </main>

    <!-- 设置抽屉 -->
    <SettingsDrawer v-model:show="showSettings" />

    <!-- 编辑消息模态框 -->
    <n-modal v-model:show="showEditModal" preset="dialog" draggable :mask-closable="false" title="编辑消息" positive-text="保存" negative-text="取消"
      @positive-click="onSaveEdit">
      <n-input v-model:value="editContent" type="textarea" :autosize="{ minRows: 2, maxRows: 10 }" placeholder="请输入内容"/>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NButton, NInput, NList, NListItem, NIcon, NScrollbar, NFlex, NSelect, NModal, NPopconfirm, NPopover, NQrCode } from 'naive-ui'
import type { UploadFileInfo } from 'naive-ui'
import { SettingsOutline, DocumentOutline, MenuOutline, QrCodeOutline } from '@vicons/ionicons5'
import { useChatStore, type Message } from '@/stores/chat'
import { useConfigStore, fileConfig } from '@/stores/config'
import { useProfileStore } from '@/stores/profiles'
import SettingsDrawer from '@/components/SettingsDrawer.vue'
import Introduction from '@/components/Introduction.vue'
import mSvg from '@/components/MSvg.vue'
// import VirtualMessageList from '@/components/VirtualMessageList.vue'
import MessageList from '@/components/MessageList.vue'
import ChatInput from '@/components/ChatInput.vue'

import { useModel } from '@/composables/useModel'
import { useFileUpload } from '@/composables/useFileUpload'
import { useChat } from '@/composables/useChat'
import { useMessageActions } from '@/composables/useMessageActions'
import { localIP, uploadDir } from '@/utils/message'

const route = useRoute()
const router = useRouter()
const chatStore = useChatStore()
const configStore = useConfigStore()
const profileStore = useProfileStore()

const isMobile = ref(false)
const sidebarOpen = ref(false)
const qrCodeUrl = ref('')
const local_ip = ref('')
const showQRCode = ref(true)

const isDark = computed(() => configStore.themeMode === 'dark')

function checkMobile() {
  isMobile.value = window.innerWidth <= 768
  if (!isMobile.value) sidebarOpen.value = false
  showQRCode.value = !(/Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent) && 'ontouchstart' in window || navigator.maxTouchPoints > 0)
}

const selected = ref(localStorage.getItem('thinking') === 'true')

const { activeModelId, modelOptions, switchActiveModel } = useModel()
const { uploadFileList, uploadedFiles, isDragging, onDragEnter, onDragOver,
    onDragLeave, onDrop, onBeforeUpload, handleFileUpload, removeFile, clearFiles
} = useFileUpload()
const { currentInput, isLoading, streamingContent, regeneratingMsg,
    sendMessage, regenerateResponse, regenerateFromCurrentHistory, stopGeneration
} = useChat()
const { showEditModal, editContent, copySvgName, copyContent,
  startEditMessage, saveEdit, renamingChatId, renameText, startRename, confirmRename
} = useMessageActions()

const messageListRef = ref<InstanceType<typeof MessageList> | null>(null)

const currentMessages = computed(() => chatStore.currentChatMessages)

// 粘贴文件处理：由 ChatInput 发出 paste 事件，此处处理
function handlePasteFiles(files: File[]) {
  if (!chatStore.activeChatId || isLoading.value || !activeModelId.value) return

  // 过滤文件类型
  const acceptedFiles = files.filter(f => {
    const suffix = '.' + f.name.split('.').pop()?.toLowerCase()
    const acceptList = fileConfig.accept.split(',').map(s => s.trim())
    return acceptList.includes(suffix)
  })
  if (acceptedFiles.length === 0) return

  const remaining = fileConfig.max - uploadedFiles.value.length
  if (remaining <= 0) return

  const filesToAdd = acceptedFiles.slice(0, remaining)
  for (const file of filesToAdd) {
    let filename = file.name
    if (!filename || filename === 'image.png' || filename === 'blob' || filename === 'clipboard') {
      const ext = file.name.split('.').pop() || 'bin'
      const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)
      filename = `paste-${timestamp}-${Math.random().toString(36).slice(2, 6)}.${ext}`
    }

    const uploadFile: UploadFileInfo = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
      name: filename,
      status: 'pending',
      file: new File([file], filename, { type: file.type }),
    }
    uploadFileList.value.push(uploadFile)
  }

  handleFileUpload({ fileList: uploadFileList.value })
}

// 发送消息
const onSendMessage = () => {
  sendMessage(uploadedFiles.value, () => {
    messageListRef.value?.scrollToLatest()
  })
  clearFiles()
}

// 重新生成当前响应
const onRegenerateFromCurrentHistory = async () => {
  await regenerateFromCurrentHistory(() => {
    messageListRef.value?.scrollToLatest()
  })
}

// 重新生成特定消息
const handleRegenerateResponse = async (msg: Message) => {
  await regenerateResponse(msg, () => {
    messageListRef.value?.scrollToLatest()
  })
}

// 编辑后保存并重新生成
const onSaveEdit = async () => {
  await saveEdit(() => onRegenerateFromCurrentHistory())
}

// ========== 动效与初始化 ==========
const isRender = ref(false)

onMounted(async () => {
  checkMobile()
  let resizeTimer: ReturnType<typeof setTimeout>
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer)
    resizeTimer = setTimeout(() => {
      checkMobile()
    }, 150)
  })
  await profileStore.loadProfiles()
  fetch('/api/system-info').then(async (res) => {
    const data = await res.json()
    localIP.value = data.local_ip
    uploadDir.value = data.upload_dir
    setQRCodeUrl()
  })
  setTimeout(() => {
    isRender.value = true
  }, 150)
})

onUnmounted(() => {
  window.removeEventListener('resize', checkMobile)
})

const showWelcome = ref(false)

watch(() => route.params.id, (newId) => {
  if (isLoading.value) stopGeneration()
  chatStore.activeChatId = newId as string
}, { immediate: true })

// 切换对话或首次加载时，滚动到底部
watch(() => chatStore.activeChatId, async (newId) => {
  if (newId) {
    await chatStore.loadMessages(newId)
    showWelcome.value = currentMessages.value.length === 0
    await nextTick()
    await new Promise(resolve => requestAnimationFrame(resolve))
    if (!showWelcome.value) {
      messageListRef.value?.scrollToLatest()
    }
  } else {
    chatStore.loadChats()
  }
}, { immediate: true })

const sidebarCollapsed = ref(true)
const showSettings = ref(false)

const profileOptions = computed(() =>
  profileStore.profiles.map((p) => ({ label: p.name, value: p.id }))
)

function setQRCodeUrl() {
  qrCodeUrl.value = window.location.href.replace(/\b(?:localhost|\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b/g, local_ip.value)
}

const createChat = async () => {
  const newChatId = await chatStore.addChat()
  openChat(newChatId)
}

const openChat = (chatId: string) => {
  if (isLoading.value) stopGeneration()
  chatStore.activeChatId = chatId
  router.push({ name: 'chat', params: { id: chatId } })
  setTimeout(() => {
    setQRCodeUrl()
  }, 300)
}

watch(() => selected.value, (newVal) => {
  localStorage.setItem('thinking', newVal ? 'true' : 'false')
})
</script>

<style scoped>
/* ========== 全局布局 ========== */
.app-container {
  display: flex;
  height: 100vh;
  background: var(--bg-primary);
  color: var(--text-primary);
  font-family: 'Inter', 'Segoe UI', sans-serif;
  overflow: hidden;
  position: relative;
}

.sidebar-enter-active,
.sidebar-leave-active {
  transition: transform 0.3s ease;
}

.sidebar-enter-from,
.sidebar-leave-to {
  transform: translateX(-100%);
}

.sidebar-enter-to,
.sidebar-leave-from {
  transform: translateX(0);
}

/* ========== 侧边栏 ========== */
.sidebar-panel {
  position: absolute;
  top: 0;
  left: 0;
  height: 100%;
  width: 260px;
  background: var(--glass-bg);
  backdrop-filter: blur(12px);
  display: flex;
  flex-direction: column;
  padding: 16px 0;
  gap: 12px;
  overflow: hidden;
  z-index: 40;
  box-shadow: 2px 0 8px rgba(0,0,0,0.1);
}

.icon-btn {
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  transition: background 0.2s;
  color: var(--text-primary);
}
.icon-btn:hover, .icon-btn.active {
  background: rgba(74, 124, 247, 0.2);
  box-shadow: var(--shadow-glow);
}

.sidebar-header {
  display: flex;
  padding:0 16px;
  justify-content: space-between;
  align-items: center;
}
.logo-text {
  font-size: 1.2rem;
  font-weight: 700;
  background: var(--accent-gradient);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.collapse-btn {
  color: var(--text-secondary);
}
.btn-main {
  padding:0 16px;
}
.new-chat-btn {
  background: var(--accent-gradient) !important;
  border: none !important;
  color: white !important;
  font-weight: 600;
  text-align: center;
  border-radius: 20px;
  box-shadow: var(--shadow-glow);
  transition: transform 0.3s cubic-bezier(0.68, -0.55, 0.265, 1.55),
              box-shadow 0.3s ease,
              background 0.3s ease;
}
.new-chat-btn:hover {
  transform: scale(1.06);
  box-shadow: var(--shadow-glow);
  background: var(--accent-gradient) !important;
}
.new-chat-btn:active {
  transform: scale(1.02);
}
.sidebar-footer {
  position: fixed;
  bottom:40px; left:20px; right:0;
  z-index:100;
}

/* ========== 主区域 ========== */
.main-stage {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: var(--bg-secondary);
  width: 100%;
  box-sizing: border-box;
  transition: padding-left 0.3s ease;
}

.drag-overlay {
  position: absolute;
  inset: 0;
  background: rgba(99, 102, 241, 0.1);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
  border: 2px dashed var(--accent);
  border-radius: 12px;
  margin: 8px;
}
.drag-hint {
  font-size: 1.5rem;
  color: var(--accent);
  background: var(--bg-secondary);
  padding: 1rem 2rem;
  border-radius: 12px;
}

.top-bar {
  display: flex;
  height: 30px;
  justify-content: space-between;
  align-items: center;
  padding: 8px 20px;
  background: var(--glass-bg);
  backdrop-filter: blur(8px);
  border-bottom: var(--glass-border);
}
.model-badge {
  display: flex;
  gap: 8px;
  font-size: 0.85rem;
  color: var(--text-secondary);
}
.toolbar-right {
  display: flex;
  align-items: center;
}
.theme-toggle-btn {
  font-size: 1.2rem;
  color: var(--text-secondary);
}
.theme-toggle-btn:hover {
  color: var(--accent);
}

.introduction {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 16px;
}

.chat-item-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}
:deep(.n-list-item__main) {
    width: 100%;
}
.chat-title {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.chat-actions {
  position: absolute;
  right: 0;
  height: 100%;
  padding: 0 8px;
  border-radius: 0 12px 12px 0;
  vertical-align: middle;
  display: flex;
  gap: 6px;
  opacity: 0;
  transition: opacity 0.2s;
}
.n-list-item:hover .chat-actions {
  opacity: 1;
}
.dark .chat-actions {
  background: linear-gradient(90deg,rgba(44,44,46,0)0%,rgba(44,44,46,.5)20.23%,rgb(44,44,46)40.62%);
}
.light .chat-actions {
  background: linear-gradient(90deg,rgba(226, 226, 226, 0)0%,rgba(226, 226, 226,.5)20.23%,rgb(226, 226, 226)40.62%);
}
.dark .active .chat-actions {
  background: linear-gradient(90deg,rgba(22, 31, 49, 0)0%,rgba(22, 31, 49,.5)20.23%,rgb(22, 31, 49)40.62%);
}
.light .active .chat-actions {
  background: linear-gradient(90deg,rgba(219, 228, 245, 0)0%,rgba(219, 228, 245,.5)20.23%,rgb(219, 228, 245)40.62%);
}

.n-list {
  background-color: unset;
}
.n-list-item {
  margin-bottom:2px;
}

/* 列表激活样式 */
.n-list-item.active {
  background: rgba(74, 124, 247, 0.1) !important;
}
</style>