<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  node: {
    type: 'toolpreview'
    content?: string
    loading?: boolean
    attrs?: Record<string, any>
  }
  customId?: string
  isDark?: boolean
}>()

interface PreviewTool {
  name: string
  arguments: string
  streaming: boolean
}

interface PreviewData {
  tools: PreviewTool[]
  count: number
  loading: boolean
}

const data = computed<PreviewData>(() => {
  try {
    const content = props.node.content || '{}'
    return JSON.parse(content)
  } catch {
    return { tools: [], count: 0, loading: false }
  }
})

const tools = computed(() => data.value.tools || [])
const toolCount = computed(() => data.value.count || tools.value.length)
const isLoading = computed(() => data.value.loading || props.node.loading || false)

const title = computed(() => {
  if (isLoading.value) {
    return toolCount.value > 0 ? `工具调用中… (${toolCount.value}个)` : '工具调用中…'
  }
  return toolCount.value > 0 ? `工具调用预览 (${toolCount.value}个)` : '工具调用预览'
})

function toggle(e: MouseEvent) {
  const target = e.target as HTMLElement
  const block = target.closest('.toolpreview-block') as HTMLElement | null
  if (!block) return

  const isCurrentlyOpen = block.dataset.preview === 'open'
  if (isCurrentlyOpen) {
    block.removeAttribute('data-preview')
  } else {
    block.setAttribute('data-preview', 'open')
  }
}
</script>

<template>
  <div class="toolpreview-block" :data-preview="isLoading ? 'open' : undefined">
    <div class="toolpreview-summary no-select" @click="toggle">
      {{ title }}
    </div>
    <div class="toolpreview-container">
      <div class="toolpreview-inner">
        <div class="toolpreview-content">
          <div 
            v-for="(tool, index) in tools" 
            :key="index"
            class="toolcall-card"
            :class="{ 'streaming': tool.streaming }"
          >
            <span class="tool-name">{{ tool.name }}</span>
            <pre class="tool-args"><code>{{ tool.arguments }}</code></pre>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.toolpreview-block {
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 8px;
  margin: 8px 0;
  overflow: hidden;
  background: var(--bg-secondary, #f5f5f5);
}

.toolpreview-summary {
  padding: 8px 12px;
  background: var(--bg-hover, #e8e8e8);
  cursor: pointer;
  font-size: 14px;
  color: var(--text-secondary, #666);
  user-select: none;
  display: flex;
  align-items: center;
  gap: 6px;
}

.toolpreview-summary::before {
  content: '▸';
  display: inline-block;
  transition: transform 0.2s;
  font-size: 12px;
}

.toolpreview-block[data-preview="open"] .toolpreview-summary::before {
  transform: rotate(90deg);
}

.toolpreview-container {
  max-height: 0;
  overflow: hidden;
  transition: max-height 0.3s ease;
}

.toolpreview-block[data-preview="open"] .toolpreview-container {
  max-height: 3000px;
}

.toolpreview-inner {
  padding: 12px;
  background: var(--bg-tertiary, #fafafa);
}

.toolpreview-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.toolcall-card {
  border: 1px solid var(--border-light, #ddd);
  border-radius: 6px;
  padding: 10px;
  background: var(--bg-card, #fff);
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

.tool-args {
  background: var(--code-bg, #f0f0f0);
  padding: 8px;
  border-radius: 4px;
  overflow-x: auto;
  margin: 0;
}

.tool-args code {
  font-family: 'Courier New', monospace;
  font-size: 12px;
  color: var(--text-code, #333);
}
</style>