import { createApp } from 'vue'
import { createPinia } from 'pinia'
import 'virtual:svg-icons-register'
import App from './App.vue'
import './assets/global.css'
import 'katex/dist/katex.min.css'
import router from './router'

const app = createApp(App)

// 状态管理
app.use(createPinia()).use(router)

app.mount('#app')