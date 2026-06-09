// src/utils/message.ts
import { ref } from 'vue'
import { type Message } from '@/stores/chat'
import type { UploadedFile } from '@/composables/useFileUpload'


/** 转义 HTML 特殊字符，防止被浏览器渲染 */
function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

export const localIP = ref('')


/** 解析思考块和工具调用，输出 markstream-vue 自定义标签格式 */
export function processMessageContent(text: string, isStreaming = false): string {
  if (!text) return ''

  let processedText = text

  // 1. 处理完整的思考块 → 转换为 <reasoning> 自定义标签
  processedText = processedText.replace(
    /<!--reasoning:start-->([\s\S]*?)<!--reasoning:end:(.*?)-->/g,
    (_, content, time) => {
      // 将 mermaid 代码块转为 text 避免内部渲染问题
      content = content.replace(/```mermaid(\s|$)/g, '```text$1')
      // 转义内容中的 </reasoning> 避免提前闭合
      const safeContent = content.replace(/<\/reasoning>/g, '\u003c/reasoning>')
      return `<reasoning time="${escapeHtml(time)}">${safeContent}</reasoning>`
    }
  )

  // 2. 处理流式未闭合的思考块
  if (isStreaming) {
    const startIdx = processedText.indexOf('<!--reasoning:start-->')
    if (startIdx !== -1 && !processedText.includes('<!--reasoning:end:-->')) {
      let afterStart = processedText.substring(startIdx + '<!--reasoning:start-->'.length)
      afterStart = afterStart.replace(/```mermaid(\s|$)/g, '```text$1')
      // 转义闭合标签
      const safeContent = afterStart.replace(/<\/reasoning>/g, '\u003c/reasoning>')
      // 移除原始标记，替换为未闭合的自定义标签（markstream-vue 会自动处理 loading 状态）
      processedText = processedText.substring(0, startIdx) + `<reasoning loading="true">${safeContent}`
    }
  }

  // 如果已经出现最终的工具调用块，则清除所有工具预览标记
  const hasToolCallsStart = processedText.includes('<!--tool_calls:start-->')
  const hasToolCallsEnd   = processedText.includes('<!--tool_calls:end-->')
  const shouldClearPreview = hasToolCallsStart && (!isStreaming || hasToolCallsEnd)

  if (shouldClearPreview) {
      // 删除闭合的预览段
      processedText = processedText.replace(/<!--tool_preview:start:\S+?:.*?-->[\s\S]*?<!--tool_preview:end:\S+?:.*?-->/g, '')
      // 删除未闭合的预览段
      processedText = processedText.replace(/<!--tool_preview:start:\S+?:.*?-->[\s\S]*$/g, '')
      // 清理残留 end
      processedText = processedText.replace(/<!--tool_preview:end:\S+?:.*?-->/g, '')
  }

  // 3. 处理工具预览 → 转换为 <toolpreview> 自定义标签（注意：标签名不能包含下划线）
  if (!processedText.includes('<!--tool_calls:start-->')) {
    const startRegex = /<!--tool_preview:start:(\S+?):(.*?)-->/g
    const endRegex = /<!--tool_preview:end:(\S+?):.*?-->/g

    let firstStart = -1
    let lastEnd = -1
    let startMatch

    // 找到第一个 start
    startRegex.lastIndex = 0
    if ((startMatch = startRegex.exec(processedText)) !== null) {
      firstStart = startMatch.index
    }

    // 找到最后一个 end
    let endMatch
    endRegex.lastIndex = 0
    while ((endMatch = endRegex.exec(processedText)) !== null) {
      lastEnd = endMatch.index + endMatch[0].length
    }

    if (firstStart !== -1) {
      const previewRegionEnd = lastEnd !== -1 ? lastEnd : processedText.length
      const previewRegion = processedText.substring(firstStart, previewRegionEnd)

      // 重新扫描区域内所有 start / end，按 idx 分组
      const idxSet = new Set<string>()
      const startPositions: Array<{ idx: string; name: string; pos: number }> = []
      const endPositions: Array<{ idx: string; pos: number }> = []

      startRegex.lastIndex = 0
      let sMatch
      while ((sMatch = startRegex.exec(previewRegion)) !== null) {
        startPositions.push({
          idx: sMatch[1],
          name: sMatch[2],
          pos: sMatch.index + sMatch[0].length
        })
        idxSet.add(sMatch[1])
      }
      endRegex.lastIndex = 0
      let eMatch
      while ((eMatch = endRegex.exec(previewRegion)) !== null) {
        endPositions.push({ idx: eMatch[1], pos: eMatch.index })
      }

      // 提取每个工具的参数文本
      const tools: Array<{ name: string; args: string; streaming: boolean }> = []
      for (const idx of idxSet) {
        const sItem = startPositions.find(s => s.idx === idx)
        const eItem = endPositions.find(e => e.idx === idx)
        const name = sItem?.name || ''
        const startIdx = sItem?.pos ?? 0
        const endIdx = eItem?.pos ?? previewRegion.length
        const argsRaw = previewRegion.substring(startIdx, endIdx).trim()
        tools.push({ name, args: argsRaw, streaming: !eItem })
      }

      // 生成工具预览数据
      const previewData = tools.map(t => {
        let formattedArgs = t.args
        try {
          const parsed = JSON.parse(formattedArgs)
          formattedArgs = JSON.stringify(parsed, null, 2)
        } catch {}
        return {
          name: t.name,
          arguments: formattedArgs,
          streaming: t.streaming
        }
      })

      const toolCount = tools.length
      const isLoading = tools.some(t => t.streaming)

      const tagContent = JSON.stringify({
        tools: previewData,
        count: toolCount,
        loading: isLoading
      })

      // 注意：标签名使用 toolpreview（不带下划线）
      const key = `<toolpreview>${escapeHtml(tagContent)}</toolpreview>`
      processedText = processedText.substring(0, firstStart) + key + processedText.substring(previewRegionEnd)
    }
  }

  // 4. 处理工具调用块 → 转换为 <toolcalls> 自定义标签（注意：标签名不能包含下划线）
  processedText = processedText.replace(
    /<!--tool_calls:start-->([\s\S]*?)<!--tool_calls:end-->/g,
    (_, inner) => {
      const tools: Array<{ name: string; arguments: any; result?: any }> = []

      // 用一个正则同时匹配 tool_call 和 tool_result，按出现顺序处理
      const tokenRegex = /<!--tool_call:([\s\S]*?)-->|<!--tool_result:(.*?)-->/g
      let match
      let currentTool: any = null

      while ((match = tokenRegex.exec(inner)) !== null) {
        if (match[1] !== undefined) {
          // 匹配到 tool_call
          const b64Str = match[1].trim()
          try {
            const decodedJson = decodeURIComponent(escape(window.atob(b64Str)))
            const tool = JSON.parse(decodedJson)
            currentTool = {
              name: tool.name || '未知工具',
              arguments: tool.arguments || {},
              result: undefined
            }
            tools.push(currentTool)
          } catch {
            currentTool = {
              name: '工具参数解析失败',
              arguments: b64Str,
              result: undefined
            }
            tools.push(currentTool)
          }
        } else if (match[2] !== undefined) {
          // 匹配到 tool_result
          const jsonStr = match[2].trim()
          try {
            const res = JSON.parse(jsonStr)
            if (currentTool) {
              currentTool.result = res.result
            }
          } catch {
            if (currentTool) {
              currentTool.result = jsonStr
            }
          }
        }
      }

      // 注意：标签名使用 toolcalls（不带下划线）
      const tagContent = JSON.stringify(tools)
      return `<toolcalls>${escapeHtml(tagContent)}</toolcalls>`
    }
  )

  // 5. 处理 Token 用量 → 转换为 <tokenusage> 自定义标签（注意：标签名不能包含下划线）
  processedText = processedText.replace(
    /<!--token_usage:(.*?)-->/g,
    (_, jsonStr) => {
      try {
        const data = JSON.parse(jsonStr)
        const tagContent = JSON.stringify({
          speed: data.speed || '0 token/s',
          completion_tokens: data.final_answer_usage?.completion_tokens ?? 0
        })
        return `<tokenusage>${escapeHtml(tagContent)}</tokenusage>`
      } catch {
        return ''
      }
    }
  )
  // 清理多余换行
  processedText = processedText.replace(/\n{3,}/g, '\n\n')
  return processedText.trim()
}

/** 将图片引用转为 base64 */
export async function urlToBase64(url: string): Promise<string> {
  const response = await fetch(url)
  const blob = await response.blob()
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onloadend = () => resolve(reader.result as string)
    reader.onerror = reject
    reader.readAsDataURL(blob)
  })
}

