<template>
  <n-config-provider :theme="naiveTheme" :theme-overrides="themeOverrides">
    <n-message-provider>
      <div class="app-container" :class="[configStore.themeMode]">
        <div v-if="isMobile && sidebarOpen" class="sidebar-overlay" @click="sidebarOpen = false"></div> <!-- 遮罩层 -->
        <!-- ========== 侧边栏（折叠式） ========== -->
        <aside v-show="!sidebarCollapsed" class="sidebar-panel border-marquee-right" :class="{ collapsed: sidebarCollapsed, 'sidebar-open': sidebarOpen }">
          <!-- 展开状态 -->
          <div class="sidebar-header">
            <span class="logo-text">✨ LumNeo</span>
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
          <n-scrollbar content-style="padding:0 16px" style="max-height: calc(100vh - 220px);">
            <n-list hoverable clickable :show-divider="false">
              <n-list-item v-for="chat in chatStore.chats" :key="chat.id" 
                @click="openChat(chat.id)"
                :class="{ active: chat.id === chatStore.activeChatId }">
                <div class="chat-item-row">
                  <!-- 标题区域 -->
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

                  <!-- 操作按钮（悬停显示） -->
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

        <!-- ========== 主区域 ========== -->
        <main
          class="main-stage"
          :class="{ 'main-stage--full': sidebarCollapsed }"
          @dragenter="onDragEnter($event, isLoading)"
          @dragover="onDragOver"
          @dragleave="onDragLeave"
          @drop="onDrop($event, chatStore.activeChatId, isLoading)"
        >
          <!-- 拖拽提示浮层 -->
          <div v-if="isDragging && chatStore.activeChatId" class="drag-overlay">
            <div class="drag-hint"><n-icon><DocumentOutline /></n-icon> 释放文件以上传</div>
          </div>
          <!-- 顶部工具栏 -->
          <header v-if="chatStore.activeChatId" class="top-bar" :class="[sidebarCollapsed || isMobile ? 'border-marquee-center' : '']">
            <n-flex style="width:100%" justify="space-between">
              <n-flex>
                <n-button v-if="isMobile" text @click="sidebarOpen = !sidebarOpen;sidebarCollapsed=false">
                  <template #icon><n-icon><MenuOutline /></n-icon></template>
                </n-button>
                <n-button v-if="!isMobile && sidebarCollapsed" text class="icon-btn" @click="sidebarCollapsed = false" title="展开侧栏">
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
                  <!-- 角色选择 -->
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

          <!-- 消息列表 -->
          <div class="message-container" ref="messageListRef">
            <div class="introduction" v-if="!chatStore.activeChatId">
              <Introduction v-if="isRender" @click="sidebarOpen=true;sidebarCollapsed=false" />
            </div>
            <div class="message-main" v-else>
              <div v-if="showWelcome && currentMessages.length === 0">
                <svgWelcomeDark v-if="configStore.themeMode === 'dark'" />
                <svgWelcomeLight v-else />
              </div>
              <div ref="virtualContainerRef" class="virtual-scroller" @scroll="handleScroll">
                <div
                  :style="{height: virtualizer.getTotalSize() + 'px', width: isMobile? '90%' : '80%', maxWidth: '1000px', position: 'relative', margin: '0 auto'}">
                  <div
                    v-for="virtualRow in virtualizer.getVirtualItems()"
                    :key="<string>virtualRow.key"
                    :ref="(el) => virtualizer.measureElement(<Element>el)"
                    :style="{position: 'absolute', top: 0, left: 0, width: '100%', transform: `translateY(${virtualRow.start}px)`}"
                    :data-index="virtualRow.index"
                  >
                    <!-- 流式输出气泡（列表最后一项） -->
                    <template v-if="listItems[virtualRow.index]?.__streaming">
                      <div class="streaming-after-item message-row assistant">
                        <div v-if="streamDisplayHtml" class="bubble streaming" v-html="streamDisplayHtml"></div>
                        <svgLoading v-else />
                      </div>
                    </template>

                    <!-- 正常消息 -->
                    <template v-else>
                      <div :class="['message-row', listItems[virtualRow.index].role]" @click="">
                        <div class="bubble" :class="{'has-file': listItems[virtualRow.index].file_ref}">
                          <!-- 文件附件 -->
                          <div v-if="normalizeFileRef(listItems[virtualRow.index].file_ref).length" class="message-files">
                            <div v-for="f in normalizeFileRef(listItems[virtualRow.index].file_ref)" :key="f.filename" class="msg-file-item">
                              <n-image v-if="f.type.startsWith('image/')" width="200" :src="f.url" class="msg-file-img"/>
                              <div v-else class="msg-file-other">
                                <n-icon><DocumentOutline /></n-icon>
                                <a :href="f.url" target="_blank">{{f.filename}}</a>
                              </div>
                            </div>
                          </div>

                          <!-- 重新生成占位 -->
                          <template v-if="listItems[virtualRow.index] === regeneratingMsg">
                            <div style="height: 1px"></div>
                          </template>
                          <template v-else>
                            <template v-if="listItems[virtualRow.index].role === 'user'">
                              <div class="message-content user-content" v-text="listItems[virtualRow.index].content.trim()"></div>
                            </template>
                            <template v-else>
                              <div class="message-content" v-html="listItems[virtualRow.index].renderedHtml || renderMessageHtml(listItems[virtualRow.index].content.trim(),false)"
                                @click="onContainerClick"
                              ></div>
                            </template>
                          </template>

                          <!-- 操作按钮 -->
                          <div :class=" 'message-actions ' + (listItems[virtualRow.index].role === 'assistant' ? 'assistant-actions' : 'user-actions')"
                            v-if="!isLoading || listItems[virtualRow.index] !== regeneratingMsg">
                            <n-button text class="icon-btn" size="small" title="复制" @click="copyContent(listItems[virtualRow.index])">
                              <template #icon><n-icon><m-svg :name="copySvgName" /></n-icon></template>
                            </n-button>
                            <n-button v-if="listItems[virtualRow.index].role === 'assistant' && virtualRow.index === currentMessages.length - 1"
                              text class="icon-btn" size="small" title="重新生成" @click="handleRegenerateResponse(listItems[virtualRow.index])">
                              <template #icon><n-icon><m-svg name="refresh" /></n-icon></template>
                            </n-button>
                            <n-button text class="icon-btn" size="small" title="编辑" @click="startEditMessage(listItems[virtualRow.index])">
                              <template #icon><n-icon :size="20"><m-svg name="edit" /></n-icon></template>
                            </n-button>
                            <n-popconfirm
                              @positive-click="() => chatStore.deleteMessage(listItems[virtualRow.index].id!)"
                              :negative-button-props="{ size: 'tiny' }"
                              :positive-button-props="{ size: 'tiny' }"
                              negative-text="取消"
                              positive-text="好的"
                            >
                              <template #trigger>
                                <n-button text class="icon-btn" size="small" title="删除">
                                  <template #icon
                                    ><n-icon :size="22"
                                      ><m-svg name="del" /></n-icon
                                  ></template>
                                </n-button>
                              </template>
                              确定要删除这条消息吗？
                            </n-popconfirm>
                          </div>
                        </div>
                      </div>
                    </template>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 底部输入区 -->
          <div class="compose-area" v-if="chatStore.activeChatId">
            <!-- ✅ 回到底部按钮 -->
            <transition name="fade">
              <n-button v-if="!isAutoScrollEnabled && currentMessages.length !== 0" circle class="scroll-to-bottom-btn" @click="forceScrollToBottom">
                <n-icon size="22"><ArrowDownOutline /></n-icon>
                <div v-show="isLoading" class="rotate-circle"></div>
              </n-button>
            </transition>
            <div>
              <!-- 文件预览条 -->
              <div v-if="uploadedFiles.length" class="file-preview-list">
                <div v-for="(f, index) in uploadedFiles" :key="f.filename" class="file-preview-item">
                  <div class="file-info">
                    <img v-if="f.type.startsWith('image/')" :src="f.url" class="file-thumb" />
                    <div v-else class="file-name">
                      <n-icon><DocumentOutline /></n-icon>
                      <span>{{ f.filename }}</span>
                    </div>
                    <n-button text class="file-close" @click="removeFile(index)">
                      <template #icon>
                        <m-svg name="close" />
                      </template>
                    </n-button>
                  </div>
                </div>
              </div>
            </div>
            <div class="compose-input-container">
              <div v-if="!isLoading && currentMessages.length >=1 && currentMessages[currentMessages.length - 1].role === 'user'" style="width:100%;text-align:center;position: absolute;top:-30px;">
                <n-button text @click="onRegenerateFromCurrentHistory">
                  <template #icon>
                    <n-icon size="22"><m-svg name="wave" /></n-icon>
                  </template>
                  点击重新生成AI响应
                </n-button>
              </div>
              <n-input
                v-model:value="currentInput"
                type="textarea"
                name="talk"
                placeholder="今天要做点什么呢？"
                :autosize="{ minRows: 4, maxRows: 6 }"
                @keydown.enter.exact="onSendMessage"
                :disabled="isLoading || !chatStore.activeChatId || !activeModelId"
                class="compose-input"
                :class="{ 'jelly-effect': isJellyActive }"
                @focus="triggerJelly"
                @paste="onPaste"
              />
            </div>

            <div class="compose-tools-tar">
              <n-button v-if="configStore.activeModel?.type === 'online'" 
              round 
              secondary
              class="compose-thinking" 
              title="先思考后回答，解决推理问题"
              :type="selected ? 'primary' : 'default'"
              @click="selected = !selected"
              >
                深度思考
              </n-button>
              <!-- 文件上传按钮 -->
              <n-upload
                :disabled="isLoading || !chatStore.activeChatId || !activeModelId"
                v-model:file-list="uploadFileList"
                multiple
                :max="fileConfig.max"
                :accept="fileConfig.accept"
                :show-file-list="false"
                @change="handleFileUpload"
                @before-upload="onBeforeUpload"
              >
                <n-button text class="upload-btn" title="上传文件">
                  <template #icon><n-icon><m-svg name="attach" /></n-icon></template>
                </n-button>
              </n-upload>

              <!-- 发送按钮 -->
              <n-button v-if="!isLoading" class="send-btn" @click="onSendMessage"
                strong secondary type="primary"
                :disabled="!!(!currentInput.trim().length && chatStore.activeChatId)"
              >
                <template #icon>
                  <n-icon><m-svg name="send"/></n-icon>
                </template>
              </n-button>
              <n-button v-else class="send-btn" @click="stopGeneration" strong secondary type="primary">
                <template #icon>
                  <n-icon><m-svg name="stop"/></n-icon>
                </template>
              </n-button>
            </div>
            <div style="width:100%;position:absolute;bottom:2px;color:#999;font-size:12px;text-align:center;">内容由 AI 生成，未必正确无误</div>
          </div>
        </main>
      </div>

      <!-- 设置抽屉 -->
      <SettingsDrawer v-model:show="showSettings" />

      <!-- 编辑消息模态框 -->
      <n-modal v-model:show="showEditModal" preset="dialog" draggable :mask-closable="false" title="编辑消息" positive-text="保存" negative-text="取消"
        @positive-click="onSaveEdit">
        <n-input v-model:value="editContent" type="textarea" :autosize="{ minRows: 2, maxRows: 10 }" placeholder="请输入内容"/>
      </n-modal>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup lang="ts">
