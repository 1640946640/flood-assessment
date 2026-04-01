<template>
  <div class="chart-container" ref="chartContainer">
    <div class="chart-toolbar" v-if="showToolbar">
      <el-button-group>
        <el-button size="mini" icon="el-icon-refresh" @click="refreshChart" title="刷新图表"></el-button>
        <el-button size="mini" icon="el-icon-download" @click="downloadChart" title="导出图表"></el-button>
        <el-button size="mini" icon="el-icon-setting" @click="showChartOptions = true" title="图表配置"></el-button>
        <el-button size="mini" icon="el-icon-data-analysis" @click="toggleDataView" title="数据视图"></el-button>
      </el-button-group>
    </div>
    <div ref="chart" class="chart"></div>
    <div v-if="showData" class="chart-data-view">
      <div class="data-view-header">
        <h4>图表数据</h4>
        <el-button size="mini" icon="el-icon-close" @click="showData = false" circle></el-button>
      </div>
      <el-table :data="tableData" size="mini" style="width: 100%" max-height="250px">
        <el-table-column v-for="(col, index) in tableColumns" :key="index" :prop="col.prop" :label="col.label"></el-table-column>
      </el-table>
    </div>
    
    <el-dialog title="图表配置" :visible.sync="showChartOptions" width="500px" append-to-body custom-class="chart-options-dialog">
      <el-form label-position="top" size="small">
        <el-form-item label="标题">
          <el-input v-model="chartSettings.title"></el-input>
        </el-form-item>
        <el-form-item label="主题">
          <el-select v-model="chartSettings.theme" style="width: 100%">
            <el-option label="默认" value="default"></el-option>
            <el-option label="亮色" value="light"></el-option>
            <el-option label="暗色" value="dark"></el-option>
            <el-option label="蓝莓" value="blue"></el-option>
            <el-option label="绿意" value="green"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="图例位置">
          <el-select v-model="chartSettings.legendPosition" style="width: 100%">
            <el-option label="顶部" value="top"></el-option>
            <el-option label="底部" value="bottom"></el-option>
            <el-option label="左侧" value="left"></el-option>
            <el-option label="右侧" value="right"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="动画效果">
          <el-switch v-model="chartSettings.animation"></el-switch>
        </el-form-item>
      </el-form>
      <span slot="footer" class="dialog-footer">
        <el-button @click="showChartOptions = false">取消</el-button>
        <el-button type="primary" @click="applyChartSettings">应用</el-button>
      </span>
    </el-dialog>
  </div>
</template>

<script>
import * as echarts from 'echarts';

