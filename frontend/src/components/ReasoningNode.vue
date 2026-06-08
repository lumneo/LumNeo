<script setup lang="ts">
import { computed } from 'vue'
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

const isOpen = computed(() => {
  return props.node.loading || props.node.autoClosed || false
})

const timeStr = computed(() => {
  const attrs = props.node.attrs || {}
  if (attrs.time) {
    return ` (${attrs.time}秒)`
  }
  return ''
})

const summaryText = computed(() => {
  if (props.node.loading) {
    return '思考中...'
  }
  return `已思考${timeStr.value}`
})

function toggle(e: MouseEvent) {
  const target = e.target as HTMLElement
  const block = target.closest('.reasoning-block') as HTMLElement | null
  if (!block) return

  const isCurrentlyOpen = block.dataset.reasoning === 'open'
  if (isCurrentlyOpen) {
    block.removeAttribute('data-reasoning')
  } else {
    block.setAttribute('data-reasoning', 'open')
  }
}
</script>

<template>
  <div class="reasoning-block" :data-reasoning="isOpen ? 'open' : undefined">
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