import { ref, type Ref } from 'vue'
import { useMessage } from 'naive-ui'


/**
 * 判断一个路径是否代表本地文件
 * 支持：
 * - file:///C:/path/file.txt
 * - C:\path\file.txt 或 D:/path/file.txt
 * - /home/user/file.pdf (Linux/macOS 绝对路径)
 */
function isLocalFilePath(path: string): boolean {
  if (path.startsWith('file://')) return true
  if (/^[a-zA-Z]:[\\/]/.test(path)) return true // Windows 盘符
  return false
}


export function isRunningInPyWebView(): boolean {
  // 优先检查 pywebview 对象（最准确）
  if (typeof window !== 'undefined' && (window as any).pywebview) {
    return true
  }
  // 后备检查 UA（某些旧版本可能没有 pywebview 全局对象）
  return /pywebview/i.test(navigator.userAgent)
}

export function useCodeEnhancer(containerRef: Ref<HTMLElement | null>) {
  const message = useMessage()

  let observer: MutationObserver | null = null
  const isStreaming = ref(false)
  let smartClickBound = false // 全局标志，确保只绑定一次事件监听

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
      if (link.dataset.enhanced === 'true') return
      link.dataset.enhanced = 'true'
      let href = link.getAttribute('href')
      if (!href) return

      if (href.includes('%')) {
        try {
          const decoded = decodeURIComponent(href)          
          if (isLocalFilePath(decoded)) {
            href = decodeURIComponent(href)
            if (link.getAttribute('href') !== href) {
              link.setAttribute('href', href)
            }
          }
        } catch (e) {}
      }
      

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
      if (!smartClickBound) {
        document.body.addEventListener('click', async (e) => {
          const link = (e.target as HTMLElement).closest('a')
          if (!link) return

          const href = link.getAttribute('href')
          if (!href || href.startsWith('javascript:') || href === '#') return
          
          if (isRunningInPyWebView()) {
            if (isLocalFilePath(href)) {
              e.preventDefault()
              // 调用 pywebview 打开本地文件（注意：路径可能需要解码）
              const decodedPath = decodeURI(href.replace(/^file:\/\//, ''))
              await window.pywebview.api.open_with_default_app(decodedPath)
            } else if (href.startsWith('http://') || href.startsWith('https://') || href.startsWith('/files/generate/')) {
              e.preventDefault()
              // 调用 pywebview 下载文件
              const fullUrl = href.startsWith('/') ? window.location.origin + href : href            
              await window.pywebview.api.download_file(fullUrl, link.textContent?.trim() || '')
            }
            // 其他协议（mailto, tel 等）保持默认行为
          } else {
            if (isLocalFilePath(href)) {
              e.preventDefault()
              message.warning('暂不支持浏览器中打开，请使用桌面端打开')
            }
          }
        })
        smartClickBound = true
      }
    })
  }

  function setStreaming(status: boolean) {
    isStreaming.value = status
  }

  // 启动自动观察
  function startObserving() {
    if (!containerRef.value) return
    // 监听新节点
    observer = new MutationObserver(async () => {
      if (isStreaming.value) return
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

  return {
    containerRef,
    addFileTypeClassToLinks,
    startObserving,
    stopObserving,
    setStreaming
  }
}