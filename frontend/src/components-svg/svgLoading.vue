<template>
<svg width="42" height="42" viewBox="0 0 42 42" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="dg" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#8250f8"/>
      <stop offset="100%" stop-color="#c4a5f9"/>
    </linearGradient>
    <filter id="df"><feGaussianBlur stdDeviation="2.5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
  </defs>
  <g>
    <circle cx="21" cy="21" r="4" fill="#8250f8" filter="url(#df)" opacity="0">
      <animate attributeName="cx" values="6;36;6" dur="1.2s" repeatCount="indefinite" calcMode="spline" keySplines="0.45 0 0.55 1;0.45 0 0.55 1"/>
      <animate attributeName="opacity" values="0;1;1;0" dur="3s" repeatCount="indefinite" keyTimes="0;0.666;0.933;1"/>
    </circle>
    <circle cx="21" cy="21" r="3" fill="#895bf7" filter="url(#df)" opacity="0">
      <animate attributeName="cx" values="6;36;6" dur="1.2s" begin="0.08s" repeatCount="indefinite" calcMode="spline" keySplines="0.45 0 0.55 1;0.45 0 0.55 1"/>
      <animate attributeName="opacity" values="0;0.7;0" dur="1.2s" begin="0.08s" repeatCount="indefinite"/>
      <animate attributeName="opacity" values="0;1;1;0" dur="3s" repeatCount="indefinite" keyTimes="0;0.666;0.933;1"/>
    </circle>
    <circle cx="21" cy="21" r="2" fill="#c4a5f9" filter="url(#df)" opacity="0">
      <animate attributeName="cx" values="6;36;6" dur="1.2s" begin="0.16s" repeatCount="indefinite" calcMode="spline" keySplines="0.45 0 0.55 1;0.45 0 0.55 1"/>
      <animate attributeName="opacity" values="0;0.5;0" dur="1.2s" begin="0.16s" repeatCount="indefinite"/>
      <animate attributeName="opacity" values="0;1;1;0" dur="3s" repeatCount="indefinite" keyTimes="0;0.666;0.933;1"/>
    </circle>
  </g>
</svg>
</template>