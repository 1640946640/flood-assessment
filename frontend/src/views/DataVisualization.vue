<template>
  <div class="data-visualization">
    <el-container class="main-container" :class="{ 'tools-hidden': !showTools }">
      <el-main class="map-main">
        <MapView 
          ref="mapView" 
          @map-initialized="handleMapInitialized" 
          @layer-added="handleLayerAdded"
          @layer-error="handleLayerError"
          @layer-exists="handleLayerExists" />
      </el-main>
      
      <!-- 工具面板折叠按钮 -->
      <div class="toggle-tools-panel" @click="toggleTools">
        <i :class="showTools ? 'el-icon-arrow-right' : 'el-icon-arrow-left'"></i>
      </div>
      
      <el-aside class="tools-aside" v-show="showTools">
        <div class="tools-container">
          <!-- <el-card class="data-card">
            <div slot="header">
              <span>数据集</span>
              <el-button style="float: right; padding: 3px 0" type="text" @click="refreshDatasets">刷新</el-button>
            </div>
            <div class="data-list">
              <el-tree
                :data="hierarchicalDatasets"
                node-key="id"
                :props="{ label: 'name', children: 'children' }"
                @node-click="handleDatasetSelect"
                :expand-on-click-node="false">
                <span class="custom-tree-node" slot-scope="{ node, data }">
                  <span>
                    <i v-if="data.isFolder" class="el-icon-folder" style="margin-right: 5px;"></i>
                    <i v-else-if="data.format === 'csv'" class="el-icon-document-copy" style="margin-right: 5px; color: #67c23a;"></i>
                    <i v-else-if="data.format === 'xls' || data.format === 'xlsx'" class="el-icon-document" style="margin-right: 5px; color: #409eff;"></i>
                    <i v-else-if="data.type === 'vector'" class="el-icon-map-location" style="margin-right: 5px;"></i>
                    <i v-else-if="data.type === 'raster'" class="el-icon-picture" style="margin-right: 5px;"></i>
                    <i v-else class="el-icon-document" style="margin-right: 5px;"></i>
                    {{ node.label }}
                    <span v-if="data.format" class="dataset-format">({{ data.format }})</span>
                    <span v-if="data.subtype === 'table'" class="table-indicator">表格数据</span>
                  </span>
                </span>
              </el-tree>
            </div>
          </el-card> -->
          
          <dataset-selector ref="datasetSelector" @load-dataset="loadDatasetToMap" />
          <img-selector ref="imgSelector" path="total" />
        </div>
      </el-aside>
    </el-container>
  </div>
</template>

<script>
import { mapGetters, mapActions } from 'vuex';
import MapView from '@/components/MapView.vue';
import ChartView from '@/components/ChartView.vue';
import ToolsPanelMixin from '@/mixins/ToolsPanelMixin';
import axios from 'axios';
import DatasetSelector from '../components/DatasetSelector.vue';
import ImgSelector from '../components/ImgSelector.vue';

