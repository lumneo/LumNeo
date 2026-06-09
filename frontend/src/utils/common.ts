/**
 * 判断一个路径是否代表本地文件
 * 支持：
 * - file:///C:/path/file.txt
 * - C:\path\file.txt 或 D:/path/file.txt
 * - /home/user/file.pdf (Linux/macOS 绝对路径)
 */
export function isLocalFilePath(path: string): boolean {
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