import { ref, h, render, nextTick, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NConfigProvider, NMessageProvider, NButton, NInput,
  NUpload, NList, NListItem, NIcon, NScrollbar, NImage, NFlex,
  NSelect, NModal, NPopconfirm, NPopover, NQrCode
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
import { localIP, renderMessageHtml, normalizeFileRef } from '@/utils/message'

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
const messageListRef = ref<HTMLElement | null>(null)

const isAutoScrollEnabled = ref(true)            // 自动滚动开关
const SCROLL_THRESHOLD = 80                     // 距离底部的容差阈值（像素）

function checkMobile() {
  isMobile.value = window.innerWidth <= 768
  if (!isMobile.value) sidebarOpen.value = false // 桌面端关闭移动菜单
  showQRCode.value = !(/Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent) && 'ontouchstart' in window || navigator.maxTouchPoints > 0)
}

const selected = ref(localStorage.getItem('thinking') === 'true')

const { naiveTheme, themeOverrides } = useTheme()

const { activeModelId, modelOptions, switchActiveModel } = useModel()

const { uploadFileList, uploadedFiles, isDragging, onDragEnter, onDragOver, 
    onDragLeave, onDrop, onBeforeUpload, handleFileUpload, removeFile, clearFiles
} = useFileUpload()

const { currentInput, isLoading, streamingContent, regeneratingMsg, 
    sendMessage, onStreamEnd, regenerateResponse, regenerateFromCurrentHistory, stopGeneration 
} = useChat()