/** 统一 file_ref 为数组 */
export function normalizeFileRef(ref: any): UploadedFile[] {
  if (!ref) return []
  return Array.isArray(ref) ? ref : [ref]
}

/**
 * 将包含文件引用的消息列表转换为适合发送给模型的消息格式
 * - 图片文件：转换为 base64 并嵌入多模态 content 数组
 * - 非图片文件：在消息文本末尾附加工具调用提示
 */
export async function cleanMessages(msgs: Message[]): Promise<{ role: string; content: string | any[] }[]> {
  const promises = msgs.map(async (msg) => {
    const fileRefs = normalizeFileRef(msg.file_ref)

    // 分离图片和非图片文件
    const imageFiles = fileRefs.filter(f => f.type?.startsWith('image/'))
    const nonImageFiles = fileRefs.filter(f => !f.type?.startsWith('image/'))

    // 如果没有文件，直接返回原内容
    if (imageFiles.length === 0 && nonImageFiles.length === 0) {
      return { role: msg.role, content: msg.content }
    }

    // 获取本地 IP 地址
    const urlhost = window.location.host.replace(/\b(?:localhost|\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b/g, localIP.value)

    // --- 处理图片：构建多模态 content ---
    let contentForModel: string | any[]
    if (imageFiles.length > 0) {
      const contentArray: any[] = []

      // 1. 图片转 base64 并嵌入
      for (const img of imageFiles) {
        const base64 = await urlToBase64(img.url)
        contentArray.push({
          type: 'image_url',
          image_url: { url: base64 }
        })
      }

      // 2. 文本部分
      if (typeof msg.content === 'string' && msg.content.trim()) {
        contentArray.push({ type: 'text', text: msg.content.trim() })
      }

      // 3. 非图片文件提示（如果有）
      if (nonImageFiles.length > 0) {
        const fileTips = nonImageFiles.map(f => f.url.replace('/files/', '/data/')).join('\n')
        const mcp_fileTips = nonImageFiles.map(f => f.url.replace('/files/', `http://${urlhost}/files/`)).join('\n')
        contentArray.push({
          type: 'text',
          text: `\n\n 如果调用【系统内置工具】使用文件路径：\n ${fileTips} \n\n 否则使用url：${mcp_fileTips}`
        })
      }

      contentForModel = contentArray
    } else {
      // --- 纯文本 + 文档提示 ---
      let text = typeof msg.content === 'string' ? msg.content : ''
      if (nonImageFiles.length > 0) {
        const fileTips = nonImageFiles.map(f => f.url.replace('/files/', '/data/')).join('\n')
        const mcp_fileTips = nonImageFiles.map(f => f.url.replace('/files/', `http://${urlhost}/files/`)).join('\n')
        text += `\n\n 如果调用【系统内置工具】使用文件路径：\n ${fileTips} \n\n 否则使用url：${mcp_fileTips}`
      }
      contentForModel = text
    }

    return { role: msg.role, content: contentForModel }
  })

  return Promise.all(promises)
}