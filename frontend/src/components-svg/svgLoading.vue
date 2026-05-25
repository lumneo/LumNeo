<template>
  <svg 
    xmlns="http://www.w3.org/2000/svg" 
    viewBox="0 0 60 40" 
    width="60" 
    height="40"
  >
    <!-- 圆点 1 -->
    <circle cx="12" cy="20" r="5" fill="#8b5cf6">
      <animate 
        attributeName="cy" 
        values="20;10;20" 
        keyTimes="0;0.3;1" 
        dur="1.2s" 
        begin="0s" 
        repeatCount="indefinite"
        calcMode="spline"
        keySplines="0.4 0 0.2 1; 0.4 0 0.2 1"
      />
    </circle>
    <!-- 圆点 2 -->
    <circle cx="30" cy="20" r="5" fill="#8b5cf6">
      <animate 
        attributeName="cy" 
        values="20;10;20" 
        keyTimes="0;0.3;1" 
        dur="1.2s" 
        begin="0.2s" 
        repeatCount="indefinite"
        calcMode="spline"
        keySplines="0.4 0 0.2 1; 0.4 0 0.2 1"
      />
    </circle>
    <!-- 圆点 3 -->
    <circle cx="48" cy="20" r="5" fill="#8b5cf6">
      <animate 
        attributeName="cy" 
        values="20;10;20" 
        keyTimes="0;0.3;1" 
        dur="1.2s" 
        begin="0.4s" 
        repeatCount="indefinite"
        calcMode="spline"
        keySplines="0.4 0 0.2 1; 0.4 0 0.2 1"
      />
    </circle>
  </svg>
</template>