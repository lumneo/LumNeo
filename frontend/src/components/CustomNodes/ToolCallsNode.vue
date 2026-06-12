<template>
  <div class="toolcalls-block" :data-tool="props.node.loading ? 'open' : undefined">
    <div class="toolcalls-summary no-select" @click="toggle">
      {{ title }}
    </div>
    <div class="toolcalls-container">
      <div class="toolcalls-inner">
        <div class="toolcalls-content">
          <div 
            v-for="(tool, index) in tools" 
            :key="index"
            class="toolcall-card"
            :class="{ 'streaming': tool.status === 'calling' }"
          >
            <span class="tool-name">{{ tool.name }}</span>
            <div class="code-block-wrapper">
              <n-button class="copy-code-btn" size="small" @click="handleCopy(formatArgs(tool.arguments))">
                <template #icon>
                  <m-svg :name="copySuccess ? 'succ' : 'copy'"/>
                </template>
                复制
              </n-button>
              <pre class="tool-args"><code>{{ formatArgs(tool.arguments) }}</code></pre>
            </div>

            <div v-if="tool.result !== undefined" class="tool-result">
              <span class="result-label">结果：</span>
              <div class="code-block-wrapper">
                <n-button class="copy-code-btn" size="small" @click="handleCopy(formatResult(tool.result))">
                  <template #icon>
                    <m-svg :name="copySuccess ? 'succ' : 'copy'"/>
                  </template>
                  复制
                </n-button>
                <pre class="result-content"><code>{{ formatResult(tool.result) }}</code></pre>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { NButton } from 'naive-ui'
import MSvg from '@/components/MSvg.vue'
import { copyToClipboard } from '@/utils/common'

const props = defineProps<{
  node: {
    type: 'toolcalls'
    content?: string
    loading?: boolean
    autoClosed?: boolean
    attrs?: Record<string, any>
  }
  customId?: string
  isDark?: boolean
}>()

interface ToolCall {
  name: string
  arguments: string | object
  result?: any
  status: 'calling' | 'done' | 'error'
}

const copySuccess = ref(false)

const tools = computed<ToolCall[]>(() => {
  try {
    const content = props.node.content || '[]'    
    const parsed = JSON.parse(content)
    if (Array.isArray(parsed)) {
      return parsed.map(t => ({
        name: t.name || '未知工具',
        arguments: t.arguments || t.args || '{}',
        result: t.result,
        status: t.result ? 'done' : (props.node.loading ? 'calling' : 'done')
      }))
    }
    return []
  } catch(e) {
    console.error('Failed to parse tool calls:', e)
    return []
  }
})

function formatArgs(args: string | object): string {
  if (typeof args === 'string') {
    try {
      const parsed = JSON.parse(args)
      return JSON.stringify(parsed, null, 2)
    } catch {
      return args
    }
  }
  return JSON.stringify(args, null, 2)
}

function formatResult(result: any): string {
  if (typeof result === 'string') {
    try {
      const parsed = JSON.parse(result)
      return JSON.stringify(parsed, null, 2)
    } catch {
      return result
    }
  }
  return JSON.stringify(result, null, 2)
}

function handleCopy(content: string) {
  copyToClipboard(content)
  copySuccess.value = true
  setTimeout(() => {
    copySuccess.value = false
  }, 800)
}

function toggle(e: MouseEvent) {
  const target = e.target as HTMLElement
  const block = target.closest('.toolcalls-block') as HTMLElement | null
  if (!block) return

  const isCurrentlyOpen = block.dataset.tool === 'open'
  if (isCurrentlyOpen) {
    block.removeAttribute('data-tool')
  } else {
    block.setAttribute('data-tool', 'open')
  }
}

const title = computed(() => {
  const count = tools.value.length
  if (props.node.loading) {
    return count > 0 ? `工具调用中… (${count}个)` : '工具调用中…'
  }
  return count > 0 ? `工具调用 (${count}个)` : '工具调用'
})
</script>

