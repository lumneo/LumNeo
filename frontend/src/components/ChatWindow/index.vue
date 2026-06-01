<template>
  <n-config-provider :theme="naiveTheme" :theme-overrides="themeOverrides">
    <n-message-provider>
      <div class="app-container" :class="[configStore.themeMode]">
        <!-- 移动端遮罩 -->
        <div v-if="isMobile && sidebarOpen" class="sidebar-overlay" @click="sidebarOpen = false"></div>

        <!-- ========== 侧边栏（折叠式） ========== -->
        <aside v-show="!sidebarCollapsed" class="sidebar-panel border-marquee-right" :class="{ collapsed: sidebarCollapsed, 'sidebar-open': sidebarOpen }">
          <div class="sidebar-header">
            <span class="logo-text">✨ LumNeo</span>
            <n-button v-if="!isMobile" text class="icon-btn" @click="sidebarCollapsed = true" title="收起侧栏">
              <template #icon><n-icon :size="22"><m-svg name="expand"/></n-icon></template>
            </n-button>
          </div>
          <div class="btn-main">
            <n-button block strong secondary size="large" class="new-chat-btn" @click="createChat">
              <template #icon><m-svg name="add"/></template> 创建新对话
            </n-button>
          </div>
          <n-scrollbar content-style="padding:0 16px" style="max-height: calc(100vh - 220px);">
            <n-list hoverable clickable :show-divider="false">
              <n-list-item v-for="chat in chatStore.chats" :key="chat.id" @click="openChat(chat.id)" :class="{ active: chat.id === chatStore.activeChatId }">
                <div class="chat-item-row">
                  <div class="chat-title" v-if="renamingChatId !== chat.id">{{ chat.title }}</div>
                  <n-input v-else v-model:value="renameText" size="small" autofocus @blur="confirmRename(chat.id)" @keydown.enter="confirmRename(chat.id)" placeholder="请输入标题" />
                  <div class="chat-actions" v-if="renamingChatId !== chat.id">
                    <n-button text size="tiny" @click.stop="startRename(chat)" title="重命名">
                      <template #icon><n-icon :size="16"><m-svg name="edit"/></n-icon></template>
                    </n-button>
                    <n-popconfirm @positive-click="() => chatStore.deleteChat(chat.id)" negative-text="取消" positive-text="好的" :negative-button-props="{size: 'tiny'}" :positive-button-props="{size: 'tiny'}">
                      <template #trigger>
                        <n-button text size="tiny" @click.stop title="删除"><template #icon><n-icon :size="16"><m-svg name="del"/></n-icon></template></n-button>
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
              <template #icon><n-icon><SettingsOutline /></n-icon></template> 系统设置
            </n-button>
          </div>
        </aside>

        <!-- ========== 主区域 ========== -->
        <main class="main-stage" :class="{ 'main-stage--full': sidebarCollapsed }" @dragenter="onDragEnter($event, isLoading)" @dragover="onDragOver" @dragleave="onDragLeave" @drop="onDrop($event, chatStore.activeChatId, isLoading)">
          <div v-if="isDragging && chatStore.activeChatId" class="drag-overlay">
            <div class="drag-hint"><n-icon><DocumentOutline /></n-icon> 释放文件以上传</div>
          </div>

          <!-- 顶部工具栏 -->
          <header v-if="chatStore.activeChatId" class="top-bar" :class="[sidebarCollapsed || isMobile ? 'border-marquee-center' : '']">
            <n-flex style="width:100%" justify="space-between">
              <n-flex>
                <n-button v-if="isMobile" text @click="sidebarOpen = !sidebarOpen;sidebarCollapsed=false"><template #icon><n-icon><MenuOutline /></n-icon></template></n-button>
                <n-button v-if="!isMobile && sidebarCollapsed" text class="icon-btn" @click="sidebarCollapsed = false" title="展开侧栏"><template #icon><n-icon :size="22"><m-svg name="expand"/></n-icon></template></n-button>
                <div class="model-badge">
                  <n-select v-model:value="activeModelId" :options="modelOptions" size="small" style="width: 120px" placeholder="选择模型" @update:value="switchActiveModel" />
                </div>
                <div class="toolbar-right">
                  <n-select v-if="chatStore.enableProfile" v-model:value="profileStore.activeProfileId" :options="profileOptions" size="small" placeholder="选择角色" style="width: 150px; margin-right: 12px;" clearable />
                </div>
              </n-flex>
              <n-popover v-if="showQRCode" placement="bottom" trigger="hover">
                <template #trigger>
                  <n-button text><template #icon><n-icon><QrCodeOutline /></n-icon></template></n-button>
                </template>
                <div style="text-align:center;font-size:14px;">
                  <n-qr-code :value="qrCodeUrl" />
                  <div style="margin-top:4px">移动设备扫码开启对话</div>
                </div>
              </n-popover>
            </n-flex>
          </header>

          <!-- ========== 虚拟滚动消息容器 ========== -->
          <div class="message-container" ref="messageListRef">
            <div class="introduction" v-if="!chatStore.activeChatId">
              <Introduction v-if="isRender" @click="sidebarOpen=true;sidebarCollapsed=false" />
            </div>
            <div class="message-main" v-else>
              <div v-if="showWelcome && currentMessages.length === 0">
                <svgWelcomeDark v-if="configStore.themeMode === 'dark'" />
                <svgWelcomeLight v-else />
              </div>

              <!-- 虚拟列表容器 -->
              <div ref="virtualContainer" class="virtual-scroller" style="overflow-y: auto; height: 100%;">
                <div :style="{ height: `${virtualizer.getTotalSize()}px`, width: '100%', position: 'relative' }">
                  <div
                    v-for="row in virtualizer.getVirtualItems()"
                    :key="virtualItems[row.index].id"
                    :style="{
                      position: 'absolute',
                      top: 0,
                      left: 0,
                      width: '100%',
                      transform: `translateY(${row.start}px)`,
                    }"
                  >
                    <div class="message-row" :class="virtualItems[row.index].role">
                      <div class="bubble" :class="{ 'has-file': virtualItems[row.index].file_ref }">
                        <!-- 文件附件 -->
                        <div v-if="normalizeFileRef(virtualItems[row.index].file_ref).length" class="message-files">
                          <div v-for="f in normalizeFileRef(virtualItems[row.index].file_ref)" :key="f.filename" class="msg-file-item">
                            <n-image v-if="f.type.startsWith('image/')" width="200" :src="f.url" class="msg-file-img" />
                            <div v-else class="msg-file-other">
                              <n-icon><DocumentOutline /></n-icon>
                              <a :href="f.url" target="_blank">{{ f.filename }}</a>
                            </div>
                          </div>
                        </div>

                        <!-- 用户消息 -->
                        <template v-if="virtualItems[row.index].role === 'user'">
                          <div class="message-content user-content" v-text="virtualItems[row.index].content.trim()"></div>
                        </template>

                        <!-- 助手消息（包括流式中的临时气泡） -->
                        <template v-else>
                          <template v-if="virtualItems[row.index].id === 'streaming'">
                            <!-- 流式输出中的临时气泡 -->
                            <div class="bubble streaming" v-html="streamDisplayHtml" v-if="streamDisplayHtml"></div>
                            <svgLoading v-else />
                          </template>
                          <template v-else>
                            <!-- 如果是正在重新生成的消息，只渲染占位 -->
                            <template v-if="virtualItems[row.index] === regeneratingMsg">
                              <div style="height: 1px;"></div>
                            </template>
                            <template v-else>
                              <div class="message-content" v-html="virtualItems[row.index].renderedHtml || renderMessageHtml(virtualItems[row.index].content.trim(), false)" @click="onContainerClick"></div>
                            </template>
                          </template>
                        </template>

                        <!-- 操作按钮 -->
                        <div :class="`message-actions ${virtualItems[row.index].role === 'assistant' ? 'assistant-actions' : 'user-actions'}`" v-if="!isLoading || virtualItems[row.index] !== regeneratingMsg">
                          <n-button text class="icon-btn" size="small" @click="copyContent(virtualItems[row.index])" title="复制">
                            <template #icon><n-icon><m-svg :name="copySvgName" /></n-icon></template>
                          </n-button>
                          <n-button v-if="virtualItems[row.index].role === 'assistant' && row.index === virtualItems.length - 1" text class="icon-btn" size="small" @click="handleRegenerateResponse(virtualItems[row.index])" title="重新生成">
                            <template #icon><n-icon ><m-svg name="refresh"/></n-icon></template>
                          </n-button>
                          <n-button text class="icon-btn" size="small" @click="startEditMessage(virtualItems[row.index])" title="编辑">
                            <template #icon><n-icon :size="20"><m-svg name="edit"/></n-icon></template>
                          </n-button>
                          <n-popconfirm @positive-click="() => chatStore.deleteMessage(virtualItems[row.index].id!)" negative-text="取消" positive-text="好的" :negative-button-props="{size: 'tiny'}" :positive-button-props="{size: 'tiny'}">
                            <template #trigger>
                              <n-button text class="icon-btn" size="small" title="删除"><template #icon><n-icon :size="22"><m-svg name="del"/></n-icon></template></n-button>
                            </template>
                            确定要删除这条消息吗？
                          </n-popconfirm>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 回到底部按钮 -->
          <transition name="fade">
            <n-button v-if="!isAutoScrollEnabled" circle class="scroll-to-bottom-btn" @click="forceScrollToBottom">
              <n-icon size="22"><ArrowDownOutline /></n-icon>
              <div v-show="isLoading" class="rotate-circle"></div>
            </n-button>
          </transition>

          <!-- 底部输入区 -->
          <div class="compose-area" v-if="chatStore.activeChatId">
            <div>
              <div v-if="uploadedFiles.length" class="file-preview-list">
                <div v-for="(f, index) in uploadedFiles" :key="f.filename" class="file-preview-item">
                  <div class="file-info">
                    <img v-if="f.type.startsWith('image/')" :src="f.url" class="file-thumb" />
                    <div v-else class="file-name">
                      <n-icon><DocumentOutline /></n-icon>
                      <span>{{ f.filename }}</span>
                    </div>
                    <n-button text class="file-close" @click="removeFile(index)"><template #icon><m-svg name="close" /></template></n-button>
                  </div>
                </div>
              </div>
            </div>
            <div class="compose-input-container">
              <div v-if="!isLoading && currentMessages.length >=1 && currentMessages[currentMessages.length - 1].role === 'user'" style="width:100%;text-align:center;position: absolute;top:-30px;">
                <n-button text @click="onRegenerateFromCurrentHistory"><template #icon><n-icon size="22"><BarcodeOutline /></n-icon></template>重新生成AI响应</n-button>
              </div>
              <n-input v-model:value="currentInput" type="textarea" name="talk" placeholder="今天要做点什么呢？" :autosize="{ minRows: 4, maxRows: 6 }" @keydown.enter.exact="onSendMessage" :disabled="isLoading || !chatStore.activeChatId || !activeModelId" class="compose-input" :class="{ 'jelly-effect': isJellyActive }" @focus="triggerJelly" @paste="onPaste" />
            </div>
            <div class="compose-tools-tar">
              <n-button v-if="configStore.activeModel?.type === 'online'" round secondary class="compose-thinking" title="先思考后回答，解决推理问题" :type="selected ? 'primary' : 'default'" @click="selected = !selected">深度思考</n-button>
              <n-upload :disabled="isLoading || !chatStore.activeChatId || !activeModelId" v-model:file-list="uploadFileList" multiple :max="fileConfig.max" :accept="fileConfig.accept" :show-file-list="false" @change="handleFileUpload" @before-upload="onBeforeUpload">
                <n-button text class="upload-btn" title="上传文件"><template #icon><n-icon><m-svg name="attach" /></n-icon></template></n-button>
              </n-upload>
              <n-button v-if="!isLoading" class="send-btn" @click="onSendMessage" strong secondary type="primary" :disabled="!!(!currentInput.trim().length && chatStore.activeChatId)">
                <template #icon><n-icon><m-svg name="send"/></n-icon></template>
              </n-button>
              <n-button v-else class="send-btn" @click="stopGeneration" strong secondary type="primary">
                <template #icon><n-icon><m-svg name="stop"/></n-icon></template>
              </n-button>
            </div>
            <div style="width:100%;position:absolute;bottom:2px;color:#999;font-size:12px;text-align:center;">内容由 AI 生成，未必正确无误</div>
          </div>
        </main>
      </div>

      <SettingsDrawer v-model:show="showSettings" />
      <n-modal v-model:show="showEditModal" preset="dialog" draggable :mask-closable="false" title="编辑消息" positive-text="保存" negative-text="取消" @positive-click="onSaveEdit">
        <n-input v-model:value="editContent" type="textarea" :autosize="{ minRows: 2, maxRows: 10 }" placeholder="请输入内容"/>
      </n-modal>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup lang="ts">
