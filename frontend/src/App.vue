<template>
  <div id="app" :class="{ 'dark': isDarkTheme }">
    <el-container class="main-container">
      <el-header height="60px">
        <div class="header-logo">
          <i class="el-icon-map-location logo-icon"></i>
          <span class="logo-text">洪涝灾害影响评估平台</span>
        </div>
        <div class="header-menu">
          <el-menu mode="horizontal" :default-active="activeIndex" router style="border-bottom: none;">
            <el-menu-item index="/data-visualization">数据可视化</el-menu-item>
            <el-submenu index="/auxiliary">
              <template slot="title">辅助功能</template>
              <el-menu-item index="/auxiliary/create-grid">
                <i class="el-icon-document"></i>
                <span>模板生成</span>
              </el-menu-item>
              <el-menu-item index="/auxiliary/raster-alignment">
                <i class="el-icon-rank"></i>
                <span>栅格对齐</span>
              </el-menu-item>
              <el-menu-item index="/auxiliary/correlation-analysis">
                <i class="el-icon-data-analysis"></i>
                <span>相关性分析</span>
              </el-menu-item>
              <el-menu-item index="/auxiliary/raster-compare">
                <i class="el-icon-picture"></i>
                <span>栅格比较分析</span>
              </el-menu-item>
              <el-menu-item index="/auxiliary/export-csv">
                <i class="el-icon-download"></i>
                <span>多栅格导出</span>
              </el-menu-item>
              <el-menu-item index="/auxiliary/raster-statistics">
                <i class="el-icon-s-data"></i>
                <span>栅格统计</span>
              </el-menu-item>
              <!-- <el-menu-item index="/auxiliary/flood-points">易涝点计算</el-menu-item> -->
            </el-submenu>
            <el-menu-item index="/flood-assessment">洪水分析</el-menu-item>
          </el-menu>
        </div>
        <div class="user-info">
          <el-switch
            v-model="isDarkTheme"
            active-color="#13ce66"
            inactive-color="#409EFF"
            active-text="暗色"
            inactive-text="亮色"
            @change="toggleTheme">
          </el-switch>
          <!-- <span class="username">用户名</span>
          <i class="el-icon-user"></i> -->
        </div>
      </el-header>
      <el-main>
        <router-view />
      </el-main>
    </el-container>
    
    <!-- 全局加载状态指示器 -->
    <div class="global-loading-indicator" v-if="isLoading">
      <div class="loading-content">
        <i class="el-icon-loading"></i>
        <p>{{ loadingMessage }}</p>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'App',
  data() {
    return {
      activeIndex: '/data-visualization',
      isDarkTheme: false,
      isLoading: false,
      loadingMessage: '加载中...'
    }
  },
  methods: {
    toggleTheme(value) {
      this.isDarkTheme = value;
      // 使用Element Plus的暗色模式
      document.documentElement.setAttribute('data-theme', value ? 'dark' : '');
      localStorage.setItem('webgis_theme', value ? 'dark' : 'light');
      
      // 触发自定义事件通知其他组件主题已变化
      window.dispatchEvent(new CustomEvent('themechange', { detail: { isDark: value } }));
    },
    
    // 显示全局加载
    showLoading(message = '加载中...') {
      this.loadingMessage = message;
      this.isLoading = true;
    },
    
    // 隐藏全局加载
    hideLoading() {
      this.isLoading = false;
    }
  },
  mounted() {
    // 从本地存储加载主题设置
    const savedTheme = localStorage.getItem('webgis_theme');
    if (savedTheme) {
      this.isDarkTheme = savedTheme === 'dark';
      // 设置Element Plus主题
      document.documentElement.setAttribute('data-theme', this.isDarkTheme ? 'dark' : '');
    }
    
    // 设置初始化路由
    this.activeIndex = this.$route.path;
    
    // 创建全局事件总线，让所有组件可以调用加载状态指示器
    this.$root.$on('show-loading', this.showLoading);
    this.$root.$on('hide-loading', this.hideLoading);
  },
  beforeDestroy() {
    // 移除事件监听
    this.$root.$off('show-loading', this.showLoading);
    this.$root.$off('hide-loading', this.hideLoading);
  }
}
</script>

