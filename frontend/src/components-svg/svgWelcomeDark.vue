<template>
  <div class="neon-sign">
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 980 600" width="100%" height="70vh" preserveAspectRatio="xMidYMid meet">
      <defs>
        <radialGradient id="bgGlow" cx="50%" cy="40%" r="60%">
          <stop offset="0%" stop-color="#2d1b69" stop-opacity="0.4"/>
          <stop offset="50%" stop-color="#1a1a2e" stop-opacity="0.2"/>
          <stop offset="100%" stop-color="#0f0f1a" stop-opacity="0"/>
        </radialGradient>
        <linearGradient id="btnGrad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="#6366f1"/>
          <stop offset="100%" stop-color="#8b5cf6"/>
        </linearGradient>
        <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="4" result="blur"/>
          <feMerge>
            <feMergeNode in="blur"/>
            <feMergeNode in="blur"/>
            <feMergeNode in="SourceGraphic"/>
          </feMerge>
        </filter>
        <filter id="softShadow" x="-20%" y="-20%" width="140%" height="140%">
          <feDropShadow dx="0" dy="4" stdDeviation="8" flood-color="#000" flood-opacity="0.3"/>
        </filter>
        <radialGradient id="pulseGlow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stop-color="#8b5cf6" stop-opacity="0.6"/>
          <stop offset="50%" stop-color="#6366f1" stop-opacity="0.2"/>
          <stop offset="100%" stop-color="#6366f1" stop-opacity="0"/>
        </radialGradient>
      </defs>

      <rect width="100%" height="100%" fill="#161622"/>
      <rect width="100%" height="100%" fill="url(#bgGlow)"/>

      <!-- 浮动粒子 -->
      <circle cx="200" cy="150" r="2" fill="#6366f1" opacity="0.3">
        <animate attributeName="cy" values="150;130;150" dur="4s" repeatCount="indefinite"/>
        <animate attributeName="opacity" values="0.3;0.7;0.3" dur="3s" repeatCount="indefinite"/>
      </circle>
      <circle cx="750" cy="200" r="1.5" fill="#8b5cf6" opacity="0.4">
        <animate attributeName="cy" values="200;220;200" dur="5s" repeatCount="indefinite"/>
        <animate attributeName="opacity" values="0.4;0.8;0.4" dur="4s" repeatCount="indefinite"/>
      </circle>
      <circle cx="150" cy="450" r="2.5" fill="#6366f1" opacity="0.2">
        <animate attributeName="cy" values="450;430;450" dur="6s" repeatCount="indefinite"/>
        <animate attributeName="opacity" values="0.2;0.6;0.2" dur="5s" repeatCount="indefinite"/>
      </circle>
      <circle cx="800" cy="400" r="1.8" fill="#a78bfa" opacity="0.3">
        <animate attributeName="cy" values="400;420;400" dur="4.5s" repeatCount="indefinite"/>
        <animate attributeName="opacity" values="0.3;0.7;0.3" dur="3.5s" repeatCount="indefinite"/>
      </circle>
      <circle cx="300" cy="100" r="1.2" fill="#818cf8" opacity="0.35">
        <animate attributeName="cy" values="100;80;100" dur="5.5s" repeatCount="indefinite"/>
        <animate attributeName="opacity" values="0.35;0.7;0.35" dur="4s" repeatCount="indefinite"/>
      </circle>
      <circle cx="650" cy="500" r="2" fill="#6366f1" opacity="0.25">
        <animate attributeName="cy" values="500;480;500" dur="5s" repeatCount="indefinite"/>
        <animate attributeName="opacity" values="0.25;0.6;0.25" dur="4.5s" repeatCount="indefinite"/>
      </circle>

      <!-- 旋转圆环 -->
      <g transform="translate(450, 280)">
        <circle cx="0" cy="0" r="120" fill="none" stroke="#6366f1" stroke-width="0.5" opacity="0.1">
          <animateTransform attributeName="transform" type="rotate" from="0" to="360" dur="60s" repeatCount="indefinite"/>
        </circle>
        <circle cx="0" cy="0" r="140" fill="none" stroke="#8b5cf6" stroke-width="0.3" opacity="0.08">
          <animateTransform attributeName="transform" type="rotate" from="360" to="0" dur="80s" repeatCount="indefinite"/>
        </circle>
      </g>

      <!-- Logo 脉冲动画 -->
      <g transform="translate(450, 180)">
        <circle cx="0" cy="0" r="50" fill="url(#pulseGlow)" opacity="0">
          <animate attributeName="r" values="30;70;30" dur="3s" repeatCount="indefinite"/>
          <animate attributeName="opacity" values="0.6;0;0.6" dur="3s" repeatCount="indefinite"/>
        </circle>
        <circle cx="0" cy="0" r="50" fill="url(#pulseGlow)" opacity="0">
          <animate attributeName="r" values="30;70;30" dur="3s" begin="1.5s" repeatCount="indefinite"/>
          <animate attributeName="opacity" values="0.6;0;0.6" dur="3s" begin="1.5s" repeatCount="indefinite"/>
        </circle>

        <g filter="url(#glow)">
          <polygon points="0,-35 30.3,-17.5 30.3,17.5 0,35 -30.3,17.5 -30.3,-17.5" 
                  fill="none" stroke="url(#btnGrad)" stroke-width="2" opacity="0.8">
            <animate attributeName="opacity" values="0.8;1;0.8" dur="2s" repeatCount="indefinite"/>
          </polygon>
          <polygon points="0,-22 19.1,-11 19.1,11 0,22 -19.1,11 -19.1,-11" 
                  fill="url(#btnGrad)" opacity="0.9">
            <animate attributeName="opacity" values="0.9;1;0.9" dur="2s" repeatCount="indefinite"/>
          </polygon>
          <circle cx="0" cy="0" r="6" fill="#fff" opacity="0.9">
            <animate attributeName="r" values="6;7;6" dur="2s" repeatCount="indefinite"/>
          </circle>
        </g>
      </g>

      <!-- 文字渐入动画 -->
      <text x="450" y="260" text-anchor="middle" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" 
            font-size="28" font-weight="600" fill="#e2e8f0" letter-spacing="0.5" opacity="0">
        你好，我是 LumNeo
        <animate attributeName="opacity" values="0;1" dur="0.8s" begin="0.3s" fill="freeze"/>
        <animate attributeName="y" values="270;260" dur="0.8s" begin="0.3s" fill="freeze"/>
      </text>

      <text x="450" y="295" text-anchor="middle" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" 
            font-size="15" fill="#94a3b8" letter-spacing="0.3" opacity="0">
        你的智能伙伴，随时为你效劳
        <animate attributeName="opacity" values="0;1" dur="0.8s" begin="0.6s" fill="freeze"/>
      </text>

      <!-- 分割线 -->
      <line x1="380" y1="325" x2="520" y2="325" stroke="#334155" stroke-width="1" opacity="0">
        <animate attributeName="opacity" values="0;0.5" dur="0.5s" begin="0.9s" fill="freeze"/>
        <animate attributeName="x1" values="450;380" dur="0.5s" begin="0.9s" fill="freeze"/>
        <animate attributeName="x2" values="450;520" dur="0.5s" begin="0.9s" fill="freeze"/>
      </line>

      <text x="450" y="355" text-anchor="middle" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" 
            font-size="13" fill="#64748b" opacity="0">
        你可以尝试以下功能
        <animate attributeName="opacity" values="0;1" dur="0.5s" begin="1.1s" fill="freeze"/>
      </text>

      <!-- 按钮渐入动画 -->
      <g transform="translate(210, 390)" filter="url(#softShadow)" opacity="0">
        <rect x="0" y="0" width="170" height="56" rx="12" fill="#1e1e2e" stroke="#2d2d44" stroke-width="1"/>
        <text x="24" y="22" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" 
              font-size="14" font-weight="500" fill="#e2e8f0">💻 写代码</text>
        <text x="24" y="42" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" 
              font-size="11" fill="#64748b">生成、调试、优化代码</text>
        <animate attributeName="opacity" values="0;1" dur="0.5s" begin="1.3s" fill="freeze"/>
        <animateTransform attributeName="transform" type="translate" values="210,400;210,390" dur="0.5s" begin="1.3s" fill="freeze"/>
      </g>

      <g transform="translate(400, 390)" filter="url(#softShadow)" opacity="0">
        <rect x="0" y="0" width="170" height="56" rx="12" fill="#1e1e2e" stroke="#2d2d44" stroke-width="1"/>
        <text x="24" y="22" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" 
              font-size="14" font-weight="500" fill="#e2e8f0">📄 文件解析</text>
        <text x="24" y="42" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" 
              font-size="11" fill="#64748b">解析文档、提取关键信息</text>
        <animate attributeName="opacity" values="0;1" dur="0.5s" begin="1.5s" fill="freeze"/>
        <animateTransform attributeName="transform" type="translate" values="400,400;400,390" dur="0.5s" begin="1.5s" fill="freeze"/>
      </g>

      <g transform="translate(590, 390)" filter="url(#softShadow)" opacity="0">
        <rect x="0" y="0" width="170" height="56" rx="12" fill="#1e1e2e" stroke="#2d2d44" stroke-width="1"/>
        <text x="24" y="22" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" 
              font-size="14" font-weight="500" fill="#e2e8f0">✨ 创意写作</text>
        <text x="24" y="42" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" 
              font-size="11" fill="#64748b">文案、故事、诗歌创作</text>
        <animate attributeName="opacity" values="0;1" dur="0.5s" begin="1.7s" fill="freeze"/>
        <animateTransform attributeName="transform" type="translate" values="590,400;590,390" dur="0.5s" begin="1.7s" fill="freeze"/>
      </g>

      <g transform="translate(305, 466)" filter="url(#softShadow)" opacity="0">
        <rect x="0" y="0" width="170" height="56" rx="12" fill="#1e1e2e" stroke="#2d2d44" stroke-width="1"/>
        <text x="24" y="22" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" 
              font-size="14" font-weight="500" fill="#e2e8f0">❓ 知识问答</text>
        <text x="24" y="42" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" 
              font-size="11" fill="#64748b">解答各类专业问题</text>
        <animate attributeName="opacity" values="0;1" dur="0.5s" begin="1.9s" fill="freeze"/>
        <animateTransform attributeName="transform" type="translate" values="305,476;305,466" dur="0.5s" begin="1.9s" fill="freeze"/>
      </g>

      <g transform="translate(495, 466)" filter="url(#softShadow)" opacity="0">
        <rect x="0" y="0" width="170" height="56" rx="12" fill="#1e1e2e" stroke="#2d2d44" stroke-width="1"/>
        <text x="24" y="22" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" 
              font-size="14" font-weight="500" fill="#e2e8f0">📑 文档生成</text>
        <text x="24" y="42" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" 
              font-size="11" fill="#64748b">自动生成专业文档和演示</text>
        <animate attributeName="opacity" values="0;1" dur="0.5s" begin="2.1s" fill="freeze"/>
        <animateTransform attributeName="transform" type="translate" values="495,476;495,466" dur="0.5s" begin="2.1s" fill="freeze"/>
      </g>

      <!-- 底部提示 -->
      <g transform="translate(450, 555)" opacity="0">
        <text x="0" y="0" text-anchor="middle" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" 
              font-size="12" fill="#475569">
          💡 支持上传文件、图片，或直接输入你的问题
        </text>
        <animate attributeName="opacity" values="0;1" dur="0.5s" begin="2.3s" fill="freeze"/>
      </g>

      <line x1="350" y1="575" x2="550" y2="575" stroke="#334155" stroke-width="1" opacity="0">
        <animate attributeName="opacity" values="0;0.3" dur="0.5s" begin="2.5s" fill="freeze"/>
      </line>
    </svg>
  </div>
</template>

<script>
export default {
  name: 'NeonSign'
}
</script>