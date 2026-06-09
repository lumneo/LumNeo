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


<style scoped>
.toolpreview-block {
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-secondary);
  overflow: hidden;
  margin:2px 0;
}
.toolpreview-block .toolpreview-summary {
  font-weight: 600;
  padding: 10px;
  font-size: 16px!important;
  cursor: pointer;
  color: var(--thinking-text);
  user-select: none;
  position: relative;
  padding-left: 60px;
}
.toolpreview-summary::before {
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
.toolpreview-summary::after {
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
.toolpreview-block .toolpreview-summary:hover {
  background: rgba(99, 102, 241, 0.05);
}
.toolpreview-block .toolpreview-container {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows 0.3s ease;
  overflow: hidden;
}
.toolpreview-container {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.toolpreview-content {
  padding: 12px;
}
.toolpreview-container > .toolpreview-inner {
  min-height: 0;
}
.toolpreview-block[data-preview="open"] .toolpreview-summary::before {
  transform: rotate(90deg);
}
.toolpreview-block[data-preview="open"] .toolpreview-container {
  grid-template-rows: 1fr;
}

.toolpreview-block[data-preview="open"] .toolpreview-summary::before {
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

.tool-args code {
  font-family: 'Courier New', monospace;
  font-size: 12px;
  color: var(--text-code, #999);
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
.tool-args {
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
}
.streaming .tool-args {
  max-height: none;
}
</style>