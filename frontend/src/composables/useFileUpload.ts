import { ref, computed } from 'vue'
import type { UploadFileInfo } from 'naive-ui'
import { useMessage } from 'naive-ui'
import { fileConfig } from '@/stores/config'

export interface UploadedFile {
  filename: string
  type: string
  url: string
  path?: string
}

export function useFileUpload() {
  const message = useMessage()
  const uploadedFiles = ref<UploadedFile[]>([])
  const uploadFileList = ref<UploadFileInfo[]>([])

  // 记录已处理的文件（文件名 + 大小）
  const processedFiles = new Set<string>()

  function getFileKey(file: File): string {
    return `${file.name}__${file.size}`
  }

  async function uploadFiles(files: File[]) {
    // 过滤掉已处理的文件
    const newFiles = files.filter(f => {
      const key = getFileKey(f)
      if (processedFiles.has(key)) return false
      processedFiles.add(key)
      return true
    })

    for (const file of newFiles) {
      const formData = new FormData()
      formData.append('file', file)
      try {
        const res = await fetch('/api/files/upload', {
          method: 'POST',
          body: formData,
        })
        const data = await res.json()
        uploadedFiles.value.push({
          filename: data.filename,
          type: data.type,
          url: data.url,
          path: data.path,
        })
      } catch (e) {
        console.error('上传失败', e)
      }
    }
  }

  function clearFiles() {
    uploadedFiles.value = []   // 清空源数据
    uploadFileList.value = []
  }

  function removeFile(index: number) {
    const removed = uploadedFiles.value[index]
  
    // 清理去重 Set（需要根据 filename 匹配）
    if (removed) {
      for (const key of processedFiles) {
        // key 格式是 "filename__size"，匹配 filename 部分
        if (key.startsWith(removed.filename)) {
          processedFiles.delete(key)
          break
        }
      }
    }

    // 从自定义列表中删除
    uploadedFiles.value.splice(index, 1)

    // 同步删除 n-upload 内部列表中对应的条目
    const matchIndex = uploadFileList.value.findIndex(
      (f: UploadFileInfo) => f.name === removed?.filename
    )
    if (matchIndex !== -1) {
      uploadFileList.value.splice(matchIndex, 1)
    }
  }

  function hasFilesInDrag(e: DragEvent): boolean {
    return !!e.dataTransfer?.types && Array.from(e.dataTransfer.types).includes('Files')
  }

  // 拖拽上传
  const dragCounter = ref(0)
  const isDragging = computed(() => dragCounter.value > 0)

  function onDragEnter(e: DragEvent) {
    e.preventDefault()
    e.stopPropagation()
    if (hasFilesInDrag(e)) {
      dragCounter.value++
    }
  }

  function onDragOver(e: DragEvent) {
    e.preventDefault()
    e.stopPropagation()
  }

  function onDragLeave(e: DragEvent) {
    e.preventDefault()
    e.stopPropagation()
    if (hasFilesInDrag(e)) {
      dragCounter.value--
    }
  }

  async function onDrop(e: DragEvent, id: string|null) {
    if (!id) {
      dragCounter.value = 0
      return
    }
    e.preventDefault()
    e.stopPropagation()
    dragCounter.value = 0
    const files = e.dataTransfer?.files
    if (!files?.length) return

    // 数量限制
    const currentCount = uploadedFiles.value.length
    if (currentCount >= fileConfig.max) {
      message.error(`最多只能上传 ${fileConfig.max} 个文件`)
      return
    }
    const remaining = fileConfig.max - currentCount

    // 过滤类型和大小，并截取不超过 remaining 的文件
    const validList: File[] = []
    for (let i = 0; i < files.length && validList.length < remaining; i++) {
      const file = files[i]
      if (validateFile(file)) {
        validList.push(file)
      }
    }

    if (validList.length === 0) return
    await uploadFiles(validList)
  }

  function validateFile(file: File): boolean {
    const suffix = file.name.substr(file.name.lastIndexOf('.'))
    if (fileConfig.accept.split(',').indexOf(suffix) === -1) {
      message.error(`该文件 ${file.name} 不支持哦~`)
      return false
    }
    if (file.size / 1024 / 1024 > fileConfig.size) {
      message.error(`文件 ${file.name} 超过限制大小 (${fileConfig.size}MB)`)
      return false
    }
    return true
  }

  function onBeforeUpload({ file }: any) {
    if (!file.name || file.name === '/') {
      message.error('选择需要上传的文件！')
      return false
    }
    if (uploadedFiles.value.length >= fileConfig.max) {
      message.error(`最多只能上传 ${fileConfig.max} 个文件`)
      return false
    }
    return validateFile(file.file)
  }

  async function handleFileUpload(options: { fileList: UploadFileInfo[] }) {
    // 直接从 fileList 提取 File 对象，不再依赖 status
    const files: File[] = []
    for (const item of options.fileList) {
      const file = (item as any).file as File
      if (file) {
        files.push(file)
      }
    }
    if (files.length === 0) return

    // uploadFiles 内部会根据 Set 去重，所以即使 change 触发了多次，也不会重复上传
    await uploadFiles(files)
  }

  return {
    uploadFileList,
    uploadedFiles,
    isDragging,
    onDragEnter,
    onDragOver,
    onDragLeave,
    onDrop,
    onBeforeUpload,
    handleFileUpload,
    removeFile,
    clearFiles,
  }
}