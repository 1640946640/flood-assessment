<template>
  <el-container class="auxiliary-layout">
    <el-aside width="200px" class="menu-aside">
      <el-menu
        :default-active="activeMenu"
        class="auxiliary-menu"
        router>
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
        <!-- <el-menu-item index="/auxiliary/flood-points">
          <i class="el-icon-location-information"></i>
          <span>易涝点计算</span>
        </el-menu-item> -->
        <!-- 可以在这里添加更多辅助功能菜单项 -->
      </el-menu>
    </el-aside>
    <el-main class="content-main">
      <router-view></router-view>
    </el-main>
  </el-container>
</template>

<script>
export default {
  name: 'AuxiliaryLayout',
  computed: {
    activeMenu() {
      return this.$route.path
    }
  }
}
</script>

<style scoped>
.auxiliary-layout {
  height: 100%;
}

.menu-aside {
  background-color: #fff;
  border-right: 1px solid #e6e6e6;
}

.auxiliary-menu {
  height: 100%;
}

.content-main {
  padding: 0;
  height: 100%;
}
</style>