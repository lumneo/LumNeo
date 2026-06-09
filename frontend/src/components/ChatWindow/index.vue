<template>
  <n-config-provider :theme="naiveTheme" :theme-overrides="themeOverrides">
    <n-message-provider>
      <div class="app-container" :class="[configStore.themeMode]">
        <div v-if="isMobile && sidebarOpen" class="sidebar-overlay" @click="sidebarCollapsed = true; sidebarOpen = false"></div>
        <!-- ========== 侧边栏（折叠式） ========== -->
        <aside v-show="!sidebarCollapsed" class="sidebar-panel border-marquee-right" :class="{ collapsed: sidebarCollapsed, 'sidebar-open': sidebarOpen }">
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

        <!-- ========== 主区域 ========== -->
        <main
          class="main-stage"
          :class="{ 'main-stage--full': sidebarCollapsed }"
          @dragenter="onDragEnter($event, isLoading)"
          @dragover="onDragOver"
          @dragleave="onDragLeave"
          @drop="onDrop($event, chatStore.activeChatId, isLoading)"
        >
          <div v-if="isDragging && chatStore.activeChatId" class="drag-overlay">
            <div class="drag-hint"><n-icon><DocumentOutline /></n-icon> 释放文件以上传</div>
          </div>
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
          <div class="message-container">
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
                  :style="{minHeight: virtualizer.getTotalSize() + 'px', width: isMobile? '90%' : '80%', maxWidth: '1000px', position: 'relative', margin: '0 auto'}">
                  <div
                    v-for="virtualRow in virtualItems"
                    :key="<string>virtualRow.key"
                    :ref="<any>measureElement"
                    :data-index="virtualRow.index"
                    :style="{position: 'absolute', top: 0, left: 0, width: '100%', transform: `translateY(${virtualRow.start}px)`}"
                  >
                    <!-- 流式输出气泡（列表最后一项） -->
                    <template v-if="listItems[virtualRow.index]?.__streaming">
                      <div class="streaming-after-item message-row assistant">
                        <div v-if="streamingContent" class="bubble streaming">
                          <MarkdownRender
                            custom-id="chat"
                            :is-dark="isDark"
                            :code-block-props="{ showExpandButton: false, showCollapseButton: false, }"
                            :themes="['vitesse-dark', 'vitesse-light']"
                            code-block-dark-theme="vitesse-dark"
                            code-block-light-theme="vitesse-light"
                            :content="processMessageContent(streamingContent, true)"
                            :final="false"
                            mode="chat"
                            smooth-streaming="auto"
                            :fade="false"
                            :typewriter="false"
                            :max-live-nodes="0"
                            :batch-rendering="true"
                            :custom-html-tags="['reasoning', 'toolcalls', 'toolpreview', 'tokenusage']"
                          />
                        </div>
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

                          <template v-if="listItems[virtualRow.index] === regeneratingMsg">
                            <div style="height: 1px"></div>
                          </template>
                          <template v-else>
                            <template v-if="listItems[virtualRow.index].role === 'user'">
                              <div class="message-content user-content" v-text="listItems[virtualRow.index].content.trim()"></div>
                            </template>
                            <template v-else>
                              <div class="message-content">
                                <MarkdownRender
                                  custom-id="chat"
                                  :is-dark="isDark"
                                  :code-block-props="{ showExpandButton: false, showCollapseButton: false, }"
                                  :themes="['vitesse-dark', 'vitesse-light']"
                                  code-block-dark-theme="vitesse-dark"
                                  code-block-light-theme="vitesse-light"
                                  :content="processMessageContent(listItems[virtualRow.index].content.trim(), false)"
                                  :final="true"
                                  :fade="false"
                                  :typewriter="false"
                                  :max-live-nodes="500"
                                  :custom-html-tags="['reasoning', 'toolcalls', 'toolpreview', 'tokenusage']"
                                />
                              </div>
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
            <transition name="fade">
              <n-button v-if="!isAutoScrollEnabled && currentMessages.length !== 0" circle class="scroll-to-bottom-btn" @click="forceScrollToBottom">
                <n-icon size="22"><ArrowDownOutline /></n-icon>
                <div v-show="isLoading" class="rotate-circle"></div>
              </n-button>
            </transition>
            <div>
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
                @keydown.enter.exact.prevent="onSendMessage"
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

      <SettingsDrawer v-model:show="showSettings" />
      <n-modal v-model:show="showEditModal" preset="dialog" draggable :mask-closable="false" title="编辑消息" positive-text="保存" negative-text="取消"
        @positive-click="onSaveEdit">
        <n-input v-model:value="editContent" type="textarea" :autosize="{ minRows: 2, maxRows: 10 }" placeholder="请输入内容"/>
      </n-modal>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup lang="ts">
