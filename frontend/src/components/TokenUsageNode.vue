<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  node: {
    type: 'tokenusage'
    content?: string
    attrs?: Record<string, any>
  }
  customId?: string
  isDark?: boolean
}>()

const data = computed(() => {
  try {
    const content = props.node.content || '{}'
    return JSON.parse(content)
  } catch {
    return {}
  }
})

const speed = computed(() => data.value.speed || '0 token/s')
const completionTokens = computed(() => data.value.completion_tokens ?? 0)
</script>

<template>
  <div class="tokenusage">
    <span title="生成速度" class="generation-speed">{{ speed }}</span>
    <span title="本次消耗" class="completion-tokens">{{ completionTokens }} token</span>
  </div>
</template>

<style scoped>
.tokenusage {
  display: flex;
  gap: 12px;
  padding: 4px 0;
  font-size: 12px;
  color: var(--text-secondary, #999);
}
</style>