export default {
  name: 'ChartView',
  props: {
    chartType: {
      type: String,
      default: 'bar',
      validator: type => ['bar', 'line', 'pie', 'scatter', 'radar', 'heatmap'].includes(type)
    },
    chartTitle: {
      type: String,
      default: '数据统计'
    },
    chartData: {
      type: Object,
      required: true
    },
    chartOptions: {
      type: Object,
      default: () => ({})
    },
    showToolbar: {
      type: Boolean,
      default: true
    }
  },
  data() {
    return {
      chart: null,
      showData: false,
      showChartOptions: false,
      chartSettings: {
        title: this.chartTitle,
        theme: 'default',
        legendPosition: 'right',
        animation: true
      },
      tableData: [],
      tableColumns: [],
      isDarkMode: false
    }
  },
  mounted() {
    this.checkDarkMode();
    this.initChart();
    
    // 监听主题变化
    window.addEventListener('themechange', this.checkDarkMode);
  },
  beforeDestroy() {
    // 移除事件监听和销毁图表
    window.removeEventListener('resize', this.resizeChart);
    window.removeEventListener('themechange', this.checkDarkMode);
    if (this.chart) {
      this.chart.dispose();
    }
  },
  watch: {
    chartData: {
      handler() {
        this.updateChart();
        this.prepareTableData();
      },
      deep: true
    },
    chartOptions: {
      handler() {
        this.updateChart();
      },
      deep: true
    },
    chartType() {
      this.initChart();
    },
    chartTitle: {
      handler(val) {
        this.chartSettings.title = val;
        this.updateChart();
      }
    },
    isDarkMode() {
      // 当暗色模式状态变化时重新初始化图表
      this.initChart();
    }
  },
  methods: {
    checkDarkMode() {
      // 检查当前是否为暗色模式
      this.isDarkMode = document.documentElement.getAttribute('data-theme') === 'dark';
    },
    
    initChart() {
      // 如果已存在图表实例，先销毁
      if (this.chart) {
        this.chart.dispose();
      }
      
      // 初始化echarts实例，自动应用当前主题
      const theme = this.isDarkMode ? 'dark' : this.chartSettings.theme;
      this.chart = echarts.init(this.$refs.chart, theme);
      this.updateChart();
      this.prepareTableData();
      
      // 响应窗口大小变化
      window.addEventListener('resize', this.resizeChart);
      
      // 添加图表交互事件
      this.chart.on('click', this.handleChartClick);
    },
    
    updateChart() {
      if (!this.chart) return;
      
      const { xAxis, yAxis, series } = this.chartData;
      let options = {
        title: {
          text: this.chartSettings.title
        },
        tooltip: {
          trigger: 'axis'
        },
        grid: {
          left: '3%',
          right: '4%',
          bottom: '3%',
          containLabel: true
        },
        legend: {
          orient: this.chartSettings.legendPosition === 'left' || this.chartSettings.legendPosition === 'right' ? 'vertical' : 'horizontal',
          left: this.chartSettings.legendPosition === 'left' ? 'left' : this.chartSettings.legendPosition === 'right' ? 'right' : 'center',
          top: this.chartSettings.legendPosition === 'top' ? 'top' : this.chartSettings.legendPosition === 'bottom' ? 'bottom' : 'middle'
        },
        animation: this.chartSettings.animation,
        ...this.chartOptions
      };
      
      // 根据不同图表类型设置不同配置
      switch (this.chartType) {
        case 'bar':
        case 'line':
          options = {
            ...options,
            xAxis: {
              type: 'category',
              data: xAxis
            },
            yAxis: {
              type: 'value'
            },
            series: series.map(item => ({
              ...item,
              type: this.chartType
            }))
          };
          break;
        case 'pie':
          options = {
            ...options,
            series: [{
              type: 'pie',
              radius: '60%',
              data: series,
              emphasis: {
                itemStyle: {
                  shadowBlur: 10,
                  shadowOffsetX: 0,
                  shadowColor: 'rgba(0, 0, 0, 0.5)'
                }
              }
            }]
          };
          break;
        case 'scatter':
          options = {
            ...options,
            xAxis: {
              type: 'value'
            },
            yAxis: {
              type: 'value'
            },
            series: series.map(item => ({
              ...item,
              type: 'scatter'
            }))
          };
          break;
        case 'radar':
          options = {
            ...options,
            radar: {
              indicator: yAxis.map(item => ({ name: item, max: 100 }))
            },
            series: [{
              type: 'radar',
              data: series
            }]
          };
          break;
        case 'heatmap':
          options = {
            ...options,
            xAxis: {
              type: 'category',
              data: xAxis
            },
            yAxis: {
              type: 'category',
              data: yAxis
            },
            visualMap: {
              min: 0,
              max: 10,
              calculable: true,
              orient: 'horizontal',
              left: 'center',
              bottom: '15%'
            },
            series: [{
              type: 'heatmap',
              data: series,
              label: {
                show: true
              },
              emphasis: {
                itemStyle: {
                  shadowBlur: 10,
                  shadowColor: 'rgba(0, 0, 0, 0.5)'
                }
              }
            }]
          };
          break;
      }
      
      // 设置主题相关颜色
      if (this.isDarkMode) {
        // 为暗色模式设置文本颜色
        options.textStyle = { color: '#eee' };
        options.title.textStyle = { color: '#eee' };
        options.legend.textStyle = { color: '#eee' };
        if (options.xAxis) options.xAxis.axisLabel = { color: '#bbb' };
        if (options.yAxis) options.yAxis.axisLabel = { color: '#bbb' };
      }
      
      this.chart.setOption(options);
    },
    
    // 准备表格数据
    prepareTableData() {
      const { xAxis, series } = this.chartData;
      
      // 针对不同图表类型准备表格数据
      if (this.chartType === 'bar' || this.chartType === 'line') {
        this.tableColumns = [
          { prop: 'category', label: '类别' }
        ];
        
        // 添加每个系列的列
        series.forEach(item => {
          this.tableColumns.push({ prop: item.name, label: item.name });
        });
        
        // 准备行数据
        this.tableData = xAxis.map((category, index) => {
          const row = { category };
          series.forEach(item => {
            row[item.name] = item.data[index];
          });
          return row;
        });
      } else if (this.chartType === 'pie') {
        this.tableColumns = [
          { prop: 'name', label: '名称' },
          { prop: 'value', label: '数值' }
        ];
        
        this.tableData = series;
      }
    },
    
    // 处理图表点击事件
    handleChartClick(params) {
      this.$emit('chart-click', params);
    },
    
    // 刷新图表
    refreshChart() {
      this.updateChart();
      this.$emit('refresh-chart');
    },
    
    // 下载图表
    downloadChart() {
      const url = this.chart.getDataURL();
      const a = document.createElement('a');
      a.href = url;
      a.download = `${this.chartSettings.title || '图表'}.png`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    },
    
    // 切换数据视图
    toggleDataView() {
      this.showData = !this.showData;
    },
    
    // 应用图表设置
    applyChartSettings() {
      this.updateChart();
      this.showChartOptions = false;
    },
    
    resizeChart() {
      this.chart && this.chart.resize();
    }
  }
}
</script>

<style scoped>
.chart-container {
  width: 100%;
  height: 100%;
  min-height: 300px;
  position: relative;
}

.chart {
  width: 100%;
  height: 100%;
}

.chart-toolbar {
  position: absolute;
  top: 10px;
  right: 10px;
  z-index: 3;
  background-color: var(--secondary-bg);
  border-radius: 4px;
  padding: 3px 5px;
  box-shadow: 0 2px 8px 0 var(--shadow-color);
  transition: all 0.3s;
  opacity: 0.6;
}

.chart-toolbar:hover {
  opacity: 1;
}

.chart-data-view {
  position: absolute;
  bottom: 0;
  left: 0;
  width: 100%;
  max-height: 300px;
  background-color: var(--card-bg);
  border-top: 1px solid var(--border-color);
  padding: 10px;
  box-shadow: 0 -2px 10px 0 var(--shadow-color);
  z-index: 2;
  transition: all 0.3s cubic-bezier(0.23, 1, 0.32, 1);
}

.data-view-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.data-view-header h4 {
  margin: 0;
}

.chart-options-dialog {
  background-color: var(--card-bg);
  color: var(--primary-text);
}

.chart-container :deep(.el-table) {
  color: var(--primary-text);
  background-color: var(--card-bg);
}

.chart-container :deep(.el-table th),
.chart-container :deep(.el-table tr),
.chart-container :deep(.el-table td) {
  background-color: var(--card-bg);
  color: var(--primary-text);
  border-bottom-color: var(--border-color);
}

.chart-container :deep(.el-table--striped .el-table__body tr.el-table__row--striped td) {
  background-color: var(--secondary-bg);
}
</style> 