import { ref, nextTick, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NConfigProvider, NMessageProvider, NButton, NInput,
  NUpload, NList, NListItem, NIcon, NScrollbar, NImage, NFlex,
  NSelect, NModal, NPopconfirm, NPopover, NQrCode
} from 'naive-ui'
import { SettingsOutline, DocumentOutline, MenuOutline, QrCodeOutline, ArrowDownOutline } from '@vicons/ionicons5'
import { MarkdownRender } from 'markstream-vue'
import 'markstream-vue/index.css'

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
import { localIP, processMessageContent, normalizeFileRef } from '@/utils/message'

// ===== markstream-vue 自定义标签注册 =====
import { setCustomComponents, removeCustomComponents } from 'markstream-vue'
import ReasoningNode from '@/components/CustomNodes/ReasoningNode.vue'
import ToolCallsNode from '@/components/CustomNodes/ToolCallsNode.vue'
import ToolPreviewNode from '@/components/CustomNodes/ToolPreviewNode.vue'
import TokenUsageNode from '@/components/CustomNodes/TokenUsageNode.vue'
import ImageNode from '@/components/CustomNodes/ImageNode.vue'
import LinkNode from '@/components/CustomNodes/LinkNode.vue'


// 注册自定义组件（使用静态 ID 'chat'，与 MarkdownRender 的 custom-id 匹配）
setCustomComponents('chat', {
  reasoning: ReasoningNode,
  toolcalls: ToolCallsNode,    
  toolpreview: ToolPreviewNode,
  tokenusage: TokenUsageNode,  
  image: ImageNode,
  link: LinkNode,
})

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

const isAutoScrollEnabled = ref(true)
const SCROLL_THRESHOLD = 180

const isDark = computed(() => configStore.themeMode === 'dark')

function checkMobile() {
  isMobile.value = window.innerWidth <= 768
  if (!isMobile.value) sidebarOpen.value = false
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

const virtualContainerRef = ref<HTMLElement | null>(null)

const currentMessages = computed(() => chatStore.currentChatMessages)
const listItems = computed<any>(() => {
  const msgs = currentMessages.value as (Message | { __streaming: boolean })[]
  return isLoading.value ? [...msgs, { __streaming: true }] : msgs
})

const virtualItems = computed(() => virtualizer.value?.getVirtualItems() ?? [])

const measureElement = (el: Element | null) => {
  if (el) {
    virtualizer.value?.measureElement(el)
  }
}

const virtualizer = useVirtualizer(
  computed(() => ({
    count: listItems.value.length,
    getScrollElement: () => virtualContainerRef.value,
    getItemKey: (index) => {
      const msg = listItems.value[index]
      if (!msg) return `fallback-${index}`
      return msg.__streaming ? `streaming-${index}` : `msg-${msg.id || index}`
    },
    estimateSize: (index) => {
      const msg = listItems.value[index]
      if (!msg) return 100
      if (msg.__streaming) return 80

      if (msg.role === 'user') {
        const len = msg.content?.length || 0
        return Math.min(80 + Math.floor(len / 30) * 24, 300)
      }

      const len = msg.content?.length || 0
      return Math.max(200, Math.min(len * 1.2, 5000))
    },
    overscan: 15,
    measureElement: (el) => el.getBoundingClientRect().height,
  }))
)

onStreamEnd.value = (fullText: string) => {
  if (regeneratingMsg.value) {
    const msg = regeneratingMsg.value
    msg.content = fullText
    regeneratingMsg.value = null
    return
  }
}


watch(() => selected.value, (newVal) => {
  localStorage.setItem('thinking', newVal ? 'true' : 'false')
})

const sidebarCollapsed = ref(true)
const showSettings = ref(false)

const profileOptions = computed(() =>
  profileStore.profiles.map((p) => ({ label: p.name, value: p.id }))
)

const isProgrammaticScroll = ref(false)

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

    uploadedFiles.value.push({
      filename,
      type: file.type || 'application/octet-stream',
      url
    })
  }

  lastPasteCount.value = filesToAdd.length
  pasteToastVisible.value = true
  if (pasteToastTimer) clearTimeout(pasteToastTimer)
  pasteToastTimer = setTimeout(() => {
    pasteToastVisible.value = false
  }, 1800)
}