export default {
  name: 'DataVisualization',
  components: {
    MapView,
    ChartView,
    DatasetSelector,
    ImgSelector
  },
  mixins: [ToolsPanelMixin],
  data() {
    return {
      datasetTab: 'vector',
      selectedDataset: null,
      selectedFields: [],
      availableFields: [],
      selectedChartType: 'bar',
      showChart: false,
      chartTitle: '数据统计',
      chartData: {
        xAxis: [],
        yAxis: [],
        series: []
      },
      map: null,
      statisticsData: [],
      showTools: true, // 控制工具面板的显示隐藏
      loading: {
        datasets: false,
        fields: false,
        statistics: false,
        chart: false
      },
      // 记录已加载的表格数据
      loadedTableDatasets: [],
      apiBaseUrl: process.env.VUE_APP_API_URL || 'http://localhost:5000' // API基础URL
    }
  },
  computed: {
    hierarchicalDatasets() {
      // 处理后端返回的数据，确保是数组格式
      const datasets = this.$store.state.datasets;
      if (!datasets) return [];
      
      // 如果datasets是字符串，尝试解析JSON
      if (typeof datasets === 'string') {
        try {
          return JSON.parse(datasets);
        } catch (error) {
          console.error('解析数据集JSON失败:', error);
          return [];
        }
      }
      
      // 如果已经是数组，直接返回
      return Array.isArray(datasets) ? datasets : [];
    },
    canGenerateChart() {
      return this.selectedDataset && this.selectedFields.length > 0;
    }
  },
  mounted() {
    document.documentElement.style.setProperty('--collapse-width', '400px');
    this.fetchDatasets();
  },
  methods: {
    // 从后端获取数据集列表
    fetchDatasets() {
      this.loading.datasets = true;
      
      // 使用axios直接请求后端API
      axios.get(`/api/datasets`)
        .then(response => {
          console.log('response', response);
          // 确保数据是正确的格式
          let datasets = response.data;
          
          // 如果是字符串，尝试解析JSON
          if (typeof datasets === 'string') {
            try {
              datasets = JSON.parse(datasets);
            } catch (error) {
              console.error('解析数据集JSON失败:', error);
              this.$message.warning('数据格式异常，尝试修复');
            }
          }
          
          // 将数据集存储到Vuex
          this.$store.commit('SET_DATASETS', datasets);
          this.loading.datasets = false;
        })
        .catch(error => {
          console.error('获取数据集失败:', error);
          this.$message.error('获取数据集失败，请稍后重试');
          this.loading.datasets = false;
        });
    },
    
    refreshDatasets() {
      this.fetchDatasets();
    },
    
    handleMapInitialized(map) {
      this.map = map;
    },
    
    handleDatasetSelect(dataset) {
      // 如果是文件夹，加载文件夹下所有数据
      if (dataset.isFolder || dataset.type === 'folder') {
        this.$message.info(`正在加载文件夹: ${dataset.name}`);
        
        // 递归函数，用于加载文件夹中的所有数据集
        const loadFolderDatasets = (items) => {
          if (!items || !Array.isArray(items)) return;
          
          for (const item of items) {
            if (item.isFolder || item.type === 'folder') {
              // 如果是文件夹，递归加载其子项
              if (item.children && Array.isArray(item.children) && item.children.length > 0) {
                loadFolderDatasets(item.children);
              }
            } else {
              // 如果是数据集，加载到地图上
              this.loadDatasetToMap(item);
            }
          }
        };
        
        // 开始加载文件夹中的所有数据集
        if (dataset.children && Array.isArray(dataset.children) && dataset.children.length > 0) {
          loadFolderDatasets(dataset.children);
        }
        
        return;
      }
      
      // 如果是单个数据集，正常处理
      this.selectedDataset = dataset;
      this.selectedFields = [];
      this.showChart = false;
      
      // 加载数据集到地图
      this.loadDatasetToMap(dataset);
    },
    
    // 将数据集加载到地图上的方法
    loadDatasetToMap(dataset) {
      // 检查数据集对象是否有效
      if (!dataset || !dataset.id) {
        console.error('无效的数据集对象:', dataset);
        this.$message.error('无效的数据集对象，无法加载');
        return;
      }
      
      // 设置当前选中的数据集，无论何种类型都更新
      this.selectedDataset = dataset;
      this.selectedFields = [];
      this.showChart = false;
      
      // 对于表格类型数据（CSV、Excel），只加载字段信息而不尝试加载到地图上
      if (dataset.subtype === 'table' || 
          (dataset.format && ['csv', 'xls', 'xlsx'].includes(dataset.format.toLowerCase()))) {
        console.log(`加载表格数据: ${dataset.name} (${dataset.format})`);
        this.loadVectorFields(dataset);
        
        // 使用替代方法添加表格数据到图层管理器
        this.addTableLayerToMap(dataset);
        
        this.$message.info(`已加载表格数据: ${dataset.name}，可进行统计分析`);
        return;
      }
      
      // 根据数据集类型载入不同字段
      if (dataset.type === 'vector') {
        // 加载矢量数据字段
        this.loadVectorFields(dataset);
        
        // 在地图上显示该图层
        try {
          const baseUrl = this.apiBaseUrl || '';
          const layerUrl = `${baseUrl}/api/datasets/${dataset.id}/geojson`;
          this.$refs.mapView.addVectorLayer({
            id: dataset.id,
            url: layerUrl,
            name: dataset.name || '未命名图层',
            format: dataset.format || 'geojson'
          });
        } catch (error) {
          console.error('加载矢量图层失败:', error);
          this.$message.error(`无法加载矢量图层 ${dataset.name || dataset.id}，请稍后重试`);
        }
      } else if (dataset.type === 'raster') {
        // 加载栅格数据字段
        this.loadRasterFields(dataset);
        
        // 在地图上显示该图层
        try {
          const baseUrl = this.apiBaseUrl || '';
          const layerUrl = `${baseUrl}/api/datasets/${dataset.id}/image`;
          this.$refs.mapView.addRasterLayer({
            id: dataset.id,
            url: layerUrl,
            name: dataset.name || '未命名图层',
            format: dataset.format || 'tif'
          });
        } catch (error) {
          console.error('加载栅格图层失败:', error);
          this.$message.error(`无法加载栅格图层 ${dataset.name || dataset.id}，请稍后重试`);
        }
      } else {
        console.warn('未知的数据集类型:', dataset.type);
        this.$message.warning(`未知的数据集类型: ${dataset.type || '未指定'}`);
      }
    },
    
    handleLayerAdded(layer) {
      console.log('Layer added:', layer);
      this.$message.success(`成功加载图层: ${layer.name || layer.id}`);
    },
    
    handleLayerError(error) {
      console.error('Layer error:', error);
      this.$message.error(`图层加载失败: ${error.message}`);
    },
    
    // 加载矢量数据字段
    loadVectorFields(dataset) {
      this.loading.fields = true;
      
      // 如果数据集中已包含字段信息，直接使用
      if (dataset.fields && dataset.fields.length > 0) {
        this.processFieldsData(dataset.fields);
        this.generateStatistics(dataset.id);
        return;
      }
      
      // 否则从API获取字段信息
      axios.get(`/api/datasets/${dataset.id}/fields`)
        .then(response => {
          this.processFieldsData(response.data);
          this.generateStatistics(dataset.id);
        })
        .catch(error => {
          console.error('获取字段信息失败:', error);
          this.$message.warning('无法获取字段信息，使用默认设置');
          
          // 使用数据集返回的属性构建字段列表
          if (dataset.properties && dataset.properties.fields) {
            const fields = dataset.properties.fields.map(field => ({
              name: field,
              type: this.guessFieldType(field)
            }));
            this.processFieldsData(fields);
          } else {
            // 如果没有字段信息，使用默认字段
            this.processFieldsData([
              { name: 'id', type: 'integer' },
              { name: 'name', type: 'string' },
              { name: 'value', type: 'float' }
            ]);
          }
          this.generateStatistics(dataset.id);
        });
    },
    
    // 加载栅格数据字段
    loadRasterFields(dataset) {
      this.loading.fields = true;
      
      // 栅格数据的字段通常更简单
      const defaultFields = [
        { name: 'value', type: 'float' },
        { name: 'class', type: 'integer' }
      ];
      
      // 如果数据集包含波段信息，为每个波段创建字段
      if (dataset.properties && dataset.properties.bands) {
        const bandFields = [];
        for (let i = 1; i <= dataset.properties.bands; i++) {
          bandFields.push({ name: `band_${i}`, type: 'float' });
        }
        this.processFieldsData(bandFields.length > 0 ? bandFields : defaultFields);
      } else {
        this.processFieldsData(defaultFields);
      }
      
      this.generateStatistics(dataset.id);
    },
    
    // 处理字段数据
    processFieldsData(fieldsData) {
      this.availableFields = fieldsData;
      this.loading.fields = false;
    },
    
    // 根据字段名猜测类型
    guessFieldType(fieldName) {
      const lowerName = fieldName.toLowerCase();
      if (lowerName.includes('id') || lowerName.includes('count') || lowerName.includes('num')) {
        return 'integer';
      } else if (lowerName.includes('name') || lowerName.includes('type') || lowerName.includes('code')) {
        return 'string';
      } else if (lowerName.includes('value') || lowerName.includes('area') || lowerName.includes('dist')) {
        return 'float';
      } else {
        return 'string'; // 默认为字符串类型
      }
    },
    
    // 生成统计数据
    generateStatistics(datasetId) {
      this.loading.statistics = true;
      
      axios.get(`/api/datasets/${datasetId}/statistics`)
        .then(response => {
          console.log('response', response);
          this.statisticsData = response.data.stats;
          this.loading.statistics = false;
        })
        .catch(error => {
          console.error('获取统计信息失败:', error);
          
          // 生成基于字段的模拟统计数据
          this.generateMockStatistics();
          this.loading.statistics = false;
        });
    },
    
    // 生成模拟统计数据（当API调用失败时使用）
    generateMockStatistics() {
      this.statisticsData = this.availableFields.map(field => {
        if (field.type === 'string') {
          return {
            field: field.name,
            type: field.type,
            min: '-',
            max: '-',
            avg: '-',
            count: Math.floor(Math.random() * 100) + 50
          };
        } else {
          const min = Math.floor(Math.random() * 100);
          const max = min + Math.floor(Math.random() * 900);
          return {
            field: field.name,
            type: field.type,
            min: min,
            max: max,
            avg: Math.floor((min + max) / 2),
            count: Math.floor(Math.random() * 100) + 50
          };
        }
      });
    },
    
    // 生成图表
    generateChart() {
      if (!this.canGenerateChart) return;
      
      this.loading.chart = true;
      
      axios.post(`/api/datasets/chart-data`, {
        datasetId: this.selectedDataset.id,
        fields: this.selectedFields,
        chartType: this.selectedChartType
      })
      .then(response => {
        this.chartData = response.data;
        this.showChart = true;
        this.chartTitle = `${this.selectedDataset.name} 数据统计`;
        this.loading.chart = false;
      })
      .catch(error => {
        console.error('获取图表数据失败:', error);
        // 生成模拟图表数据
        this.generateMockChartData();
        this.loading.chart = false;
      });
    },
    
    // 生成模拟图表数据（当API调用失败时使用）
    generateMockChartData() {
      const fieldCount = this.selectedFields.length;
      
      if (this.selectedChartType === 'pie') {
        // 饼图数据
        this.chartData = {
          series: this.selectedFields.map(field => {
            return {
              name: field,
              value: Math.floor(Math.random() * 1000)
            };
          })
        };
      } else if (this.selectedChartType === 'radar') {
        // 雷达图数据
        this.chartData = {
          yAxis: this.selectedFields.map(field => {
            return { name: field, max: 100 };
          }),
          series: [
            {
              name: '指标值',
              value: this.selectedFields.map(() => Math.floor(Math.random() * 100))
            }
          ]
        };
      } else if (this.selectedChartType === 'heatmap') {
        // 热力图数据
        const xCategories = ['类别1', '类别2', '类别3', '类别4', '类别5'];
        const yCategories = this.selectedFields;
        const data = [];
        
        for (let i = 0; i < yCategories.length; i++) {
          for (let j = 0; j < xCategories.length; j++) {
            data.push([j, i, Math.floor(Math.random() * 10)]);
          }
        }
        
        this.chartData = {
          xAxis: xCategories,
          yAxis: yCategories,
          series: data
        };
      } else {
        // 柱状图、折线图、散点图数据
        const categories = ['区域1', '区域2', '区域3', '区域4', '区域5', '区域6', '区域7'];
        const series = this.selectedFields.map(field => {
          return {
            name: field,
            data: categories.map(() => Math.floor(Math.random() * 1000))
          };
        });
        
        this.chartData = {
          xAxis: categories,
          series: series
        };
      }
      
      this.showChart = true;
      this.chartTitle = `${this.selectedDataset.name} 数据统计`;
    },
    
    // 添加处理图层已存在的方法
    handleLayerExists(layer) {
      console.log('Layer already exists:', layer);
      this.$message.info(`图层 "${layer.name || layer.id}" 已存在，已缩放至该图层`);
    },
    
    // 添加处理表格数据的替代方法
    addTableLayerToMap(dataset) {
      // 记录已加载的表格数据
      if (!this.loadedTableDatasets.some(item => item.id === dataset.id)) {
        this.loadedTableDatasets.push({
          id: dataset.id,
          name: dataset.name,
          type: 'table',
          format: dataset.format
        });
      }
      
      // 手动发送图层添加事件，使用一个模拟的图层对象
      this.$refs.mapView.$emit('layer-added', {
        id: dataset.id,
        type: 'table',
        name: dataset.name,
        format: dataset.format
      });
      
      // 直接更新图层树
      if (this.$refs.mapView && this.$refs.mapView.layerTree) {
        // 检查是否已存在
        const existingIndex = this.$refs.mapView.layerTree.findIndex(layer => layer.id === dataset.id);
        if (existingIndex === -1) {
          this.$refs.mapView.layerTree.push({
            id: dataset.id,
            name: dataset.name,
            type: 'table',
            format: dataset.format,
            opacity: 1
          });
        }
      }
    }
  }
}
</script>