<style>
/* 全局样式 */
html, body {
  margin: 0;
  padding: 0;
  height: 100%;
  width: 100%;
  font-family: "Helvetica Neue", Helvetica, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", Arial, sans-serif;
}

#app {
  height: 100%;
  width: 100%;
}

/* 定义CSS变量用于亮色模式 */
:root {
  --primary-bg: #ffffff;
  --secondary-bg: #f5f7fa;
  --primary-text: #303133;
  --secondary-text: #606266;
  --border-color: #e4e7ed;
  --shadow-color: rgba(0, 0, 0, 0.1);
  --header-bg: #ffffff;
  --tool-bg: #f5f7fa;
  --card-bg: #ffffff;
  --component-bg: #f5f7fa;
  --map-control-bg: rgba(255, 255, 255, 0.85);
  transition: all 0.3s;
  --collapse-width: 500px;
}

/* 暗色主题变量 */
html[data-theme='dark'] {
  --primary-bg: rgba(30, 30, 30, 0.9);
  --secondary-bg: rgba(30, 30, 30, 0.9);
  --primary-text: #eee;
  --secondary-text: #bbb;
  --border-color: #425164;
  --shadow-color: rgba(0, 0, 0, 0.3);
  --header-bg: rgba(30, 30, 30, 0.9);
  --tool-bg: rgba(30, 30, 30, 0.9);
  --card-bg: rgba(30, 30, 30, 0.9);
  --component-bg: rgba(30, 30, 30, 0.9);
  --map-control-bg: rgba(30, 30, 30, 0.9);
}

.main-container {
  height: 100%;
  width: 100%;
}

.header-logo {
  display: flex;
  align-items: center;
}

.logo-icon {
  font-size: 24px;
  margin-right: 10px;
  color: #409EFF;
}

.logo-text {
  font-size: 18px;
  font-weight: bold;
}

.header-menu {
  flex: 1;
  margin-left: 50px;
}

.user-info {
  display: flex;
  align-items: center;
  margin-left: 20px;
}

.username {
  margin: 0 10px;
  color: var(--primary-text);
}

.user-info i {
  margin-left: 8px;
  font-size: 20px;
  color: var(--primary-text);
}

.el-header {
  display: flex;
  align-items: center;
  background-color: var(--header-bg);
  color: var(--primary-text);
  box-shadow: 0 2px 12px 0 var(--shadow-color);
  padding: 0 20px;
  z-index: 100;
}

.el-aside {
  background-color: var(--tool-bg);
}

.el-main {
  padding: 0!important;
  position: relative;
  background-color: var(--primary-bg);
  color: var(--primary-text);
}

/* 折叠按钮全局样式 */
.toggle-tools-panel {
  position: fixed;
  top: 50%;
  right: var(--collapse-width, 400px);
  transform: translateY(-50%);
  width: 20px;
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  z-index: 100;
  border-radius: 4px 0 0 4px;
  box-shadow: -2px 0 5px var(--shadow-color);
  background-color: var(--secondary-bg);
  color: var(--primary-text);
  transition: right 0.3s cubic-bezier(0.23, 1, 0.32, 1);
}

.toggle-tools-panel:hover {
  background-color: var(--card-bg);
}

.tools-hidden .toggle-tools-panel {
  right: 0;
}

.tools-aside {
  position: fixed !important;
  height: calc(100% - 60px) !important; /* 减去header高度 */
  right: 0 !important;
  top: 60px !important; /* header高度 */
  width: var(--collapse-width, 400px) !important;
  background-color: var(--tool-bg);
  box-shadow: -2px 0 10px var(--shadow-color);
  z-index: 50 !important;
  overflow-y: auto;
  transition: transform 0.3s cubic-bezier(0.23, 1, 0.32, 1);
}