import { ref, h, render, nextTick, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  NConfigProvider, NMessageProvider, NButton, NInput, NUpload, NList, NListItem, NIcon,
  NScrollbar, NImage, NFlex, NSelect, NModal, NPopconfirm, NPopover, NQrCode
} from 'naive-ui'
import { SettingsOutline, DocumentOutline, MenuOutline, QrCodeOutline, BarcodeOutline, ArrowDownOutline } from '@vicons/ionicons5'
import { useVirtualizer } from '@tanstack/vue-virtual'

import { useChatStore, type Message } from '@/stores/chat'
import { useConfigStore, fileConfig } from '@/stores/config'
import { useProfileStore } from '@/stores/profiles'
import SettingsDrawer from '@/components/SettingsDrawer.vue'
import svgWelcomeDark from '@/components-svg/svgWelcomeDark.vue'
import svgWelcomeLight from '@/components-svg/svgWelcomeLight.vue'
import svgLoading from '@/components-svg/svgLoading.vue'
import Introduction from '@/components/Introduction.vue'
import mSvg from '@/components/MSvg.vue'

import { useTheme } from '@/composables/useTheme'
import { useModel } from '@/composables/useModel'
import { useFileUpload } from '@/composables/useFileUpload'
import { useChat } from '@/composables/useChat'
import { useMessageActions } from '@/composables/useMessageActions'
import { useCodeEnhancer } from '@/composables/useCodeEnhancer'
import { localIP, renderMessageHtml, normalizeFileRef, addFileTypeClassToLinks } from '@/utils/message'

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
const streamDisplayHtml = ref('')
let renderRafId: number | null = null
const isAutoScrollEnabled = ref(true)
const SCROLL_THRESHOLD = 80
const scrollerRef = ref<any>(null) // 滚动容器引用

