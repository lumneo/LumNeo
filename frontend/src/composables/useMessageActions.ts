import { ref } from 'vue'
import { useChatStore, type Message } from '@/stores/chat'


function cleanReasoning(content: string) {
  return content
    .replace(/<!--reasoning:start-->[\s\S]*?<!--reasoning:end(:\d+\.\d+)?-->/g, '')
    .replace(/<!--tool_calls:start-->[\s\S]*?<!--tool_calls:end-->/g, '')
    .replace(/<!--token_usage:.*?-->/g, '')
    .replace(/<!--thinking_time:.*?-->/g, '')
    // 新增：清理流式工具调用预览快照
    .replace(/<!--tool_preview:start:[^>]+-->[\s\S]*?<!--tool_preview:end:[^>]+-->/g, '')
    // 新增：清理流式过程中的临时状态提示（如“准备执行操作…”）
    .replace(/<!--status:show:[^>]+-->[\s\S]*?<!--status:hide:[^>]+-->/g, '')
    // 保留原有的未闭合标记清理（思考块、工具调用块开始标记）
    .replace(/<!--reasoning:start-->/g, '')
    .replace(/<!--tool_calls:start-->/g, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}
export function useMessageActions() {
  const chatStore = useChatStore()

  const showEditModal = ref(false)
  const editingMsg = ref<Message | null>(null)
  const editContent = ref('')
  const copySvgName = ref('copy')


  async function copyContent(msg: Message) {
    const textToCopy = cleanReasoning(msg.content)
    let copySuccess = false

    // 1. 优先使用现代 Clipboard API
    if (navigator.clipboard && window.isSecureContext) {
      try {
        await navigator.clipboard.writeText(textToCopy)
        copySuccess = true
      } catch (err) {
        console.warn('Clipboard API 失败:', err)
      }
    }

    // 2. 降级方案：传统 execCommand（兼容移动端 WebView）
    if (!copySuccess) {
      const textarea = document.createElement('textarea')
      textarea.value = textToCopy
      textarea.style.position = 'fixed'
      textarea.style.top = '-9999px'
      textarea.style.left = '-9999px'
      textarea.style.opacity = '0'
      document.body.appendChild(textarea)
      textarea.select()
      textarea.setSelectionRange(0, 99999) // 移动端必需
      try {
        copySuccess = document.execCommand('copy')
      } catch (err) {
        console.warn('execCommand 复制失败:', err)
      }
      document.body.removeChild(textarea)
    }

    // 复制成功，更新图标
    copySvgName.value = 'succ'
    setTimeout(() => {
      copySvgName.value = 'copy'
    }, 1000)
  }

  function startEditMessage(msg: Message) {
    editingMsg.value = msg
    if (msg.role === 'assistant') {
      const content = msg.content
      // 按所有特殊块的结束标记切割，取最后一部分作为初始编辑内容
      const parts = content.split(/<!--(?:reasoning:end|tool_calls:end|tool_preview:end)[^>]*-->/)
      let lastPart = parts[parts.length - 1] || ''
      // 去掉尾部的 token 统计等不可见标记
      lastPart = lastPart.replace(/<!--token_usage:.*?-->/g, '').replace(/<!--thinking_time:.*?-->/g, '').trim()
      editContent.value = lastPart
    } else {
      editContent.value = msg.content
    }
    showEditModal.value = true
  }

  async function saveEdit(regenerateCallback?: () => Promise<void>) {
    if (!editingMsg.value) return
    const msg = editingMsg.value
    const newText = editContent.value.trim()

    if (newText === msg.content) {
      showEditModal.value = false
      return
    }

    let finalContent = newText
    if (msg.role === 'assistant') {
      const content = msg.content
      // 找到最后一个特殊块结束的位置
      const lastEndMatch = content.match(/.*<!--(?:reasoning:end|tool_calls:end|tool_preview:end)[^>]*-->/g)
      if (lastEndMatch && lastEndMatch.length > 0) {
        const lastEndStr = lastEndMatch[lastEndMatch.length - 1]
        const splitIndex = content.lastIndexOf(lastEndStr) + lastEndStr.length
        // 前面部分（所有思考、工具块）原封不动
        const prefix = content.slice(0, splitIndex)
        // 后面部分保留 token_usage / thinking_time，但去掉原有正文
        const suffix = content.slice(splitIndex)
        const tokenMarkers = (suffix.match(/<!--token_usage:.*?-->/g) || []).join('')
        const timeMarkers = (suffix.match(/<!--thinking_time:.*?-->/g) || []).join('')
        finalContent = prefix + '\n' + newText + '\n' + tokenMarkers + timeMarkers
      } else {
        // 没有特殊块，直接替换正文并保留尾部统计
        const tokenMarkers = (content.match(/<!--token_usage:.*?-->/g) || []).join('')
        const timeMarkers = (content.match(/<!--thinking_time:.*?-->/g) || []).join('')
        finalContent = newText + '\n' + tokenMarkers + timeMarkers
      }
    }

    msg.content = finalContent
    await chatStore.editMessage(msg.id!, finalContent)
    showEditModal.value = false

    // 如果编辑的是用户消息，删除后续回复并重新生成
    if (msg.role === 'user') {
      const msgs = chatStore.currentChatMessages
      const idx = msgs.findIndex((m) => m.id === msg.id)
      if (idx !== -1 && idx < msgs.length - 1) {
        const nextMsg = msgs[idx + 1]
        await chatStore.deleteMessage(nextMsg.id!)
      }
      if (regenerateCallback) {
        await regenerateCallback()
      }
    }
  }

  // 重命名对话
  const renamingChatId = ref<string | null>(null)
  const renameText = ref('')

  function startRename(chat: { id: string; title: string }) {
    renamingChatId.value = chat.id
    renameText.value = chat.title
  }

  async function confirmRename(chatId: string) {
    if (!renameText.value.trim()) return
    await chatStore.renameChat(chatId, renameText.value.trim())
    renamingChatId.value = null
  }

  return {
    showEditModal,
    editingMsg,
    editContent,
    copySvgName,
    copyContent,
    startEditMessage,
    saveEdit,
    renamingChatId,
    renameText,
    startRename,
    confirmRename,
  }
}