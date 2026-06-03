// src/utils/message.ts
import { ref } from 'vue'
import { marked } from 'marked'
import mermaid from 'mermaid'
import { markedHighlight } from 'marked-highlight'
import { type Message } from '@/stores/chat'
import type { UploadedFile } from '@/composables/useFileUpload'
import hljs from 'highlight.js'
import markedKatex from 'marked-katex-extension'
import 'katex/dist/katex.min.css'
import 'highlight.js/styles/atom-one-dark.css'


// 初始化 mermaid
mermaid.initialize({
  startOnLoad: false,
  theme: 'dark',
  securityLevel: 'loose',
  themeVariables: {
    primaryColor: '#6366f1',
    primaryTextColor: '#e4e7ed',
    lineColor: '#8b5cf6',
  }
})

marked.use({
  extensions: [
      {
          name: 'no-single-tilde-strikethrough',
          level: 'inline',           // 规则作用范围为行内元素
          start(src) {
              // 查找单个波浪号的位置
              return src.match(/~[^~]/)?.index
          },
          tokenizer(src, _tokens) {
              // 匹配被单个波浪号包裹的内容（非贪婪模式）
              const match = src.match(/^~([^~]+)~/)
              if (match) {
                  // 若匹配成功，则返回一个普通的文本节点，保持原样
                  return {
                      type: 'text',
                      raw: match[0],
                      text: match[0],
                  }
              }
              return undefined; // 未匹配则返回 undefined，交由其他解析器处理
          },
      },
  ],
  tokenizer: {
    code() {
      return undefined // 拒绝识别空格缩进的代码块，直接跳过
    }
  }
})

marked.use(markedHighlight({
  langPrefix: 'hljs language-',
  highlight(code, lang) {
    if (lang === 'mermaid') return code
    const language = hljs.getLanguage(lang) ? lang : 'plaintext'
    return hljs.highlight(code, { language }).value
  }
}))

marked.use(markedKatex({
  throwOnError: false,       // 报错时显示原始公式而不是中断
  output: 'html',           // 使用 KaTeX 生成 HTML 而不是 MathML
  nonStandard: true,       // 允许使用非标准 KaTeX 命令
  strict: 'ignore'
}))

/** 转义 HTML 特殊字符，防止被浏览器渲染 */
function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}

export const localIP = ref('')


