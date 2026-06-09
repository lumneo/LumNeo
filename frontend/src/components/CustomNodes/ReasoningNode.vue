<template>
  <div class="reasoning-block" :data-reasoning="isExpanded ? 'open' : undefined">
    <div class="reasoning-summary no-select" @click="toggle">
      {{ summaryText }}
    </div>
    <div class="reasoning-container">
      <div class="reasoning-inner">
        <div class="reasoning-content">
          <MarkdownRender
            :content="String(props.node.content ?? '')"
            :custom-id="props.customId"
            :is-dark="props.isDark"
            :custom-html-tags="['reasoning']"
            :typewriter="false"
            :viewport-priority="false"
            :defer-nodes-until-visible="false"
            :max-live-nodes="0"
            :batch-rendering="false"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import MarkdownRender from 'markstream-vue'

const props = defineProps<{
  node: {
    type: 'reasoning'
    content?: string
    loading?: boolean
    autoClosed?: boolean
    attrs?: Record<string, any>
  }
  customId?: string
  isDark?: boolean
}>()
const isExpanded = ref(props.node.loading || props.node.autoClosed)
const isOpen = computed(() => {
  return props.node.loading || props.node.autoClosed || false
})


watch(() => isOpen.value, (newVal) => {
  isExpanded.value = newVal
})
const timeStr = computed(() => {
  const attrs = props.node.attrs || {}  
  if (attrs[0][1]) {
    return ` (${attrs[0][1]}秒)`
  }
  return ''
})

const summaryText = computed(() => {
  if (props.node.loading) {
    return '思考中...'
  }
  return `已思考${timeStr.value}`
})

function toggle() {
  isExpanded.value = !isExpanded.value
}
</script>

<style scoped>
/* 思考块 */
.reasoning-block {
  background: rgba(129, 78, 247, 0.06);
  border-radius: 6px;
  overflow: hidden;
  margin:2px 0;
}
.reasoning-block .reasoning-summary {
  font-weight: 600;
  padding: 10px;
  font-size: 16px!important;
  color: var(--thinking-text);
  cursor: pointer;
  user-select: none;
  position: relative;
  padding-left:40px;
}
.reasoning-block .reasoning-summary:hover {
  background: rgba(99, 102, 241, 0.05);
}
.reasoning-content {
  padding: 12px;
  font-size:14px!important;
}
.reasoning-content .paragraph-node {
  font-size:14px!important;
}
.reasoning-summary::before {
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
  position: relative;
  left: -26px;
}
.reasoning-summary::after {
  content: '';
  position: absolute;
  left: 34px;
  top: calc(50% - 0.6em);
  width: 1.2em;
  height: 1.2em;
  mask-image: url('/svg/thinking.svg');
  mask-size: contain;
  mask-repeat: no-repeat;
  mask-position: center;
  background-color: #fff;
  -webkit-mask-image: url('/svg/thinking.svg');
  -webkit-mask-size: contain;
  -webkit-mask-repeat: no-repeat;
  -webkit-mask-position: center;
}
.reasoning-container {
  font-size: 0.9rem;
  color: var(--text-secondary);
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows 0.3s ease;
  overflow: hidden;
}
.reasoning-container > .reasoning-inner {
  min-height: 0; /* 必须，否则 grid 不会折叠 */
}
.reasoning-block[data-reasoning="open"] .reasoning-summary {
  background: rgba(99, 102, 241, 0.1);
}
.reasoning-block[data-reasoning="open"] .reasoning-summary::before {
  transform: rotate(90deg);
}
.reasoning-block[data-reasoning="open"] .reasoning-container {
  grid-template-rows: 1fr;
}

[theme-mode="light"] .reasoning-summary::after {
  background-color: #666;
}
</style>