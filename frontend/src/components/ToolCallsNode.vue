<script setup lang="ts">
import { computed } from 'vue'

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
  } catch {
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
            <pre class="tool-args"><code>{{ formatArgs(tool.arguments) }}</code></pre>

            <div v-if="tool.result !== undefined" class="tool-result">
              <span class="result-label">结果：</span>
              <pre class="result-content"><code>{{ formatResult(tool.result) }}</code></pre>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.toolcalls-block {
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 8px;
  margin: 8px 0;
  overflow: hidden;
  background: var(--bg-secondary, #f5f5f5);
}

.toolcalls-summary {
  padding: 8px 12px;
  
  cursor: pointer;
  font-size: 14px;
  color: var(--text-secondary, #666);
  user-select: none;
  display: flex;
  align-items: center;
  gap: 6px;
}

.toolcalls-block[data-tool="open"] .toolcalls-summary::before {
  transform: rotate(90deg);
}

.toolcalls-container {
  max-height: 0;
  overflow: hidden;
  transition: max-height 0.3s ease;
}

.toolcalls-block[data-tool="open"] .toolcalls-container {
  max-height: 3000px;
}

.toolcalls-content {
  display: flex;
  padding: 12px;
  flex-direction: column;
  gap: 12px;
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

.tool-name {
  font-weight: 600;
  font-size: 14px;
  color: var(--text-primary, #333);
  display: block;
  margin-bottom: 6px;
}

.tool-args code {
  font-family: 'Courier New', monospace;
  font-size: 12px;
  color: var(--text-code, #999);
}

.tool-result {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed var(--border-light, #ddd);
}

.result-label {
  font-size: 13px;
  color: var(--text-secondary, #666);
  font-weight: 500;
}

.result-content {
  background: var(--code-bg, #f0f0f0);
  padding: 8px;
  border-radius: 4px;
  overflow-x: auto;
  margin: 6px 0 0 0;
}

.result-content code {
  font-family: 'Courier New', monospace;
  font-size: 12px;
  color: var(--text-success, #52c41a);
}
</style>