function openChat(chatId: string) {
  if (isLoading.value) stopGeneration()
  chatStore.activeChatId = chatId  
  router.push({ name: 'chat', params: { id: chatId } })
  setTimeout(() => {
    setQRCodeUrl()
  }, 300)
}

function onSendMessage() {
  isAutoScrollEnabled.value = true
  sendMessage(uploadedFiles.value, () => {
    if (isAutoScrollEnabled.value) {
      scrollToBottom()
    }
  })
  clearFiles()
}

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

function forceScrollToBottom() {
  isAutoScrollEnabled.value = true
  virtualizer.value.scrollToIndex(listItems.value.length - 1, { align: 'end' })
}

const isJellyActive = ref(false)
let jellyTimer: ReturnType<typeof setTimeout> | null = null

function triggerJelly() {
  if (isJellyActive.value) return
  isJellyActive.value = true
  if (jellyTimer) clearTimeout(jellyTimer)
  jellyTimer = setTimeout(() => {
    isJellyActive.value = false
  }, 600)
}

const isRender = ref(false)

onMounted(async () => {
  checkMobile()
  let resizeTimer: ReturnType<typeof setTimeout>
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer)
    resizeTimer = setTimeout(checkMobile, 150)
  })
  await profileStore.loadProfiles()
  fetch('/api/local-ip').then(async (res) => {
    local_ip.value = await res.json()
    localIP.value = local_ip.value
    setQRCodeUrl()
  })

  setTimeout(() => {
    isRender.value = true
  }, 150)
})

onUnmounted(() => {
  if (jellyTimer) clearTimeout(jellyTimer)
  if (pasteToastTimer) clearTimeout(pasteToastTimer)
  window.removeEventListener('resize', checkMobile)
  // 清理 markstream-vue 自定义组件注册
  removeCustomComponents('chat')
})

const showWelcome = ref(false)

watch(() => route.params.id, (newId) => {
  if (isLoading.value) stopGeneration()
  chatStore.activeChatId = newId as string
})

watch(() => chatStore.activeChatId, async (newId) => {
    if (newId) {
      await chatStore.loadMessages(newId)
      showWelcome.value = currentMessages.value.length === 0

      await nextTick()
      await new Promise(resolve => requestAnimationFrame(resolve))

      if (!showWelcome.value) {
        isAutoScrollEnabled.value = true
        virtualizer.value.scrollToIndex(listItems.value.length - 1, { align: 'end' })
      }
    } else {
      chatStore.loadChats()
    }
  },
  { immediate: true }
)

watch(
  () => chatStore.currentChatMessages.length,
  () => {
    nextTick(async () => {
      if (isAutoScrollEnabled.value) {
        scrollToBottom()
      }
    })
  }
)
</script>

<style scoped src="./index.css"></style>