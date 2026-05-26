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
              <Introduction @click="sidebarOpen=true;sidebarCollapsed=false" />
            </div>
            <div class="message-main" v-else>
              <div v-if="showWelcome && currentMessages.length === 0">
                <!-- <svgWelcome /> -->
              </div>
              <div v-for="(msg, idx) in currentMessages" :key="msg.id ?? idx" :class="['message-row', msg.role]" @click="">
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

                  <!-- 如果是正在重新生成的消息，显示流式内容；否则显示原内容 -->
                  <div v-if="msg === regeneratingMsg" class="message-row assistant">
                    <div v-if="streamingContent" class="bubble streaming" v-html="renderMessageHtml(streamingContent, true)"></div>
                    <svgLoading v-else />
                  </div>
                  <div v-else class="message-content" v-html="renderMessageHtml(msg.content.trim(), false)" @click="onContainerClick"></div>

                  <!-- 操作按钮（只在非加载状态悬停显示） -->
                  <div :class="`message-actions ${msg.role === 'assistant' ? 'assistant-actions' : 'user-actions'}`" v-if="!isLoading || msg !== regeneratingMsg">
                    <n-button text class="icon-btn" size="small" @click="copyContent(msg)" title="复制">
                      <template #icon><n-icon><m-svg :name="copySvgName" /></n-icon></template>
                    </n-button>
                    <n-button v-if="msg.role === 'assistant' && idx == currentMessages.length - 1" text class="icon-btn" size="small" @click="regenerateResponse(msg)" title="重新生成">
                      <template #icon><n-icon ><m-svg name="refresh"/></n-icon></template>
                    </n-button>
                    <n-button text class="icon-btn" size="small" @click="startEditMessage(msg)" title="编辑">
                      <template #icon><n-icon :size="20"><m-svg name="edit"/></n-icon></template>
                    </n-button>
                    <n-popconfirm 
                    @positive-click="() => chatStore.deleteMessage(msg.id!)" 
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
              <!-- 流式输出中的临时气泡 -->
              <div v-if="isLoading && !regeneratingMsg" class="message-row assistant">
                <div v-if="streamingContent" class="bubble streaming" v-html="renderMessageHtml(streamingContent, true)"></div>
                <svgLoading v-else />
              </div>
            </div>
          </div>

          <!-- 底部输入区 -->
          <div class="compose-area" v-if="chatStore.activeChatId">
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
import { SettingsOutline, DocumentOutline, MenuOutline, QrCodeOutline, BarcodeOutline } from '@vicons/ionicons5'
import { useChatStore } from '@/stores/chat'
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
    sendMessage, regenerateResponse, regenerateFromCurrentHistory, stopGeneration 
} = useChat()

const { showEditModal, editContent, copySvgName, copyContent,
  startEditMessage, saveEdit, renamingChatId, renameText, startRename, confirmRename 
} = useMessageActions()

const { messageListRef, addCopyButtons, renderMermaidDiagrams, startObserving, stopObserving } = useCodeEnhancer()


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


// ---------- 滚动到底部 ----------
function scrollToBottom() {
  if (messageListRef.value) {
    messageListRef.value.scrollTop = messageListRef.value.scrollHeight
  }
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
  sendMessage(uploadedFiles.value, scrollToBottom)
  clearFiles()
}

// ---------- 编辑后重新生成包装 ----------
async function onRegenerateFromCurrentHistory() {
  await regenerateFromCurrentHistory(scrollToBottom)
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

// ---------- 监视消息变化以重新渲染增强内容 ----------
watch( () => chatStore.currentChatMessages.length, () => {
    renderMermaidDiagrams()
    addCopyButtons()
    scrollToBottom()
  }
)

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
    addFileTypeClassToLinks(document.body)
  }, 150)
})

onUnmounted(() => {
  window.removeEventListener('resize', checkMobile)
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
      addCopyButtons()
      renderMermaidDiagrams()
      scrollToBottom()
    } else {
      chatStore.loadChats()
    }
  },
  { immediate: true }
)
</script>

<style scoped src="./index.css"></style>