function checkMobile() {
  isMobile.value = window.innerWidth <= 768
  if (!isMobile.value) sidebarOpen.value = false
  showQRCode.value = !(/Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent) && 'ontouchstart' in window || navigator.maxTouchPoints > 0)
}

const selected = ref(localStorage.getItem('thinking') === 'true')

const { naiveTheme, themeOverrides } = useTheme()
const { activeModelId, modelOptions, switchActiveModel } = useModel()
const { uploadFileList, uploadedFiles, isDragging, onDragEnter, onDragOver, onDragLeave, onDrop, onBeforeUpload, handleFileUpload, removeFile, clearFiles } = useFileUpload()
const { currentInput, isLoading, streamingContent, regeneratingMsg, sendMessage, onStreamEnd, regenerateResponse, regenerateFromCurrentHistory, stopGeneration } = useChat()
const { showEditModal, editContent, copySvgName, copyContent, startEditMessage, saveEdit, renamingChatId, renameText, startRename, confirmRename } = useMessageActions()
const { messageListRef, addCopyButtons, renderMermaidDiagrams, startObserving, stopObserving, setStreaming } = useCodeEnhancer()

// ========== 虚拟列表数据源 ==========
const currentMessages = computed(() => chatStore.currentChatMessages)
const virtualItems = computed(() => {
  const msgs = [...currentMessages.value]
  if (isLoading.value && !regeneratingMsg.value) {
    // 追加一个流式输出临时项
    msgs.push({
      id: 'streaming',
      role: 'assistant',
      content: streamingContent.value,
      renderedHtml: null,
      file_ref: null
    } as Message)
  }
  return msgs
})