const { showEditModal, editContent, copySvgName, copyContent,
  startEditMessage, saveEdit, renamingChatId, renameText, startRename, confirmRename 
} = useMessageActions()

const virtualContainerRef = ref<HTMLElement | null>(null)   // 虚拟滚动容器（也是滚动元素）

const { addCopyButtons, addFileTypeClassToLinks, renderMermaidDiagrams, startObserving, stopObserving, setStreaming } = useCodeEnhancer(virtualContainerRef)

const currentMessages = computed(() => chatStore.currentChatMessages)
const listItems = computed<any>(() => {
  const msgs = currentMessages.value as (Message | { __streaming: boolean })[]
  return isLoading.value ? [...msgs, { __streaming: true }] : msgs
})

const virtualizer = useVirtualizer(
  computed(() => ({
    count: listItems.value.length,
    getScrollElement: () => virtualContainerRef.value,
    estimateSize: () => 120,            // 初始估算高度，后续自动测量
    overscan: 5,
  }))
)

// 绑定缓存逻辑：当流结束时，计算 HTML 并写入当前最新的历史消息中
onStreamEnd.value = (fullText: string) => {
  // 获取当前对话的最新一条助手消息（也就是刚刚生成的这条）
  const messages = chatStore.getActiveMessages()

  // 如果是重新生成，更新正在重新生成的那条消息
  if (regeneratingMsg.value) {
    const msg = regeneratingMsg.value
    msg.content = fullText
    msg.renderedHtml = renderMessageHtml(fullText, true)  // 缓存渲染结果
    regeneratingMsg.value = null   // 清空标记，恢复成普通消息显示
    nextTick(() => {
      setStreaming(false)
      addCopyButtons()
      renderMermaidDiagrams()
      addFileTypeClassToLinks(virtualContainerRef.value!)
      nextTick(() => virtualizer.value?.measure())
    })
    return
  }

  const lastMsg = messages[messages.length - 1]
  if (lastMsg && lastMsg.role === 'assistant' && lastMsg.content === fullText) {
    // 如果还没有缓存，就进行一次性完整渲染并存入
    if (!lastMsg.renderedHtml) {
      lastMsg.renderedHtml = renderMessageHtml(fullText, true)
    }
    nextTick(() => {
      addCopyButtons()
      renderMermaidDiagrams()
      addFileTypeClassToLinks(virtualContainerRef.value!)
      virtualizer.value?.measure()
    })
  }
}

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
  })
})

