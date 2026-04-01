/**
 * 工具面板控制的混入，提供统一的工具面板折叠/展开动画效果
 */
export default {
  data() {
    return {
      showTools: true, // 控制工具面板的显示隐藏
      panelAnimating: false, // 是否正在动画中
    };
  },
  methods: {
    /**
     * 切换工具面板显示/隐藏
     */
    toggleTools() {
      if (this.panelAnimating) return;
      
      const toolsAside = document.querySelector('.tools-aside');
      const toggleButton = document.querySelector('.toggle-tools-panel');
      if (!toolsAside || !toggleButton) return;
      
      this.panelAnimating = true;
      
      // 定义共同的过渡属性
      const transition = 'transform 0.3s cubic-bezier(0.23, 1, 0.32, 1), right 0.3s cubic-bezier(0.23, 1, 0.32, 1)';
      
      if (this.showTools) {
        // 准备隐藏：先移出页面，再隐藏
        // 同步移动工具面板和折叠按钮
        toolsAside.style.transform = 'translateX(100%)';
        toolsAside.style.transition = transition;
        
        // 同时移动折叠按钮到右侧边缘
        toggleButton.style.right = '0px';
        toggleButton.style.transition = transition;
        
        // 动画结束后设置为不显示
        setTimeout(() => {
          this.showTools = false;
          this.panelAnimating = false;
          // 只清除transition，保留transform和right位置
          toolsAside.style.transition = '';
          toggleButton.style.transition = '';
        }, 300);
      } else {
        // 准备显示：先显示元素，再移入页面
        this.showTools = true;
        
        // 确保DOM已更新
        this.$nextTick(() => {
          // 先设置为隐藏状态（位于屏幕外）
          toolsAside.style.transform = 'translateX(100%)';
          
          // 强制浏览器重排
          void toolsAside.offsetWidth;
          
          // 添加过渡动画并同步移入工具面板和折叠按钮
          toolsAside.style.transition = transition;
          toolsAside.style.transform = 'translateX(0)';
          
          // 同时移动折叠按钮到工具面板边缘
          // 动态获取CSS变量--collapse-width的值
          const collapseWidth = getComputedStyle(document.documentElement).getPropertyValue('--collapse-width').trim() || '400px';
          toggleButton.style.right = collapseWidth;
          toggleButton.style.transition = transition;
          
          // 动画结束后清除动画
          setTimeout(() => {
            this.panelAnimating = false;
            // 只清除transition，保留transform和right位置
            toolsAside.style.transition = '';
            toggleButton.style.transition = '';
          }, 300);
        });
      }
    }
  }
};