// 虚拟滚动容器 ref
const virtualContainer = ref<HTMLElement | null>(null)

// 创建虚拟列表器
const virtualizer = useVirtualizer(computed(() => ({
  count: virtualItems.value.length,
  getScrollElement: () => virtualContainer.value,
  estimateSize: () => 200, // 估计每项高度，越大越安全
  overscan: 5,
  // 测量元素（可选）
  getItemKey: (index) => virtualItems.value[index].id,
  // 动态测量
  measureElement: (el) => el?.getBoundingClientRect().height,
})))

// 当流式内容或消息变化时，重新测量最后一项（或全部）
watch(streamingContent, () => {
  if (virtualizer.value) {
    // 延迟一帧等待 DOM 更新
    nextTick(() => {
      if (virtualizer.value) {
        // 测量最后一项（流式气泡）
        const lastIndex = virtualItems.value.length - 1
        if (lastIndex >= 0) {
          const el = document.querySelector(`[data-index="${lastIndex}"]`)
          if (el) {
            virtualizer.value.measureElement(el as HTMLElement)
          } else {
            virtualizer.value.measure()
          }
        }
        if (isAutoScrollEnabled.value) {
          virtualizer.value.scrollToIndex(lastIndex, { align: 'end' })
        }
      }
    })
  }
})