watch(() => selected.value, (newVal) => {
  localStorage.setItem('thinking', newVal ? 'true' : 'false')
})

// ---------- 侧边栏折叠 ----------
const sidebarCollapsed = ref(true)

// ---------- 设置抽屉 ----------
const showSettings = ref(false)

// ---------- 角色选项 ----------
const profileOptions = computed(() =>
  profileStore.profiles.map((p) => ({ label: p.name, value: p.id }))
)

const isProgrammaticScroll = ref(false)

// ---------- 滚动到底部 ----------
function scrollToBottom() {
  if (listItems.value.length === 0) return
  isProgrammaticScroll.value = true
  requestAnimationFrame(() => {
    virtualizer.value.scrollToIndex(listItems.value.length - 1, { align: 'end' })
  })
  setTimeout(() => {
    isProgrammaticScroll.value = false
  }, 200)
}

function updateScrollState() {
  const target = virtualContainerRef.value
  if (!target) return
  requestAnimationFrame(() => {
    const scrollTop = target.scrollTop
    const scrollHeight = target.scrollHeight
    const clientHeight = target.clientHeight
    const isAtBottom = (scrollHeight - scrollTop - clientHeight) <= SCROLL_THRESHOLD
    isAutoScrollEnabled.value = isAtBottom
  })
}