.tools-hidden .chart-row,
.tools-hidden .chart-card,
.tools-hidden .analysis-info-card {
  width: calc(100% - 20px) !important;
}

/* 全局加载状态指示器 */
.global-loading-indicator {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 9999;
  backdrop-filter: blur(3px);
}

.loading-content {
  background-color: var(--card-bg);
  border-radius: 8px;
  padding: 30px;
  text-align: center;
  box-shadow: 0 4px 16px var(--shadow-color);
  animation: fadeIn 0.3s;
}

.loading-content i {
  font-size: 48px;
  color: #409EFF;
  margin-bottom: 15px;
}

.loading-content p {
  font-size: 16px;
  color: var(--primary-text);
  margin: 0;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(-20px); }
  to { opacity: 1; transform: translateY(0); }
}

/* 卡片样式 */
.el-card {
  background-color: var(--card-bg);
  color: var(--primary-text);
  border-color: var(--border-color);
  transition: all 0.3s;
}

.el-card__header {
  border-bottom-color: var(--border-color);
}

/* 工具面板中的卡片 */
.tools-aside .el-card {
  background-color: var(--card-bg);
  margin-bottom: 10px;
}

/* 地图控件样式 */
.map-main .el-card,
.map-header-controls,
.map-controls,
.map-legend,
.map-tools {
  background-color: var(--map-control-bg);
  backdrop-filter: blur(5px);
}

/* 输入框和按钮样式 */
.el-input__inner,
.el-textarea__inner,
.el-input-number__decrease, 
.el-input-number__increase {
  background-color: var(--secondary-bg);
  color: var(--primary-text);
  border-color: var(--border-color);
}

.el-select-dropdown {
  background-color: var(--secondary-bg);
  border-color: var(--border-color);
}

.el-select-dropdown__item {
  color: var(--primary-text);
}

.el-select-dropdown__item.hover, 
.el-select-dropdown__item:hover {
  background-color: var(--primary-bg);
}

/* 表格样式 */
.el-table {
  background-color: var(--card-bg);
  color: var(--primary-text);
}

.el-table th,
.el-table tr,
.el-table td {
  background-color: var(--card-bg);
  color: var(--primary-text);
  border-bottom-color: var(--border-color);
}

.el-table--striped .el-table__body tr.el-table__row--striped td {
  background-color: var(--secondary-bg);
}

.el-table--enable-row-hover .el-table__body tr:hover > td {
  background-color: var(--secondary-bg);
}

/* 地图和图表容器 */
.map-container {
  background-color: var(--primary-bg);
}

/* ElementUI深色模式样式覆盖 */
.dark .el-select-dropdown {
  background-color: var(--component-bg);
  border-color: var(--border-color);
}

.dark .el-select-dropdown__item {
  color: var(--primary-text);
}

.dark .el-select-dropdown__item.hover, 
.dark .el-select-dropdown__item:hover {
  background-color: var(--secondary-bg);
}

.dark .el-tabs__item {
  color: var(--secondary-text);
}

.dark .el-tabs__item.is-active {
  color: #409EFF;
}

.dark .el-tabs__nav-wrap::after {
  background-color: var(--border-color);
}

.dark .el-tree {
  background-color: transparent;
  color: var(--primary-text);
}

.dark .el-tabs__content {
  color: var(--primary-text);
}

.dark .el-radio-button__inner {
  background-color: var(--component-bg);
  border-color: var(--border-color);
  color: var(--primary-text);
}

.dark .el-date-table td.available:hover {
  color: #409EFF;
}

.dark .el-date-table td.current:not(.disabled) {
  color: #fff;
  background-color: #409EFF;
}

/* 工具面板折叠动画 */
@keyframes slideIn {
  from { transform: translateX(100%); }
  to { transform: translateX(0); }
}

@keyframes slideOut {
  from { transform: translateX(0); }
  to { transform: translateX(100%); }
}

.el-tabs__nav-next, .el-tabs__nav-prev{
  line-height: 39px;
  padding-left: 4px;
  padding-right: 4px;
}

</style>