/** 解析思考块和工具调用 */
export function processMessageContent(text: string, isStreaming = false): string {
  if (!text) return ''
  
  // 使用 Map 存储占位符到 HTML 的映射
  const blockMap = new Map<string, string>()
  let processedText = text

  // 1. 处理完整的思考块
  processedText = processedText.replace(
    /<!--reasoning:start-->([\s\S]*?)<!--reasoning:end:(.*?)-->/g,
    (_, content, time) => {
      const key = `<!--BLOCK_0${blockMap.size}-->` // 使用 HTML 注释占位符
      const timeStr = time ? ` (${time}秒)` : ''
      const html = `<div class="reasoning-block"><div class="reasoning-summary no-select">💭 已思考 ${timeStr}</div><div class="reasoning-content"><div class="reasoning-inner">${marked.parse(content)}</div></div></div>`
      blockMap.set(key, html)
      return key
    }
  )

  // 2. 处理流式未闭合的思考块
  if (isStreaming) {
    const startIdx = processedText.indexOf('<!--reasoning:start-->');
    if (startIdx !== -1 && !processedText.includes('<!--reasoning:end:-->')) {
      const afterStart = processedText.substring(startIdx + '<!--reasoning:start-->'.length)
      const key = `<!--BLOCK_${blockMap.size}-->`
      const html = `<div class="reasoning-block" data-reasoning="open"><div class="reasoning-summary no-select">💭 思考中...</div><div class="reasoning-content"><div class="reasoning-inner">${marked.parse(afterStart)}</div></div></div>`
      // 移除原始标记，只保留占位符
      processedText = processedText.substring(0, startIdx) + key
      blockMap.set(key, html)
    }
  }

  // 如果已经出现最终的工具调用块，则清除所有工具预览标记，避免同时显示两个块
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

  // 仅在还没有最终工具调用块时，才渲染工具预览
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
      const cards: Array<{ name: string; args: string; streaming: boolean }> = []
      for (const idx of idxSet) {
        const sItem = startPositions.find(s => s.idx === idx)
        const eItem = endPositions.find(e => e.idx === idx)
        const name = sItem?.name || ''
        const startIdx = sItem?.pos ?? 0
        const endIdx = eItem?.pos ?? previewRegion.length
        const argsRaw = previewRegion.substring(startIdx, endIdx).trim()
        cards.push({ name, args: argsRaw, streaming: !eItem })
      }

      // 生成卡片 HTML
      let cardsHtml = ''
      for (const card of cards) {
        let formattedArgs = card.args
        try {
          const parsed = JSON.parse(formattedArgs)
          formattedArgs = JSON.stringify(parsed, null, 2)
        } catch {}
        cardsHtml += `<div class="tool-call-card streaming">
          <span class="tool-name">🛠 ${escapeHtml(card.name)}</span>
          <pre class="tool-args"><code>${escapeHtml(formattedArgs)}</code></pre>
        </div>`
      }

      const toolCount = cards.length
      const title = toolCount > 0 ? `🔧 工具调用中… (${toolCount}个)` : '🔧 工具调用中…'
      const blockHtml = `<div class="tool-calls-block" data-tool="open">
        <div class="tool-summary no-select">${title}</div>
        <div class="tool-calls-container">
          <div class="tool-inner">${cardsHtml}</div>
        </div>
      </div>`

      const key = `<!--BLOCK_${blockMap.size}-->`
      processedText = processedText.substring(0, firstStart) + key + processedText.substring(previewRegionEnd)
      blockMap.set(key, blockHtml)
    }
  }

  // 3. 处理工具调用块（顺序保留）
  processedText = processedText.replace(
    /<!--tool_calls:start-->([\s\S]*?)<!--tool_calls:end-->/g,
    (_, inner) => {
      let cardsHtml = ''

      // 用一个正则同时匹配 tool_call 和 tool_result，按出现顺序处理
      const tokenRegex = /<!--tool_call:([\s\S]*?)-->|<!--tool_result:(.*?)-->/g
      let match
      while ((match = tokenRegex.exec(inner)) !== null) {
        if (match[1] !== undefined) {
          // 匹配到 tool_call
          const b64Str = match[1].trim()
          try {
            const decodedJson = decodeURIComponent(escape(window.atob(b64Str)))
            const tool = JSON.parse(decodedJson)
            let formatted = tool.arguments
            // ... 格式化参数（保持你原来的逻辑）
            if (typeof formatted === 'string') {
              try {
                const parsed = JSON.parse(formatted)
                formatted = JSON.stringify(parsed, null, 2)
              } catch { /* 原样 */ }
            } else if (typeof formatted === 'object') {
              formatted = JSON.stringify(formatted, null, 2)
            } else {
              formatted = String(formatted)
            }
            cardsHtml += `<div class="tool-call-card"><span class="tool-name">🛠 ${escapeHtml(tool.name || '未知工具')}</span><pre class="tool-args"><code>${escapeHtml(formatted)}</code></pre></div>`
          } catch {
            cardsHtml += `<div class="tool-call-card"><span class="tool-name">🛠 工具参数解析失败</span><pre class="tool-args"><code>${escapeHtml(b64Str)}</code></pre></div>`
          }
        } else if (match[2] !== undefined) {
          // 匹配到 tool_result
          const jsonStr = match[2].trim()
          try {
            const res = JSON.parse(jsonStr)
            let formatted = res.result
            // ... 格式化结果（保持原逻辑）
            if (typeof formatted === 'string') {
              try {
                const parsed = JSON.parse(formatted)
                formatted = JSON.stringify(parsed, null, 2)
              } catch { /* 原样 */ }
            } else if (typeof formatted === 'object') {
              formatted = JSON.stringify(formatted, null, 2)
            } else {
              formatted = String(formatted)
            }
            cardsHtml += `<div class="tool-result"><span class="result-label">📑 结果：</span><pre class="result-content"><code>${escapeHtml(formatted)}</code></pre></div>`
          } catch {
            cardsHtml += `<div class="tool-result"><span class="result-label">📑 结果解析失败：</span><pre class="result-content"><code>${escapeHtml(jsonStr)}</code></pre></div>`
          }
        }
      }

      const toolCount = (cardsHtml.match(/tool-call-card/g) || []).length
      const title = toolCount > 0 ? `🔧 工具调用 (${toolCount}个)` : '🔧 工具调用'

      const html = `<div class="tool-calls-block"><div class="tool-summary no-select">${title}</div><div class="tool-calls-container"><div class="tool-inner">${cardsHtml}</div></div></div>`
      const key = `<!--BLOCK_${blockMap.size}-->`
      blockMap.set(key, html)
      return key
    }
  )

  // 4. 处理 Token 用量
  const hasToolCalls = /<!--tool_call:|<!--tool_calls:start-->/.test(processedText)
  if (!hasToolCalls) {
    processedText = processedText.replace(
      /<!--token_usage:(.*?)-->/g,
      (_, jsonStr) => {
        try {
          const data = JSON.parse(jsonStr)
          const speed = data.speed || '0 token/s'
          const completionTokens = data.final_answer_usage?.completion_tokens ?? 0
          // const totalTokens = data.total_usage_all_steps?.total_tokens ?? 0

          let html = `<div class="token-usage"><span title="生成速度">🚀 ${speed}</span><span title="本次回答消耗"> 📈 ${completionTokens} token</span>`

          html += `</div>`
          const key = `<!--BLOCK_${blockMap.size}-->`
          blockMap.set(key, html)
          return key
        } catch {
          return ''
        }
      }
    )
  } else {
    // 有工具调用的场景：你也可以选择显示 token 统计，例如在工具调用结果之后展示
    // 这里保留原逻辑，直接移除 token_usage 注释
    processedText = processedText.replace(/<!--token_usage:.*?-->/g, '')
  }

  processedText = processedText.replace(/(\*\*.*?\*\*)/g, ' $1 ')
  processedText = processedText.replace(/^(\s*[*\-+]) {4}/gm, '$1   ')

  // 5. 用 marked 渲染剩余纯文本
  let finalHtml: any = marked.parse(processedText.trim())

  // 6. 将占位符替换为实际 HTML
  blockMap.forEach((html, key) => {
    finalHtml = finalHtml.replace(key, html)
  })

  return finalHtml
}

export function renderMessageHtml(text: string, isStreaming = false) {
  return processMessageContent(text, isStreaming)
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
    const fileRefs = normalizeFileRef(msg.file_ref) // file_ref 现在是数组

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