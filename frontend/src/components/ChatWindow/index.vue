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
                <!-- <svgWelcome /> -->
              </div>
              <DynamicScroller
                :items="currentMessages"
                :min-item-size="80"
                key-field="id"
                class="virtual-scroller"
                ref="scrollerRef"
                @scroll="handleScroll"
              >
                <!-- slot 写法，item 就是单条 msg，index 是索引，active 表示当前是否在可视区 -->
                <template #default="{ item: msg, index: idx, active }">
                  <!-- ✅ 包裹 DynamicScrollerItem，并传入 size-dependencies 监听内容变化以重新计算高度 -->
                  <DynamicScrollerItem
                    :item="msg"
                    :active="active"
                    :data-index="idx"
                  >
                    <div :class="['message-row', msg.role]" @click="">
                      <div class="bubble" :class="{ 'has-file': msg.file_ref }">
                        <!-- 文件附件 -->
                        <div v-if="normalizeFileRef(msg.file_ref).length" class="message-files">
                          <div v-for="f in normalizeFileRef(msg.file_ref)" :key="f.filename" class="msg-file-item">
                            <n-image v-if="f.type.startsWith('image/')" width="200" :src="f.url" class="msg-file-img" />
                            <div v-else class="msg-file-other">
                              <n-icon><DocumentOutline /></n-icon>
                              <a :href="f.url" target="_blank">{{ f.filename }}</a>
                            </div>
                          </div>
                        </div>

                        <!-- 如果是正在重新生成的消息，只渲染占位，不显示旧内容或流式内容 -->
                        <template v-if="msg === regeneratingMsg">
                          <!-- 可留空，或加一个不可见的占位元素防止高度塌陷 -->
                          <div style="height: 1px;"></div>
                        </template>
                        <template v-else>
                          <template v-if="msg.role === 'user'">
                            <div class="message-content user-content" v-text="msg.content.trim()"></div>
                          </template>
                          <template v-else>
                            <div class="message-content" v-html="msg.renderedHtml || renderMessageHtml(msg.content.trim(), false)" @click="onContainerClick"></div>
                          </template>
                        </template>

                        <!-- 操作按钮（只在非加载状态悬停显示） -->
                        <div :class="`message-actions ${msg.role === 'assistant' ? 'assistant-actions' : 'user-actions'}`" v-if="!isLoading || msg !== regeneratingMsg">
                          <n-button text class="icon-btn" size="small" @click="copyContent(msg)" title="复制">
                            <template #icon><n-icon><m-svg :name="copySvgName" /></n-icon></template>
                          </n-button>
                          <n-button v-if="msg.role === 'assistant' && idx == currentMessages.length - 1" text class="icon-btn" size="small" @click="handleRegenerateResponse(msg)" title="重新生成">
                            <template #icon><n-icon ><m-svg name="refresh"/></n-icon></template>
                          </n-button>
                          <n-button text class="icon-btn" size="small" @click="startEditMessage(msg)" title="编辑">
                            <template #icon><n-icon :size="20"><m-svg name="edit"/></n-icon></template>
                          </n-button>
                          <n-popconfirm 
                          @positive-click="() => chatStore.deleteMessage(<number>msg.id!)" 
                          negative-text="取消" 
                          positive-text="好的"
                          :negative-button-props="{size: 'tiny'}"
                          :positive-button-props="{size: 'tiny'}"
                          >
                            <template #trigger>
                              <n-button text class="icon-btn" size="small" title="删除">
                                <template #icon><n-icon :size="22"><m-svg name="del"/></n-icon></template>
                              </n-button>
                            </template>
                            确定要删除这条消息吗？
                          </n-popconfirm>
                        </div>
                      </div>
                    </div>
                  </DynamicScrollerItem>
                </template>
                <template #after>
                  <!-- 流式输出中的临时气泡 -->
                  <div v-if="isLoading" class="streaming-after-item message-row assistant">
                    <div v-if="streamDisplayHtml" class="bubble streaming" v-html="streamDisplayHtml"></div>
                    <svgLoading v-else />
                  </div>
                </template>
              </DynamicScroller>
            </div>
          </div>

          <!-- 底部输入区 -->
          <div class="compose-area" v-if="chatStore.activeChatId">
            <!-- ✅ 回到底部按钮 -->
            <transition name="fade">
              <n-button 
                v-if="!isAutoScrollEnabled" 
                circle 
                class="scroll-to-bottom-btn" 
                @click="forceScrollToBottom"
              >
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
                    <n-icon size="22"><BarcodeOutline /></n-icon>
                  </template>
                  重新生成AI响应
                </n-button>
              </div>
              <n-input
                v-model:value="currentInput"
                type="textarea"
                name="talk"
                placeholder="今天要做点什么？"
                :autosize="{ minRows: 4, maxRows: 6 }"
                @keydown.enter.exact="onSendMessage"
                :disabled="isLoading || !chatStore.activeChatId || !activeModelId"
                class="compose-input"
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
              <n-button
                v-if="!isLoading"
                class="send-btn"
                @click="onSendMessage"
                strong
                secondary
                type="primary"
                :disabled="!!(!currentInput.trim().length && chatStore.activeChatId)"
              >
                <template #icon>
                  <n-icon><m-svg name="send"/></n-icon>
                </template>
              </n-button>
              <n-button
              v-else
                class="send-btn"
                @click="stopGeneration"
                strong
                secondary
                type="primary"
              >
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
import { DynamicScroller, DynamicScrollerItem } from 'vue-virtual-scroller'
import 'vue-virtual-scroller/dist/vue-virtual-scroller.css'

