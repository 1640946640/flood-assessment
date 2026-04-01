import Vue from 'vue'
import App from './App.vue'
import router from './router'
import store from './store'
import ElementUI from 'element-ui'
import 'element-ui/lib/theme-chalk/index.css'
// 导入Element UI显示工具类
import 'element-ui/lib/theme-chalk/display.css'
// 导入自定义暗色主题
import '@/assets/theme-dark.css'
import axios from 'axios'

Vue.config.productionTip = false
Vue.use(ElementUI)

// 配置axios
axios.defaults.baseURL = 'http://localhost:5000'
Vue.prototype.$http = axios

// 设置网站标题

// 检查本地存储中是否有暗色主题设置
const savedTheme = localStorage.getItem('webgis_theme')
if (savedTheme === 'dark') {
  document.documentElement.setAttribute('data-theme', 'dark')
}

new Vue({
  router,
  store,
  render: h => h(App)
}).$mount('#app') 