<style scoped>
.data-visualization {
  height: 100%;
  width: 100%;
}

.main-container {
  height: 100%;
  width: 100%;
  position: relative;
}

.map-main {
  padding: 0;
  height: 100%;
}

.tools-aside {
  padding: 10px;
  height: 100%;
  transition: all 0.3s cubic-bezier(0.23, 1, 0.32, 1);
  background-color: var(--card-bg);
  box-shadow: -2px 0 10px var(--shadow-color);
  z-index: 10;
}

.tools-container {
  height: 100%;
  overflow-y: auto;
  padding-right: 10px;
}



.toggle-tools-panel:hover {
  background-color: var(--card-bg);
}

.tools-hidden .toggle-tools-panel {
  right: 0;
}



.chart-card {
  height: 300px;
}

.no-chart-placeholder, .no-data-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 200px;
  color: var(--secondary-text);
}

.no-chart-placeholder i, .no-data-placeholder i {
  font-size: 48px;
  margin-bottom: 20px;
}

.no-chart-placeholder p, .no-data-placeholder p {
  font-size: 16px;
}

/* 加载状态指示器 */
.el-loading-mask {
  background-color: rgba(255, 255, 255, 0.7);
  z-index: 10;
}

/* 动画效果 */
.el-card {
  box-shadow: 0 2px 12px 0 var(--shadow-color);
  transition: all 0.3s;
}

/* .el-card:hover {
  box-shadow: 0 4px 15px 0 var(--shadow-color);
  transform: translateY(-2px);
} */

.el-button {
  transition: all 0.3s;
}

.el-tree-node__content {
  transition: all 0.2s;
}

.el-tree-node__content:hover {
  background-color: var(--secondary-bg);
}

/* 数据列表项样式 */
.data-list .el-tree-node__content {
  transition: all 0.2s;
  color: var(--primary-text);
}

.dark .data-list .el-tree-node__content {
  background-color: var(--component-bg);
}

/* 确保图表区域在深色模式下有正确的背景色 */
.chart-card .el-card__body {
  background-color: var(--card-bg);
}

.dataset-format {
  font-size: 12px;
  color: #909399;
  margin-left: 4px;
}

.table-indicator {
  font-size: 12px;
  color: #67c23a;
  margin-left: 4px;
  background-color: rgba(103, 194, 58, 0.1);
  padding: 2px 4px;
  border-radius: 4px;
}
</style>