<style scoped>
.toolcalls-block {
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-secondary);
  overflow: hidden;
  margin:2px 0;
}
.toolcalls-block .toolcalls-summary {
  font-weight: 600;
  padding: 10px;
  font-size: 16px!important;
  cursor: pointer;
  color: var(--thinking-text);
  user-select: none;
  position: relative;
  padding-left: 60px;
}
.toolcalls-summary::before {
  content: '';
  display: inline-block;
  width: 0;
  height: 0;
  /* 三角形大小 */
  border-top: 0.6em solid transparent;
  border-bottom: 0.6em solid transparent;
  border-left: 0.9em solid currentColor;   /* 使用当前文字颜色 */
  margin-right: 0.4em;
  transition: transform 0.3s ease;
  vertical-align: middle;
  position: absolute;
  left: 12px;
  top: calc(50% - 0.6em)
}
.toolcalls-summary::after {
  content: '';
  position: absolute;
  left: 34px;
  top: calc(50% - 0.6em);
  width: 1.2em;
  height: 1.2em;
  background-color: #fff;
  mask-image: url('/svg/tools.svg');
  mask-size: contain;
  mask-repeat: no-repeat;
  mask-position: center;
  -webkit-mask-image: url('/svg/tools.svg');
  -webkit-mask-size: contain;
}
.toolcalls-block .toolcalls-summary:hover {
  background: rgba(99, 102, 241, 0.05);
}
.toolcalls-block .toolcalls-container {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows 0.3s ease;
  overflow: hidden;
}
.toolcalls-content {
  padding: 12px;
}
.toolcalls-container > .toolcalls-inner {
  min-height: 0;
}
.toolcalls-block[data-tool="open"] .toolcalls-summary::before {
  transform: rotate(90deg);
}
.toolcalls-block[data-tool="open"] .toolcalls-container {
  grid-template-rows: 1fr;
}

.toolcalls-block[data-tool="open"] .toolcalls-summary::before {
  transform: rotate(90deg);
}


.toolcall-card {
  border-radius: 6px;
  padding: 10px;
}

.toolcall-card.streaming {
  border-left: 3px solid var(--primary-color, #1890ff);
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}

.code-block-wrapper {
  position: relative;
  margin: 6px 0;
}

.tool-args, .result-content {
  background: var(--bg-secondary);
  padding: 8px;
  min-height: 30px;
  max-height: 320px;
  border-radius: 4px;
  font-size: 0.85rem;
  white-space: pre-wrap;
  word-break: break-all;
  font-family: Consolas, '微软雅黑', monospace;
  margin: 6px 0 0;
  overflow: auto;
}

.tool-args code {
  font-family: 'Courier New', '微软雅黑', monospace;
  font-size: 12px;
  color: var(--text-code, #999);
}

.result-content code {
  font-family: 'Courier New', '微软雅黑', monospace;
  font-size: 12px;
  color: var(--text-info, #26cf6d);
}
.code-block-wrapper .copy-code-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  background: rgba(255, 255, 255, 0.1);
  color: var(--text-secondary);
  border-radius: 6px;
  padding: 4px 6px;
  cursor: pointer;
  transition: all 0.2s;
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  gap: 4px;
  opacity: 0;
}
.code-block-wrapper .copy-code-btn:hover {
  background: rgba(99, 102, 241, 0.3);
  color: #fff;
}
.code-block-wrapper:hover .copy-code-btn {
  opacity: 1;
}

/* 工具调用卡片 */
.toolcalls-container {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.toolcall-card {
  background: rgba(59, 130, 246, 0.08);
  border: 1px solid rgba(59, 130, 246, 0.3);
  border-radius: 8px;
  padding: 12px;
}
.tool-name {
  font-weight: 600;
  font-size:14px;
  color: #3b82f6;
}
.tool-name::before {
  content: '';
  display: inline-block;
  width: 1.2em;
  height: 1.2em;
  margin-right: 0.4em;
  vertical-align: text-bottom;
  background-color: currentColor;
  mask-image: url('/svg/tool.svg');
  mask-size: contain;
  mask-repeat: no-repeat;
  mask-position: center;
  -webkit-mask-image: url('/svg/tool.svg');
  -webkit-mask-size: contain;
  -webkit-mask-repeat: no-repeat;
  -webkit-mask-position: center;
}
.streaming .tool-args, .streaming .result-content {
  max-height: none;
}
.tool-result {
  margin-top: 8px;
}
.result-label, .tool-label {
  font-weight: 500;
  font-size: 14px;
  color: var(--text-primary);
}
.result-label:before {
  content: '';
  display: inline-block;
  width: 1.2em;
  height: 1.2em;
  margin-right: 0.4em;
  vertical-align: text-bottom;
  background-color: currentColor; /* 颜色跟随文字 */
  mask-image: url('/svg/result.svg');
  mask-size: contain;
  mask-repeat: no-repeat;
  mask-position: center;
  -webkit-mask-image: url('/svg/result.svg');
  -webkit-mask-size: contain;
}

[theme-mode="light"] .toolcalls-summary::after {
  background-color: #666;
}
</style>