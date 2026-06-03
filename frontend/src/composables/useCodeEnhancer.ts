import { ref, nextTick, type Ref } from 'vue'
import mermaid from 'mermaid'
import { useMessage } from 'naive-ui'

export function useCodeEnhancer(containerRef: Ref<HTMLElement | null>) {
  const message = useMessage()

  let observer: MutationObserver | null = null
  const isStreaming = ref(false)

  const copyIcon =
      '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M6.14929 4.02032C7.11197 4.02032 7.87983 4.02016 8.49597 4.07598C9.12128 4.13269 9.65792 4.25188 10.1415 4.53106C10.7202 4.8653 11.2008 5.3459 11.535 5.92462C11.8142 6.40818 11.9334 6.94481 11.9901 7.57012C12.0459 8.18625 12.0458 8.95419 12.0458 9.9168C12.0458 10.8795 12.0459 11.6473 11.9901 12.2635C11.9334 12.8888 11.8142 13.4254 11.535 13.909C11.2008 14.4877 10.7202 14.9683 10.1415 15.3025C9.65792 15.5817 9.12128 15.7009 8.49597 15.7576C7.87984 15.8134 7.11196 15.8133 6.14929 15.8133C5.18667 15.8133 4.41874 15.8134 3.80261 15.7576C3.1773 15.7009 2.64067 15.5817 2.1571 15.3025C1.5784 14.9683 1.09778 14.4877 0.76355 13.909C0.484366 13.4254 0.365184 12.8888 0.308472 12.2635C0.252649 11.6473 0.252808 10.8795 0.252808 9.9168C0.252808 8.95418 0.252664 8.18625 0.308472 7.57012C0.365184 6.94481 0.484366 6.40818 0.76355 5.92462C1.09777 5.34589 1.57839 4.86529 2.1571 4.53106C2.64067 4.25188 3.1773 4.13269 3.80261 4.07598C4.41874 4.02017 5.18666 4.02032 6.14929 4.02032ZM6.14929 5.37774C5.16181 5.37774 4.46634 5.37761 3.92566 5.42657C3.39434 5.47472 3.07859 5.56574 2.83582 5.70587C2.4632 5.92106 2.15354 6.2307 1.93835 6.60333C1.79823 6.8461 1.70721 7.16185 1.65906 7.69317C1.6101 8.23385 1.61023 8.92933 1.61023 9.9168C1.61023 10.9043 1.61009 11.5998 1.65906 12.1404C1.70721 12.6717 1.79823 12.9875 1.93835 13.2303C2.15356 13.6029 2.46321 13.9126 2.83582 14.1277C3.07859 14.2679 3.39434 14.3589 3.92566 14.407C4.46634 14.456 5.16182 14.4559 6.14929 14.4559C7.13682 14.4559 7.83224 14.456 8.37292 14.407C8.90425 14.3589 9.21999 14.2679 9.46277 14.1277C9.83535 13.9126 10.145 13.6029 10.3602 13.2303C10.5004 12.9875 10.5914 12.6717 10.6395 12.1404C10.6885 11.5998 10.6884 10.9043 10.6884 9.9168C10.6884 8.92934 10.6885 8.23384 10.6395 7.69317C10.5914 7.16185 10.5004 6.8461 10.3602 6.60333C10.1451 6.23071 9.83536 5.92107 9.46277 5.70587C9.21999 5.56574 8.90424 5.47472 8.37292 5.42657C7.83224 5.3776 7.13682 5.37774 6.14929 5.37774ZM9.80164 0.367975C10.7638 0.367975 11.5314 0.36788 12.1473 0.423639C12.7726 0.480307 13.3093 0.598759 13.7928 0.877741C14.3717 1.21192 14.8521 1.69355 15.1864 2.27227C15.4655 2.75574 15.5857 3.29164 15.6425 3.9168C15.6983 4.53301 15.6971 5.3016 15.6971 6.26446V7.82989C15.6971 8.29264 15.6989 8.58993 15.6649 8.84844C15.4668 10.3525 14.401 11.5738 12.9833 11.9988V10.5467C13.6973 10.1903 14.2105 9.49662 14.3192 8.67169C14.3387 8.52347 14.3407 8.3358 14.3407 7.82989V6.26446C14.3407 5.27706 14.3398 4.58149 14.2909 4.04083C14.2428 3.50968 14.1526 3.19372 14.0126 2.95098C13.7974 2.57849 13.4876 2.26869 13.1151 2.05352C12.8724 1.91347 12.5564 1.82237 12.0253 1.77423C11.4847 1.72528 10.7888 1.7254 9.80164 1.7254H7.71472C6.7562 1.72558 5.92665 2.27697 5.52332 3.07891H4.07019C4.54221 1.51132 5.9932 0.368186 7.71472 0.367975H9.80164Z" fill="currentColor"></path></svg>'
  const succIcon =
      '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M15.0498 3.92579L8.49512 12.3818C8.25774 12.6881 8.04517 12.9645 7.84668 13.1689C7.63957 13.3823 7.38732 13.5841 7.04492 13.6719C6.86373 13.7183 6.6757 13.7346 6.48926 13.7197C6.13666 13.6915 5.8528 13.5355 5.6123 13.3604C5.38201 13.1926 5.12573 12.9567 4.83984 12.6953L1.03125 9.21289L1.96875 8.1875L5.77734 11.6699C6.08684 11.9529 6.27773 12.1249 6.43066 12.2363C6.50183 12.2882 6.54699 12.3135 6.57324 12.3252C6.58525 12.3305 6.59269 12.3322 6.5957 12.333C6.59802 12.3336 6.59961 12.334 6.59961 12.334C6.63317 12.3367 6.66758 12.3335 6.7002 12.3252C6.7002 12.3252 6.70211 12.3251 6.7041 12.3242C6.70698 12.3229 6.71348 12.319 6.72461 12.3115C6.74849 12.2956 6.78843 12.2642 6.84961 12.2012C6.98138 12.0654 7.13957 11.8628 7.39648 11.5313L13.9502 3.07422L15.0498 3.92579Z" fill="currentColor"></path></svg>'


  /**
   * 为所有匹配的 a 标签根据文件类型添加 class
   * @param {string|HTMLElement} container - 容器元素或选择器，例如 '#content' 或 document.body
   * @param {boolean} recursive - 是否递归查找后代元素，默认 true
   */
  async function addFileTypeClassToLinks(container: string|HTMLElement, recursive: boolean = true) {
    // 获取容器元素  
    const root = typeof container === 'string' 
      ? document.querySelector(container) 
      : container
      
    if (!root) return

    // 获取容器内的所有 a 标签
    const links: any = recursive 
      ? root.querySelectorAll('a') 
      : root.children

    // 文件类型映射表
    const typeMap = [
      { extensions: ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg'], class: 'file-image' },
      { extensions: ['pdf'], class: 'file-pdf' },
      { extensions: ['doc', 'docx'], class: 'file-word' },
      { extensions: ['xls', 'xlsx'], class: 'file-excel' },
      { extensions: ['ppt', 'pptx'], class: 'file-powerpoint' },
      { extensions: ['txt', 'md', 'rtf'], class: 'file-text' },
      { extensions: ['zip', 'rar', '7z', 'tar', 'gz'], class: 'file-archive' },
      { extensions: ['mp3', 'wav', 'flac', 'aac'], class: 'file-audio' },
      { extensions: ['mp4', 'webm', 'avi', 'mov', 'mkv'], class: 'file-video' },
    ]

    links.forEach((link: HTMLElement) => {
      const href = link.getAttribute('href')
      
      if (!href) return

      // 提取文件扩展名（忽略查询参数和哈希）
      let ext = href.split('?')[0].split('#')[0].split('.').pop()
      if (!ext) return
      ext = ext.toLowerCase()

      // 查找匹配的类型
      const matched = typeMap.find(item => item.extensions.includes(ext))
      if (matched) {
        link.classList.add(matched.class)
      } else {
        // 可选：未知类型添加通用 class
        link.classList.add('file-unknown')
      }
      link.setAttribute('target', '_blank')
      link.setAttribute('download', link.textContent?.trim() || '')
    })
  }
  /**
   * 为所有代码块添加复制按钮
   */
  async function addCopyButtons() {
    if (isStreaming.value) return
    await nextTick()
    if (!containerRef.value) return
    
    const pres = containerRef.value.querySelectorAll('pre:not([data-copy-added])')
    
    pres.forEach((pre) => {
      pre.setAttribute('data-copy-added', 'true')
      const btn = document.createElement('button')
      btn.className = 'copy-code-btn'
      btn.innerHTML = `${copyIcon}复制`
      btn.title = '复制代码'
      btn.addEventListener('click', async () => {
        const code = pre.querySelector('code')?.textContent || ''
        let copySuccess = false

        // 1. 优先使用现代 Clipboard API（需安全上下文 + 用户手势）
        if (navigator.clipboard && window.isSecureContext) {
          try {
            await navigator.clipboard.writeText(code)
            copySuccess = true
          } catch (err) {
            console.warn('Clipboard API 失败:', err)
          }
        }

        // 2. 降级：execCommand（兼容移动端微信/QQ/旧浏览器）
        if (!copySuccess) {
          const textarea = document.createElement('textarea')
          textarea.value = code
          // 移出可视区域，避免页面跳动
          textarea.style.position = 'fixed'
          textarea.style.top = '-9999px'
          textarea.style.left = '-9999px'
          textarea.style.opacity = '0'
          document.body.appendChild(textarea)
          textarea.select()
          textarea.setSelectionRange(0, 99999) // 移动端必须
          try {
            copySuccess = document.execCommand('copy')
          } catch (err) {
            console.warn('execCommand 复制失败:', err)
          }
          document.body.removeChild(textarea)
        }

        // 3. 最终反馈
        if (copySuccess) {
          btn.innerHTML = `${succIcon}复制`
          setTimeout(() => {
            btn.innerHTML = `${copyIcon}复制`
          }, 2000);
        } else {
          // 原代码中的 message.error（假设你用的是 antd-message 或类似）
          message.error('复制失败，请手动复制')
        }
      })

      // 包裹 pre 以便按钮定位
      if (!pre.parentElement?.classList.contains('code-block-wrapper')) {
        const wrapper = document.createElement('div')
        wrapper.className = 'code-block-wrapper'
        pre.parentNode?.insertBefore(wrapper, pre)
        wrapper.appendChild(pre)
      }
      pre.parentElement!.appendChild(btn)
    })
  }

  function setStreaming(status: boolean) {
    isStreaming.value = status
  }

  // 启动自动观察
  function startObserving() {
    if (!containerRef.value) return
    // 立即添加一次已有代码块
    addCopyButtons()
    // 监听新节点
    observer = new MutationObserver(() => {
      addCopyButtons()
      renderMermaidDiagrams()
      addFileTypeClassToLinks(containerRef.value!)
    })
    observer.observe(containerRef.value, {
      childList: true,
      subtree: true,
    })
  }

  // 停止观察
  function stopObserving() {
    observer?.disconnect()
    observer = null
  }

  /**
   * 渲染页面中的 Mermaid 图表
   */
  async function renderMermaidDiagrams() {
    await nextTick()
    if (!containerRef.value) return

    const mermaidCodes = containerRef.value.querySelectorAll(
      'pre code.language-mermaid'
    )
    for (const codeEl of mermaidCodes) {
      const preEl = codeEl.parentElement!
      if (preEl.dataset.mermaidRendered) continue

      const code = codeEl.textContent || ''
      if (!code.trim()) continue

      try {
        const { svg } = await mermaid.render(
          'mermaid-' + Math.random().toString(36).substr(2, 9),
          code
        )
        const div = document.createElement('div')
        div.className = 'mermaid-rendered'
        div.innerHTML = svg
        preEl.replaceWith(div)
        preEl.dataset.mermaidRendered = 'true'
      } catch (e) {
        console.warn('Mermaid 渲染失败', e)
      }
    }
  }

  return {
    containerRef,
    addCopyButtons,
    addFileTypeClassToLinks,
    renderMermaidDiagrams,
    startObserving,
    stopObserving,
    setStreaming
  }
}