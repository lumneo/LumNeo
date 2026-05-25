<template>
  <div class="neon-sign">
    <svg viewBox="0 0 800 400" width="100%" height="100%">
      <defs>
        <!-- 霓虹彩虹渐变（随时间流动） -->
        <linearGradient id="neon-gradient" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stop-color="#ff0080">
            <animate attributeName="stop-color" values="#ff0080;#00ffff;#ff0080" dur="4s" repeatCount="indefinite" />
          </stop>
          <stop offset="33%" stop-color="#7928ca">
            <animate attributeName="stop-color" values="#7928ca;#ff0080;#7928ca" dur="4s" repeatCount="indefinite" />
          </stop>
          <stop offset="66%" stop-color="#00ffff">
            <animate attributeName="stop-color" values="#00ffff;#7928ca;#00ffff" dur="4s" repeatCount="indefinite" />
          </stop>
          <stop offset="100%" stop-color="#ff0080">
            <animate attributeName="stop-color" values="#ff0080;#00ffff;#ff0080" dur="4s" repeatCount="indefinite" />
          </stop>
        </linearGradient>

        <!-- 副标题霓虹渐变 -->
        <linearGradient id="cyan-glow" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stop-color="#00ffff">
            <animate attributeName="stop-color" values="#00ffff;#0088ff;#00ffff" dur="5s" repeatCount="indefinite" />
          </stop>
          <stop offset="100%" stop-color="#0088ff">
            <animate attributeName="stop-color" values="#0088ff;#00ffff;#0088ff" dur="5s" repeatCount="indefinite" />
          </stop>
        </linearGradient>

        <!-- 霓虹发光滤镜（粉色/青色背景） -->
        <filter id="glow-primary" x="-30%" y="-30%" width="160%" height="160%">
          <feGaussianBlur stdDeviation="6" result="blur1" />
          <feGaussianBlur stdDeviation="15" result="blur2" />
          <feGaussianBlur stdDeviation="25" result="blur3" />
          <feMerge>
            <feMergeNode in="blur3" />
            <feMergeNode in="blur2" />
            <feMergeNode in="blur1" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>

        <!-- 柔和发光滤镜（用于副标题） -->
        <filter id="glow-soft" x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="4" result="blur1" />
          <feGaussianBlur stdDeviation="10" result="blur2" />
          <feMerge>
            <feMergeNode in="blur2" />
            <feMergeNode in="blur1" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      <!-- 装饰边框（透明背景上的霓虹灯框架） -->
      <rect x="140" y="70" width="520" height="230" rx="30" fill="none" stroke="rgba(255,255,255,0.2)" stroke-width="4" class="flicker" />
      <rect x="150" y="80" width="500" height="210" rx="20" fill="none" stroke="rgba(255,255,255,0.3)" stroke-width="1" stroke-dasharray="8,8" class="breathe" />
      
      <!-- 边框边角装饰 -->
      <circle cx="155" cy="85" r="4" fill="rgba(255,255,255,0.3)" class="flicker" />
      <circle cx="645" cy="85" r="4" fill="rgba(255,255,255,0.3)" class="flicker" />
      <circle cx="155" cy="275" r="4" fill="rgba(255,255,255,0.3)" class="flicker" />
      <circle cx="645" cy="275" r="4" fill="rgba(255,255,255,0.3)" class="flicker" />

      <!-- ================= LUMNEO 文字（霓虹层） ================= -->
      
      <!-- 第一层：外部光晕（粗管发光） -->
      <text x="400" y="175" font-family="'Arial Black', 'Impact', 'Helvetica Neue', sans-serif" font-size="90" font-weight="900" text-anchor="middle" fill="none" stroke="url(#neon-gradient)" stroke-width="14" filter="url(#glow-primary)" opacity="0.9" letter-spacing="2" class="flicker">LUMNEO</text>

      <!-- 第二层：霓虹灯管实体（渐变描边） -->
      <text x="400" y="175" font-family="'Arial Black', 'Impact', 'Helvetica Neue', sans-serif" font-size="90" font-weight="900" text-anchor="middle" fill="none" stroke="url(#neon-gradient)" stroke-width="6" letter-spacing="2" class="pulse">LUMNEO</text>

      <!-- 第三层：内部明亮核心（白色描边） -->
      <text x="400" y="175" font-family="'Arial Black', 'Impact', 'Helvetica Neue', sans-serif" font-size="90" font-weight="900" text-anchor="middle" fill="none" stroke="#ffffff" stroke-width="2" letter-spacing="2" class="pulse">LUMNEO</text>

      <!-- 第四层：炽热内部（白色填充） -->
      <text x="400" y="175" font-family="'Arial Black', 'Impact', 'Helvetica Neue', sans-serif" font-size="90" font-weight="900" text-anchor="middle" fill="#ffffff" letter-spacing="2" class="pulse">LUMNEO</text>

      <!-- ================= 副标题：我是你的灵魂伴侣（霓虹层） ================= -->

      <!-- 第一层：外部光晕 -->
      <text x="400" y="260" font-family="'PingFang SC', 'Microsoft YaHei', 'WenQuanYi Micro Hei', sans-serif" font-size="28" font-weight="500" text-anchor="middle" fill="url(#cyan-glow)" filter="url(#glow-soft)" opacity="0.9" letter-spacing="4" class="breathe">我是你的灵魂伴侣</text>

      <!-- 第二层：霓虹灯管实体（青色描边） -->
      <text x="400" y="260" font-family="'PingFang SC', 'Microsoft YaHei', 'WenQuanYi Micro Hei', sans-serif" font-size="28" font-weight="500" text-anchor="middle" fill="none" stroke="#00ffff" stroke-width="2" letter-spacing="4" class="breathe">我是你的灵魂伴侣</text>

      <!-- 第三层：内部明亮核心（白色填充） -->
      <text x="400" y="260" font-family="'PingFang SC', 'Microsoft YaHei', 'WenQuanYi Micro Hei', sans-serif" font-size="28" font-weight="500" text-anchor="middle" fill="#ffffff" letter-spacing="4" class="breathe">我是你的灵魂伴侣</text>

      <!-- 底部装饰霓虹灯线 -->
      <path d="M 300 300 L 500 300" fill="none" stroke="#00ffff" stroke-width="2" filter="url(#glow-soft)" opacity="0.8" class="breathe" />
      <circle cx="300" cy="300" r="4" fill="#00ffff" filter="url(#glow-soft)" opacity="0.8" class="breathe" />
      <circle cx="500" cy="300" r="4" fill="#00ffff" filter="url(#glow-soft)" opacity="0.8" class="breathe" />
    </svg>
  </div>
</template>

<script>
export default {
  name: 'NeonSign'
}
</script>

<style scoped>
.neon-sign {
  width: 100%;
  height: 100%;
  background: transparent;
  display: flex;
  align-items: center;
  justify-content: center;
}
 /* 呼吸脉冲动画 */
@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.6; }
}

/* 随机闪烁动画（模拟真霓虹灯管） */
@keyframes flicker {
    0%, 90%, 100% { opacity: 1; }
    92% { opacity: 0.4; }
    93% { opacity: 0.9; }
    94% { opacity: 0.2; }
    95% { opacity: 0.8; }
    96% { opacity: 1; }
}

/* 柔和呼吸动画 */
@keyframes breathe {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.7; }
}

.pulse { animation: pulse 3s ease-in-out infinite; }
.flicker { animation: flicker 6s linear infinite; }
.breathe { animation: breathe 4s ease-in-out infinite; }
</style>