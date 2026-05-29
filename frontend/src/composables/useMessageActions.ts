import { ref } from 'vue'
import { useChatStore, type Message } from '@/stores/chat'


function cleanReasoning(content: string) {
  return content.replace(/<!--reasoning:start-->[\s\S]*?<!--reasoning:end(:\d+\.\d+)?-->/g, '')
    .replace(/<!--tool_calls:start-->[\s\S]*?<!--tool_calls:end-->/g, '')
    .replace(/<!--token_usage:.*?-->/g, '')
    .replace(/<!--thinking_time:.*?-->/g, '')
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
    editContent.value = cleanReasoning(msg.content)
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
      // 从原始内容中提取各种特殊标记块（注意要在修改 msg.content 前提取）
      const reasoningBlocks = msg.content.match(
        /<!--reasoning:start-->[\s\S]*?<!--reasoning:end(:\d+\.\d+)?-->/g
      ) || []
      const toolBlocks = msg.content.match(
        /<!--tool_calls:start-->[\s\S]*?<!--tool_calls:end-->/g
      ) || []
      const tokenUsage = msg.content.match(
        /<!--token_usage:.*?-->/g
      ) || []
      const thinkingTime = msg.content.match(
        /<!--thinking_time:.*?-->/g
      ) || []

      // 通常思考块和工具块放在前面，token/时间放在结尾
      const leading = [...reasoningBlocks, ...toolBlocks].join('\n')
      const trailing = [...tokenUsage, ...thinkingTime].join('\n')

      finalContent = [leading, newText, trailing].filter(Boolean).join('\n')
    }

    msg.content = finalContent
    msg.renderedHtml = null
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