// 自动滚动到底部
function scrollToBottom() {
  if (virtualizer.value) {
    virtualizer.value.scrollToIndex(virtualItems.value.length - 1, { align: 'end' })
  }
}

function updateScrollState() {
  if (virtualContainer.value) {
    const target = virtualContainer.value
    const scrollTop = target.scrollTop
    const scrollHeight = target.scrollHeight
    const clientHeight = target.clientHeight
    isAutoScrollEnabled.value = (scrollHeight - scrollTop - clientHeight) <= SCROLL_THRESHOLD
  }
}

function handleScroll() {
  updateScrollState()
}

const isProgrammaticScroll = ref(false)
function forceScrollToBottom() {
  isAutoScrollEnabled.value = true
  scrollToBottom()
}

// 绑定流结束回调
onStreamEnd.value = (fullText: string) => {
  const messages = chatStore.getActiveMessages()
  if (regeneratingMsg.value) {
    const msg = regeneratingMsg.value
    msg.content = fullText
    msg.renderedHtml = renderMessageHtml(fullText, true)
    regeneratingMsg.value = null
    nextTick(() => {
      setStreaming(false)
      addCopyButtons()
      renderMermaidDiagrams()
      virtualizer.value?.measure()
      scrollToBottom()
    })
    return
  }
  const lastMsg = messages[messages.length - 1]
  if (lastMsg && lastMsg.role === 'assistant' && lastMsg.content === fullText) {
    if (!lastMsg.renderedHtml) {
      lastMsg.renderedHtml = renderMessageHtml(fullText, true)
    }
    nextTick(() => {
      addCopyButtons()
      renderMermaidDiagrams()
      virtualizer.value?.measure()
      scrollToBottom()
    })
  }
}

// 流式内容更新
watch(streamingContent, (newVal) => {
  setStreaming(!!newVal)
  if (!newVal) {
    streamDisplayHtml.value = ''
    if (renderRafId !== null) cancelAnimationFrame(renderRafId)
    return
  }
  if (renderRafId !== null) cancelAnimationFrame(renderRafId)
  renderRafId = requestAnimationFrame(() => {
    streamDisplayHtml.value = renderMessageHtml(newVal, true)
    renderRafId = null
    // 上面虚拟列表的 watch 会处理测量和滚动
  })
})

watch(() => selected.value, (newVal) => {
  localStorage.setItem('thinking', newVal ? 'true' : 'false')
})

const sidebarCollapsed = ref(true)
const showSettings = ref(false)

const profileOptions = computed(() =>
  profileStore.profiles.map((p) => ({ label: p.name, value: p.id }))
)

// 创建对话
async function createChat() {
  const newChatId = await chatStore.addChat()
  openChat(newChatId)
}