function handleScroll() {
  if (isProgrammaticScroll.value) return
  updateScrollState()
}

async function createChat() {
  const newChatId = await chatStore.addChat()
  openChat(newChatId)
}

function setQRCodeUrl () {
  qrCodeUrl.value = window.location.href.replace(/\b(?:localhost|\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b/g, local_ip.value)
}

// ========== 粘贴上传相关 ==========
const pasteToastVisible = ref(false)
const lastPasteCount = ref(0)
let pasteToastTimer: ReturnType<typeof setTimeout> | null = null

/**
 * 检查文件类型是否在 fileConfig.accept 允许范围内
 * @param fileType MIME 类型，如 "image/png"
 * @param fileName 文件名（用于扩展名匹配）
 */
function isFileTypeAccepted(fileType: string, fileName: string): boolean {
  const accept = fileConfig.accept
  // 空 accept 或通配符表示接受所有
  if (!accept || accept === '*' || accept === '*/*') return true
  
  const acceptItems = accept.split(',').map(s => s.trim()).filter(Boolean)
  if (acceptItems.length === 0) return true
  
  for (const item of acceptItems) {
    // 匹配 MIME 类型通配符，如 image/*
    if (item.endsWith('/*')) {
      const prefix = item.slice(0, -1) // "image/"
      if (fileType.startsWith(prefix)) return true
      continue
    }
    // 匹配扩展名，如 .pdf .doc
    if (item.startsWith('.')) {
      const ext = item.toLowerCase()
      if (fileName.toLowerCase().endsWith(ext)) return true
      // 也尝试从 MIME 类型推断扩展名
      const mimeExt = fileType.split('/')[1]
      if (mimeExt && ext === '.' + mimeExt.toLowerCase()) return true
      continue
    }
    // 精确 MIME 类型匹配
    if (fileType === item) return true
  }
  return false
}

/**
 * 粘贴事件处理 - 支持 Ctrl+V 粘贴剪贴板中的文件/图片
 */
function onPaste(e: ClipboardEvent) {
  // 检查上传条件
  if (!chatStore.activeChatId) return
  if (isLoading.value) return
  if (!activeModelId.value) return
  
  const clipboardData = e.clipboardData
  if (!clipboardData) return
  
  const items = clipboardData.items
  if (!items || items.length === 0) return
  
  // 收集剪贴板中的文件
  const pastedFiles: File[] = []
  let hasOnlyText = true
  
  for (let i = 0; i < items.length; i++) {
    const item = items[i]
    if (item.kind === 'file') {
      hasOnlyText = false
      const file = item.getAsFile()
      if (file && file.size > 0) {
        pastedFiles.push(file)
      }
    }
  }
  
  // 如果没有文件，只有纯文本，不拦截（让输入框正常处理文本粘贴）
  if (pastedFiles.length === 0) return
  
  // 过滤不符合 accept 条件的文件
  const acceptedFiles = pastedFiles.filter(f => isFileTypeAccepted(f.type, f.name))
  if (acceptedFiles.length === 0) return
  
  // 阻止默认行为（防止图片以 base64 等形式插入到输入框）
  e.preventDefault()
  
  // 计算还能添加多少个文件
  const remaining = fileConfig.max - uploadedFiles.value.length
  if (remaining <= 0) {
    // 已达上限，静默忽略
    return
  }
  
  // 截断到剩余可添加数量
  const filesToAdd = acceptedFiles.slice(0, remaining)
  
  // 为每个粘贴的文件创建上传对象并添加到 uploadedFiles
  for (const file of filesToAdd) {
    // 为没有合适文件名的粘贴文件生成名称（如截图粘贴）
    let filename = file.name
    if (!filename || filename === 'image.png' || filename === 'blob' || filename === 'clipboard') {
      const ext = file.type ? file.type.split('/')[1] || 'png' : 'png'
      const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)
      filename = `paste-${timestamp}-${Math.random().toString(36).slice(2, 6)}.${ext}`
    }
    
    const url = URL.createObjectURL(file)
    
    uploadedFiles.value.push({
      filename,
      type: file.type || 'application/octet-stream',
      url
    })
  }
  
  // 显示粘贴成功提示
  lastPasteCount.value = filesToAdd.length
  pasteToastVisible.value = true
  if (pasteToastTimer) clearTimeout(pasteToastTimer)
  pasteToastTimer = setTimeout(() => {
    pasteToastVisible.value = false
  }, 1800)
}

