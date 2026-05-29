import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export interface Message {
  id?: number
  role: 'user' | 'assistant' | 'system'
  content: any
  file_ref?: any
  renderedHtml?: string | null // 用于缓存渲染后的 HTML
}

export interface Chat {
  id: string
  title: string
  messages: Message[]
}

export const useChatStore = defineStore('chat', () => {
  const chats = ref<Chat[]>([])
  const activeChatId = ref<string>('')
  const enableProfile = ref(localStorage.getItem('enableProfile') === 'true')

  // 从后端加载对话列表
  async function loadChats() {
    try {
      const res = await fetch('/api/chats/')
      const data = await res.json()
      chats.value = data.map((c: any) => ({ id: c.id, title: c.title, messages: [] }))
    } catch (e) {
      console.error('加载对话列表失败', e)
      // 降级：本地创建一个临时对话
      // const id = Date.now().toString()
      // chats.value = [{ id, title: '新对话', messages: [] }]
      // activeChatId.value = id
    }
  }

  // 创建新对话
  async function addChat() {
    const res = await fetch('/api/chats/', { method: 'POST' })
    const newChat = await res.json()
    newChat.messages = []
    chats.value.unshift(newChat)
    activeChatId.value = newChat.id
    return newChat.id
  }

  // 重命名对话
  async function renameChat(chatId: string, newTitle: string) {
    const chat = chats.value.find(c => c.id === chatId)
    if (!chat) return
    // 本地更新
    chat.title = newTitle
    // 调用后端 PATCH API
    await fetch(`/api/chats/${chatId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: newTitle })
    }).catch(e => console.warn('重命名失败', e))
  }

  // 删除对话
  async function deleteChat(chatId: string) {
    await fetch(`/api/chats/${chatId}`, { method: 'DELETE' })
    chats.value = chats.value.filter(c => c.id !== chatId)
    if (activeChatId.value === chatId && chats.value.length > 0) {
      activeChatId.value = chats.value[0].id
    } else if (chats.value.length === 0) {
      // 如果所有对话都被删除，自动创建一个新对话
      await addChat()
    }
  }

  // 加载某个对话的历史消息
  async function loadMessages(chatId: string) {
    if (!chats.value.length) {
      await loadChats()
    }
    const chat = chats.value.find(c => c.id === chatId)
    if (!chat) return
    const res = await fetch(`/api/chats/${chatId}/messages`)
    const msgs = await res.json()
    
    chat.messages = msgs    
  }

  // 当前对话的消息（过滤 system）
  const currentChatMessages = computed(() => {
    const chat = chats.value.find(c => c.id === activeChatId.value)
    
    return chat ? chat.messages.filter(m => m.role !== 'system') : []
  })

  // 获取完整消息（含 system）
  function getActiveMessages(): Message[] {
    const chat = chats.value.find(c => c.id === activeChatId.value)
    return chat ? [...chat.messages] : []
  }

  // ---------- 立即添加到本地（不等待后端） ----------
  async function addMessageToLocal(msg: Message) {
    const chat = chats.value.find(c => c.id === activeChatId.value)
    if (!chat) return
    if (msg.id == null) {
      msg.id = Date.now()
    }
    chat.messages.push(msg)
    // 自动更新标题
    if (msg.role === 'user' && chat.messages.filter(m => m.role === 'user').length === 1) {
      chat.title = msg.content.substring(0, 15) + (msg.content.length > 15 ? '...' : '')
      // 可选：告知后端更新标题（异步，不阻塞）
      fetch(`/api/chats/${chat.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: chat.title })
      }).catch(() => {})
    }
  }

  // ---------- 新增：异步保存到后端 ----------
  async function saveMessageToBackend(msg: Message) {
    if (!activeChatId.value) return
    const res = await fetch(`/api/chats/${activeChatId.value}/messages`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ 
        role: msg.role, 
        content: msg.content,
        file_ref:  Array.isArray(msg.file_ref) 
        ? msg.file_ref.map(f => ({
            filename: f.filename,
            type: f.type,
            url: f.url
          })) 
        : msg.file_ref 
          ? {
              filename: msg.file_ref.filename,
              type: msg.file_ref.type,
              url: msg.file_ref.url
            }
          : null
      })
    })
    const data = await res.json()
    // 将后端返回的真实 ID 赋给本地消息对象
    if (data.id != null) {
      msg.id = data.id
    }
  }

  // 原有的 addMessageToActive 现在只是组合调用
  async function addMessageToActive(msg: Message) {
    addMessageToLocal(msg)
    await saveMessageToBackend(msg)
  }

  // 编辑消息内容（本地 + 后端）
  async function editMessage(messageId: number, newContent: string) {
    const chat = chats.value.find(c => c.id === activeChatId.value)
    if (!chat) return
    const msg = chat.messages.find(m => m.id === messageId)
    if (msg) {
      msg.content = newContent
      await fetch(`/api/chats/${activeChatId.value}/messages/${messageId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role: msg.role, content: newContent })
      }).catch(e => console.warn('更新消息失败', e))
    }
  }

  // 删除消息（本地移除 + 后端删除）
  async function deleteMessage(messageId: number) {
    if (!activeChatId.value) return
    // 调用后端，只删除单条消息
    await fetch(`/api/chats/${activeChatId.value}/messages/${messageId}?cascade=false`, {
      method: 'DELETE'
    }).catch(e => console.warn('删除消息失败', e))

    // 从本地列表中移除该条消息
    const chat = chats.value.find(c => c.id === activeChatId.value)
    if (chat) {
      chat.messages = chat.messages.filter(m => m.id !== messageId)
    }
  }

  return {
    chats,
    activeChatId,
    enableProfile,
    currentChatMessages,
    loadChats,
    addChat,
    renameChat,
    deleteChat,
    loadMessages,
    getActiveMessages,
    addMessageToActive,
    addMessageToLocal,
    saveMessageToBackend,
    editMessage,
    deleteMessage
  }
})