function setQRCodeUrl () {
  qrCodeUrl.value = window.location.href.replace(/\b(?:localhost|\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b/g, local_ip.value)
}

// 粘贴上传相关
const pasteToastVisible = ref(false)
const lastPasteCount = ref(0)
let pasteToastTimer: ReturnType<typeof setTimeout> | null = null

function isFileTypeAccepted(fileType: string, fileName: string): boolean {
  const accept = fileConfig.accept
  if (!accept || accept === '*' || accept === '*/*') return true
  const acceptItems = accept.split(',').map(s => s.trim()).filter(Boolean)
  if (acceptItems.length === 0) return true
  for (const item of acceptItems) {
    if (item.endsWith('/*')) {
      const prefix = item.slice(0, -1)
      if (fileType.startsWith(prefix)) return true
      continue
    }
    if (item.startsWith('.')) {
      const ext = item.toLowerCase()
      if (fileName.toLowerCase().endsWith(ext)) return true
      const mimeExt = fileType.split('/')[1]
      if (mimeExt && ext === '.' + mimeExt.toLowerCase()) return true
      continue
    }
    if (fileType === item) return true
  }
  return false
}

function onPaste(e: ClipboardEvent) {
  if (!chatStore.activeChatId) return
  if (isLoading.value) return
  if (!activeModelId.value) return
  const clipboardData = e.clipboardData
  if (!clipboardData) return
  const items = clipboardData.items
  if (!items || items.length === 0) return
  const pastedFiles: File[] = []
  for (let i = 0; i < items.length; i++) {
    const item = items[i]
    if (item.kind === 'file') {
      const file = item.getAsFile()
      if (file && file.size > 0) {
        pastedFiles.push(file)
      }
    }
  }
  if (pastedFiles.length === 0) return
  const acceptedFiles = pastedFiles.filter(f => isFileTypeAccepted(f.type, f.name))
  if (acceptedFiles.length === 0) return
  e.preventDefault()
  const remaining = fileConfig.max - uploadedFiles.value.length
  if (remaining <= 0) return
  const filesToAdd = acceptedFiles.slice(0, remaining)
  for (const file of filesToAdd) {
    let filename = file.name
    if (!filename || filename === 'image.png' || filename === 'blob' || filename === 'clipboard') {
      const ext = file.type ? file.type.split('/')[1] || 'png' : 'png'
      const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)
      filename = `paste-${timestamp}-${Math.random().toString(36).slice(2, 6)}.${ext}`
    }
    const url = URL.createObjectURL(file)
    uploadedFiles.value.push({ filename, type: file.type || 'application/octet-stream', url })
  }
  lastPasteCount.value = filesToAdd.length
  pasteToastVisible.value = true
  if (pasteToastTimer) clearTimeout(pasteToastTimer)
  pasteToastTimer = setTimeout(() => { pasteToastVisible.value = false }, 1800)
}

function openChat(chatId: string) {
  chatStore.activeChatId = chatId
  router.push({ name: 'chat', params: { id: chatId } })
  setTimeout(() => { setQRCodeUrl() }, 300)
}

function onSendMessage() {
  isAutoScrollEnabled.value = true
  sendMessage(uploadedFiles.value, () => { scrollToBottom() })
  clearFiles()
}

async function onRegenerateFromCurrentHistory() {
  isAutoScrollEnabled.value = true
  await regenerateFromCurrentHistory(() => { scrollToBottom() })
}

async function handleRegenerateResponse(msg: Message) {
  isAutoScrollEnabled.value = true
  await regenerateResponse(msg, () => { scrollToBottom() })
}

async function onSaveEdit() {
  await saveEdit(() => onRegenerateFromCurrentHistory())
}

function previewImage(imageUrl:string) {
  const container = document.createElement('div')
  container.style.display = 'none'
  document.body.appendChild(container)
  const vnode = h(NImage, { src: imageUrl })
  render(vnode, container)
  nextTick(() => {
    const imgEl = container.querySelector('img')
    if (imgEl) imgEl.click()
    setTimeout(() => { document.body.removeChild(container) }, 200)
  })
}

const onContainerClick = (e: any) => {
  const target = e.target
  if (target.tagName === 'IMG') {
    e.preventDefault()
    previewImage(target.src)
  }
}

// 推理块和工具块点击逻辑（保持原有逻辑，但改用虚拟滚动测量）
function handleReasoningClick(e: MouseEvent) {
  const target = e.target as HTMLElement
  const summary = target.closest('.reasoning-summary')
  if (!summary) return
  const block = summary.closest('.reasoning-block') as HTMLElement | null
  if (!block) return
  const isOpen = block.dataset.reasoning === 'open'
  const container = block.closest('.message-content')
  let blockIndex = -1
  if (container) {
    const blocks = Array.from(container.querySelectorAll('.reasoning-block'))
    blockIndex = blocks.indexOf(block)
  }
  if (isOpen) {
    block.removeAttribute('data-reasoning')
  } else {
    block.setAttribute('data-reasoning', 'open')
  }
  if (blockIndex !== -1) {
    const scrollerItem = target.closest('[data-index]')
    if (scrollerItem) {
      const idx = parseInt(scrollerItem.getAttribute('data-index') || '0', 10)
      const msg = chatStore.currentChatMessages[idx]
      if (msg) {
        let html = msg.renderedHtml || renderMessageHtml(msg.content.trim(), false)
        const parts = html.split('<div class="reasoning-block"')
        if (blockIndex >= 0 && blockIndex + 1 < parts.length) {
          let part = parts[blockIndex + 1]
          if (isOpen) {
            part = part.replace(/^ data-reasoning="open">/, '>')
          } else {
            part = part.replace(/^>/, ' data-reasoning="open">')
          }
          parts[blockIndex + 1] = part
          msg.renderedHtml = parts.join('<div class="reasoning-block"')
          // 重新测量该项
          nextTick(() => {
            virtualizer.value?.measure()
            updateScrollState()
          })
        }
      }
    }
  }
}

