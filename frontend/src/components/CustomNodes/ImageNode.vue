<template>
   <n-image
    class="image-node"
    width="512"
    :src="node.src"
    :title="node.title"
    :loading="node.loading"
    :alt="node.alt"
  />
</template>

<script setup lang="ts">
import { NImage } from 'naive-ui'

const props = defineProps<{
  node: {
    type: 'image'
    src?: string
    title?: string
    loading?: boolean
    alt?: string
  }
}>()
</script>

<style scoped>
.image-node {
  border-radius: 8px;
  cursor: pointer;
}
</style>
