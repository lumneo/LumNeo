<<template>
  <div class="intro-card" :class="{ animate: isAnimate }">
    <div class="typewriter-container">
      <div class="typewriter-line">
        <span class="gradient-text">✨ LumNeo</span>
      </div>
      <div class="typewriter-line">
        <MarkdownRender
          custom-id="intro"
          :content="fullText"
          :final="final"
          :typewriter="true"
          :fade="true"
          :smooth-streaming="true"
          :max-live-nodes="0"
          :batch-rendering="true"
          :render-batch-size="12"
          :render-batch-delay="8"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import MarkdownRender from 'markstream-vue'

const fullText = `
*—— 不是冰冷的工具，是点亮你灵感的那束光*
你的本地智能体工作台

**双擎驱动，懂你所想**
🧠 本地模型：隐私无忧，离线深思
☁️ 云端大模型：算力澎湃，破解难题

**文件读写，如臂使指**
📂 拖入文档/图片 → 自动解析结构与细节
💾 提出修改需求 → 直接写入并保存结果

**万千角色，一键切换**
🎭 自由创建专属角色，定义独特人格与边界
🔧 为每个角色绑定独立工具集（含 MCP 服务）
⚡ 随时无缝切换，让专业的人做专业的事

**LumNeo —— 你的全能本地灵感引擎**
✨ 点击这里，开始你的专属对话`

const final = ref(false)
const isAnimate = ref(false)

onMounted(() => {
  setTimeout(() => {
    final.value = true
    setTimeout(() => {
      isAnimate.value = true
    }, 260)
  }, 2600)
})
</script>

<style scoped>
.intro-card {
  background: #131720;
  border: 1px solid rgba(99, 102, 241, 0.2);
  border-radius: 16px;
  padding: 32px;
  max-width: 520px;
  margin: 0 auto;
  cursor: pointer;
  font-family: 'Inter', system-ui, sans-serif;
}

.animate {
  animation: jelly-pop 0.6s cubic-bezier(0.68, -0.55, 0.265, 1.55),
    breathe 1.6s ease-in-out infinite;
}

.gradient-text {
  font-size: 2rem;
  font-weight: 700;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

/* 打字机光标样式 */
:deep(.typewriter-cursor) {
  color: #fbbf24 !important;
  font-weight: 200 !important;
  animation: blink 1s step-end infinite !important;
}

@keyframes blink {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0;
  }
}

@keyframes jelly-pop {
  0% {
    transform: scale(0.8);
    opacity: 0;
  }
  60% {
    transform: scale(1.03);
    opacity: 1;
  }
  80% {
    transform: scale(0.97);
  }
  100% {
    transform: scale(1);
    opacity: 1;
  }
}

@keyframes breathe {
  0% {
    box-shadow: 0 0 2px rgba(149, 193, 223, 0.6);
  }
  50% {
    box-shadow: 0 0 24px 6px #7f86be;
  }
  100% {
    box-shadow: 0 0 2px rgba(149, 193, 223, 0.8);
  }
}
</style>