function handleToolClick(e: MouseEvent) {
  const target = e.target as HTMLElement
  const summary = target.closest('.tool-summary')
  if (!summary) return
  const block = summary.closest('.tool-calls-block') as HTMLElement | null
  if (!block) return
  const isOpen = block.dataset.tool === 'open'
  const container = block.closest('.message-content')
  let blockIndex = -1
  if (container) {
    const blocks = Array.from(container.querySelectorAll('.tool-calls-block'))
    blockIndex = blocks.indexOf(block)
  }
  if (isOpen) {
    block.removeAttribute('data-tool')
  } else {
    block.setAttribute('data-tool', 'open')
  }
  if (blockIndex !== -1) {
    const scrollerItem = target.closest('[data-index]')
    if (scrollerItem) {
      const idx = parseInt(scrollerItem.getAttribute('data-index') || '0', 10)
      const msg = chatStore.currentChatMessages[idx]
      if (msg) {
        let html = msg.renderedHtml || renderMessageHtml(msg.content.trim(), false)
        const parts = html.split('<div class="tool-calls-block"')
        if (blockIndex >= 0 && blockIndex + 1 < parts.length) {
          let part = parts[blockIndex + 1]
          if (isOpen) {
            part = part.replace(/^ data-tool="open">/, '>')
          } else {
            part = part.replace(/^>/, ' data-tool="open">')
          }
          parts[blockIndex + 1] = part
          msg.renderedHtml = parts.join('<div class="tool-calls-block"')
          nextTick(() => {
            virtualizer.value?.measure()
            updateScrollState()
          })
        }
      }
    }
  }
}

// 监听消息数量变化，重新测量并滚动
watch(() => chatStore.currentChatMessages.length, () => {
  nextTick(() => {
    addCopyButtons()
    renderMermaidDiagrams()
    virtualizer.value?.measure()
    if (isAutoScrollEnabled.value) {
      scrollToBottom()
    }
  })
})

// 果冻动画
const isJellyActive = ref(false)
let jellyTimer: ReturnType<typeof setTimeout> | null = null
function triggerJelly() {
  if (isJellyActive.value) return
  isJellyActive.value = true
  if (jellyTimer) clearTimeout(jellyTimer)
  jellyTimer = setTimeout(() => { isJellyActive.value = false }, 600)
}

const isRender = ref(false)

// 生命周期
onMounted(async () => {
  checkMobile()
  window.addEventListener('resize', checkMobile)
  if (virtualContainer.value) {
    virtualContainer.value.addEventListener('scroll', handleScroll, { passive: true })
    virtualContainer.value.addEventListener('click', handleReasoningClick)
    virtualContainer.value.addEventListener('click', handleToolClick)
  }
  await profileStore.loadProfiles()
  renderMermaidDiagrams()
  startObserving()
  fetch('/api/local-ip').then(async (res) => {
    local_ip.value = await res.json()
    localIP.value = local_ip.value
    setQRCodeUrl()
  })
  setTimeout(() => {
    addFileTypeClassToLinks(document.body)
    isRender.value = true
  }, 150)
})

onUnmounted(() => {
  if (jellyTimer) clearTimeout(jellyTimer)
  window.removeEventListener('resize', checkMobile)
  if (virtualContainer.value) {
    virtualContainer.value.removeEventListener('scroll', handleScroll)
    virtualContainer.value.removeEventListener('click', handleReasoningClick)
    virtualContainer.value.removeEventListener('click', handleToolClick)
  }
  stopObserving()
})

const showWelcome = ref(false)

watch(() => route.params.id, (newId) => {
  chatStore.activeChatId = newId as string
})

watch(() => chatStore.activeChatId, async (newId) => {
    if (newId) {
      await chatStore.loadMessages(newId)
      showWelcome.value = currentMessages.value.length === 0
    } else {
      chatStore.loadChats()
    }
  },
  { immediate: true }
)
</script>

<style scoped src="./index.css"></style>