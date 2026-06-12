<template>
  <div class="tokenusage">
    <span title="生成速度" class="generation-speed">{{ speed }}</span>
    <span title="本次消耗" class="completion-tokens">{{ completionTokens }} token</span>
  </div>
</template>

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
  } catch(e) {
    console.error(e)
    return {}
  }
})

const speed = computed(() => data.value.speed || '0 token/s')
const completionTokens = computed(() => data.value.completion_tokens ?? 0)
</script>


<style scoped>
.tokenusage {
  display: flex;
  gap: 12px;
  padding: 4px 0;
  font-size: 12px;
  color: var(--text-secondary, #999);
}
.token-usage {
  font-size: 12px;
  color: #6b7280;
  display: none;
}

.message-row.assistant:last-child .message-content .token-usage {
  display:block !important; /* 显示token使用情况 */
}

.generation-speed::before {
  content: '';
  display: inline-block;
  width: 1.5em;
  height: 1.5em;
  margin-right: 0.4em;
  vertical-align: text-bottom;
  background-image: url('/svg/speed.svg');
  background-size: contain;
  background-repeat: no-repeat;
  background-position: center;

}
.completion-tokens::before {
  content: '';
  display: inline-block;
  width: 1.6em;
  height: 1.6em;
  margin-left: 0.6em;
  vertical-align: text-bottom;
  background-image: url('/svg/tokens.svg');
  background-size: contain;
  background-repeat: no-repeat;
  background-position: center;
}
</style>