// ---------- 导航 ----------
function openChat(chatId: string) {
  if (isLoading.value) stopGeneration()
  chatStore.activeChatId = chatId  
  router.push({ name: 'chat', params: { id: chatId } })
  setTimeout(() => {
    setQRCodeUrl()
  }, 300)
}

// ---------- 发送消息包装 ----------
function onSendMessage() {
  isAutoScrollEnabled.value = true
  sendMessage(uploadedFiles.value, () => {
    if (isAutoScrollEnabled.value) {
      scrollToBottom()
    }
  })
  clearFiles()
}

// ---------- 编辑后重新生成包装 ----------
async function onRegenerateFromCurrentHistory() {
  isAutoScrollEnabled.value = true
  await regenerateFromCurrentHistory(() => {
    if (isAutoScrollEnabled.value) {
      scrollToBottom()
    }
  })
}

async function handleRegenerateResponse(msg: Message) {
  isAutoScrollEnabled.value = true
  await regenerateResponse(msg, () => {
    if (isAutoScrollEnabled.value) {
      scrollToBottom()
    }
  })
}

async function onSaveEdit() {
  await saveEdit(() => onRegenerateFromCurrentHistory())
  requestAnimationFrame(() => virtualizer.value?.measure())
}

/**
 * 使用 Naive UI 的预览功能打开一张图片
 * @param imageUrl 图片地址
 */
function previewImage(imageUrl:string) {
  // 创建一个隐藏的容器
  const container = document.createElement('div')
  container.style.display = 'none'
  document.body.appendChild(container)

  // 创建一个虚拟的 NImage 组件
  const vnode = h(NImage, {
    src: imageUrl,
  })

  // 渲染到容器
  render(vnode, container)

  // 等待 DOM 更新后，找到里面的 img 并触发点击
  nextTick(() => {
    const imgEl = container.querySelector('img')
    if (imgEl) {
      imgEl.click()  // 触发 NImage 内置的预览行为
    }
    // 预览打开后延迟移除临时容器（避免干扰）
    setTimeout(() => {
      document.body.removeChild(container)
    }, 200)
  })
}

const onContainerClick = (e: any) => {
  const target = e.target
  if (target.tagName === 'IMG') {
    e.preventDefault()
    previewImage(target.src)   // 你的预览函数
  }
}

// 强制滚动到底部并开启自动滚动
function forceScrollToBottom() {
  isAutoScrollEnabled.value = true
  virtualizer.value.scrollToIndex(listItems.value.length - 1, { align: 'end' })
}


