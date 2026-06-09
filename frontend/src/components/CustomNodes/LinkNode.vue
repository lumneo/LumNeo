<template>
  <a
    :href="finalHref"
    :class="['link-node', fileTypeClass]"
    target="_blank"
    :download="downloadName"
    @click="handleSmartClick"
  >
    <slot>{{ node.text }}</slot>
  </a>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useMessage } from 'naive-ui'
import { isLocalFilePath, isRunningInPyWebView } from '@/utils/common'


const props = defineProps<{
  node: {
    type: 'link'
    href?: string
    text?: string
    loading?: boolean
    alt?: string
  }
}>()

  const message = useMessage()

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

// 1. 计算最终的 href (处理 URI 解码)
const finalHref = computed(() => {
  let url = props.node.href
  if (!url) return ''

  if (url.includes('%')) {
    try {
      const decoded = decodeURIComponent(url)
      // 假设 isLocalFilePath 已在外部定义
      if (isLocalFilePath(decoded)) {
        url = decoded
      }
    } catch (e) {
      console.warn('URL Decode failed', e)
    }
  }
  return url
})

// 2. 计算文件类型对应的 Class
const fileTypeClass = computed(() => {
  const url = finalHref.value
  if (!url) return ''

  // 提取文件扩展名（忽略查询参数和哈希）
  let ext = url.split('?')[0].split('#')[0].split('.').pop()
  if (!ext) return ''
  
  ext = ext.toLowerCase()

  // 查找匹配的类型
  const matched = typeMap.find(item => item.extensions.includes(ext))
  return matched ? matched.class : 'file-unknown'
})

// 3. 计算下载文件名
const downloadName = computed(() => {
  // 优先使用传入的 text 属性，如果没有则尝试获取 slot 的纯文本
  if (props.node.text) return props.node.text.trim()
  return ''
})

// 4. 智能点击处理逻辑 (替代全局 document.body.addEventListener)
const handleSmartClick = async (e: MouseEvent) => {
  const url = finalHref.value
  if (!url || url.startsWith('javascript:') || url === '#') return

  // 假设 isRunningInPyWebView 已在外部定义
  if (isRunningInPyWebView()) {
    if (isLocalFilePath(url)) {
      e.preventDefault()
      // 调用 pywebview 打开本地文件（注意：路径可能需要解码）
      const decodedPath = decodeURI(url.replace(/^file:\/\//, ''))
      if (window.pywebview?.api?.open_with_default_app) {
         await window.pywebview.api.open_with_default_app(decodedPath)
      }
    } else if (url.startsWith('http://') || url.startsWith('https://') || url.startsWith('/files/generate/')) {
      e.preventDefault()
      // 调用 pywebview 下载文件
      const fullUrl = url.startsWith('/') ? window.location.origin + url : url
      const fileName = downloadName.value || 'download'
      if (window.pywebview?.api?.download_file) {
        await window.pywebview.api.download_file(fullUrl, fileName)
      }
    }
    // 其他协议（mailto, tel 等）保持默认行为，不阻止
  } else {
    // 浏览器环境
    if (isLocalFilePath(url)) {
      e.preventDefault()
      // 假设 message 组件可用
      message.warning('暂不支持浏览器中打开，请使用桌面端打开')
    }
  }
}
</script>

<style scoped>
.link-node {
  text-decoration: none;
}
.message-content .file-pdf::before {
  content: '';
  display: inline-block;
  width: 1.6em;
  height: 1.6em;
  background: url('/svg/pdf.svg') no-repeat center;
  background-size: contain;
  margin-right: 0.3em;
  vertical-align: middle;
}
.message-content .file-word::before {
  content: '';
  display: inline-block;
  width: 1.6em;
  height: 1.6em;
  background: url('/svg/word.svg') no-repeat center;
  background-size: contain;
  margin-right: 0.3em;
  vertical-align: middle;
}
.message-content .file-excel::before {
  content: '';
  display: inline-block;
  width: 1.6em;
  height: 1.6em;
  background: url('/svg/excel.svg') no-repeat center;
  background-size: contain;
  margin-right: 0.3em;
  vertical-align: middle;
}
.message-content .file-powerpoint::before {
  content: '';
  display: inline-block;
  width: 1.6em;
  height: 1.6em;
  background: url('/svg/ppt.svg') no-repeat center;
  background-size: contain;
  margin-right: 0.3em;
  vertical-align: middle;
}
.message-content .file-text::before {
  content: '';
  display: inline-block;
  width: 1.6em;
  height: 1.6em;
  background: url('/svg/text.svg') no-repeat center;
  background-size: contain;
  margin-right: 0.3em;
  vertical-align: middle;
}
.message-content .file-archive::before {
  content: '';
  display: inline-block;
  width: 1.6em;
  height: 1.6em;
  background: url('/svg/zip.svg') no-repeat center;
  background-size: contain;
  margin-right: 0.3em;
  vertical-align: middle;
}
.message-content .file-image::before {
  content: '';
  display: inline-block;
  width: 1.6em;
  height: 1.6em;
  background: url('/svg/image.svg') no-repeat center;
  background-size: contain;
  margin-right: 0.3em;
  vertical-align: middle;
}
.message-content a {
  display: inline-block;
  padding: 8px 12px;
  background: rgba(255, 255, 255, 0.18);
  color: #fff;
  border-radius: 4px;
  position: relative;
}
.message-content a:hover {
  background: rgba(100, 104, 230, 0.4);
}

[theme-mode="light"] .message-content a {
  background: rgba(0, 0, 0, 0.1);
  color: #000;
}

[theme-mode="light"] .message-content a:hover {
  background: rgba(0, 0, 0, 0.3);
}
</style>