import { useChatStore, type Message } from '@/stores/chat'
import { useConfigStore, fileConfig } from '@/stores/config'
import { useProfileStore } from '@/stores/profiles'
import SettingsDrawer from '@/components/SettingsDrawer.vue'
import svgWelcome from '@/components-svg/svgWelcome.vue'
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
const isAutoScrollEnabled = ref(true)            // 自动滚动开关
const SCROLL_THRESHOLD = 80                     // 距离底部的容差阈值（像素）
const scrollerRef = ref<any>(null)

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

const { messageListRef, addCopyButtons, renderMermaidDiagrams, startObserving, stopObserving, setStreaming } = useCodeEnhancer()

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
      scrollerRef.value?.forceUpdate() // 强制更新，确保滚动条位置正确
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

// ---------- 当前消息（过滤 system） ----------
const currentMessages = computed(() => chatStore.currentChatMessages)

const isProgrammaticScroll = ref(false)

// ---------- 滚动到底部 ----------
function scrollToBottom() {
  if (scrollerRef.value) {
    isProgrammaticScroll.value = true
    setTimeout(() => {
      scrollerRef.value.scrollToBottom()
    }, 50)
    nextTick(() => {
      setTimeout(() => {
        isProgrammaticScroll.value = false
      }, 200)
    })
  }
}

function updateScrollState() {
  if (scrollerRef.value?.$el) {
    const target = scrollerRef.value.$el
    const scrollTop = target.scrollTop
    const scrollHeight = target.scrollHeight
    const clientHeight = target.clientHeight

    // 判断当前是否真的还在底部
    const isAtBottom = (scrollHeight - scrollTop - clientHeight) <= SCROLL_THRESHOLD
    isAutoScrollEnabled.value = isAtBottom
  }
}

function handleScroll(event: Event) {
  if (isProgrammaticScroll.value) return

  const target = event.target as HTMLElement
  if (!target) return

  updateScrollState()
}

async function createChat() {
  const newChatId = await chatStore.addChat()
  openChat(newChatId)
}

function setQRCodeUrl () {
  qrCodeUrl.value = window.location.href.replace(/\b(?:localhost|\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b/g, local_ip.value)
}

// ---------- 导航 ----------
function openChat(chatId: string) {
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
    // 可选：preview-src 如果大图不同
    // previewSrc: largeImageUrl,
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
  // 使用 DynamicScroller 的 scrollToBottom 方法
  if (scrollerRef.value) {
    scrollerRef.value.scrollToBottom()
  }
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

          setTimeout(() => {
            scrollerRef.value?.forceUpdate()
            updateScrollState()
          }, 60)
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
          setTimeout(() => {
            scrollerRef.value?.forceUpdate() 
            updateScrollState()
          }, 60)
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
      // 如果处于自动滚动模式，则滚动到底部
      if (isAutoScrollEnabled.value) {
        scrollToBottom()
      }
    })
  }
)

const isRender = ref(false)

// ---------- 生命周期 ----------
onMounted(async () => {
  checkMobile()
  window.addEventListener('resize', checkMobile)
  if (messageListRef.value) {
    messageListRef.value.addEventListener('scroll', handleScroll, { passive: true })
    messageListRef.value.addEventListener('click', handleReasoningClick)
    messageListRef.value.addEventListener('click', handleToolClick)
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
  window.removeEventListener('resize', checkMobile)
  if (messageListRef.value) {
    messageListRef.value.removeEventListener('scroll', handleScroll)
    messageListRef.value.removeEventListener('click', handleReasoningClick)
    messageListRef.value.removeEventListener('click', handleToolClick)
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