function handleReasoningClick(e: MouseEvent) {
  const target = e.target as HTMLElement
  const summary = target.closest('.reasoning-summary')
  if (!summary) return
  
  const block = summary.closest('.reasoning-block') as HTMLElement | null
  
  if (!block) return
  
  // 切换状态
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
        // 通过特征字符串切分，精准修改目标块的属性
        const parts = html.split('<div class="reasoning-block"')
        if (blockIndex >= 0 && blockIndex + 1 < parts.length) {
          let part = parts[blockIndex + 1]
          if (isOpen) {
            part = part.replace(/^ data-reasoning="open">/, '>')
          } else {
            part = part.replace(/^>/, ' data-reasoning="open">')
          }
          parts[blockIndex + 1] = part
          msg.renderedHtml = parts.join('<div class="reasoning-block"') // 防止虚拟滚动后展开状态丢失

          requestAnimationFrame(() => {
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
          requestAnimationFrame(() => {
            updateScrollState()
          })
        }
      }
    }
  }
}

// ---------- 监视消息变化以重新渲染增强内容 ----------
watch(
  () => chatStore.currentChatMessages.length,
  () => {
    // 确保 DOM 更新后再渲染图表和按钮
    nextTick(() => {
      addCopyButtons()
      renderMermaidDiagrams()
      addFileTypeClassToLinks(virtualContainerRef.value!)
      // 如果处于自动滚动模式，则滚动到底部
      if (isAutoScrollEnabled.value) {
        scrollToBottom()
      }
    })
  }
)

// 果冻动画控制
const isJellyActive = ref(false)
let jellyTimer: ReturnType<typeof setTimeout> | null = null

function triggerJelly() {
  if (isJellyActive.value) return   // 避免动画叠加
  isJellyActive.value = true
  if (jellyTimer) clearTimeout(jellyTimer)
  jellyTimer = setTimeout(() => {
    isJellyActive.value = false
  }, 600)   // 与动画时长匹配
}

// 用于清理事件监听的函数
let cleanupListeners: (() => void) | null = null

watch(virtualContainerRef, async (el) => {  
  // 清理旧的监听
  if (cleanupListeners) {
    cleanupListeners()
    cleanupListeners = null
  }
  if (el) {
    // 绑定事件
    el.addEventListener('click', handleReasoningClick)
    el.addEventListener('click', handleToolClick)
    cleanupListeners = () => {
      el.removeEventListener('click', handleReasoningClick)
      el.removeEventListener('click', handleToolClick)
    }
    // 容器出现后强制测量一次（确保初始高度正确）
    await nextTick()
    virtualizer.value?.measure()
    addCopyButtons()
  }
}, { immediate: true })

const isRender = ref(false)

// ---------- 生命周期 ----------
onMounted(async () => {
  checkMobile()
  window.addEventListener('resize', checkMobile)
  await profileStore.loadProfiles()
  renderMermaidDiagrams()
  startObserving()
  fetch('/api/local-ip').then(async (res) => {
    local_ip.value = await res.json()
    localIP.value = local_ip.value
    setQRCodeUrl()
  })
  
  setTimeout(() => {
    addFileTypeClassToLinks(virtualContainerRef.value!)
    isRender.value = true
  }, 150)
})

onUnmounted(() => {
  if (jellyTimer) clearTimeout(jellyTimer)
  window.removeEventListener('resize', checkMobile)
  stopObserving()
})

const showWelcome = ref(false)

watch(() => route.params.id, (newId) => {
  if (isLoading.value) stopGeneration()
  chatStore.activeChatId = newId as string
})

watch(
  () => currentMessages.value.length,
  () => {
    nextTick(() => {
      virtualizer.value?.measure()
      addCopyButtons()
    })
  }
)

watch(() => chatStore.activeChatId, async (newId) => {
    if (newId) {
      await chatStore.loadMessages(newId)
      showWelcome.value = currentMessages.value.length === 0
      
      // ⬇️ 等待虚拟滚动渲染完毕
      await nextTick()
      await new Promise(resolve => requestAnimationFrame(resolve))
      
      if (!showWelcome.value) {
        isAutoScrollEnabled.value = true
        virtualizer.value.scrollToIndex(listItems.value.length - 1, { align: 'end' })
        addCopyButtons()
        renderMermaidDiagrams()
        addFileTypeClassToLinks(virtualContainerRef.value!)
      }
    } else {
      chatStore.loadChats()
    }
  },
  { immediate: true }
)
</script>

<style scoped src="./index.css"></style>