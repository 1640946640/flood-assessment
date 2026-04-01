<template>
  <div class="create-raster">
    <el-container class="main-container" :class="{ 'tools-hidden': !showTools }">
      <el-main class="map-main">
        <MapView ref="mapView" @map-initialized="handleMapInitialized" @layer-added="handleLayerAdded"
          @layer-error="handleLayerError" @layer-exists="handleLayerExists" />
      </el-main>

      <!-- 工具面板折叠按钮 -->
      <div class="toggle-tools-panel" @click="toggleTools">
        <i :class="showTools ? 'el-icon-arrow-right' : 'el-icon-arrow-left'"></i>
      </div>

      <el-aside class="tools-aside" v-show="showTools">
        <div class="tools-container">
          <!-- 数据集选择器 -->
          <dataset-selector ref="datasetSelector" :allowedTypes="['vector']" :selectionMode="'single'"
            @load-dataset="loadDatasetToMap" @selected-datasets-change="handleSelectedDatasetsChange"
            :showCheckbox="true" />

          <!-- 栅格模板参数配置卡片 -->
          <el-card class="raster-card" shadow="never">
            <div slot="header">
              <span>模板生成</span>
            </div>
            <div class="raster-config">
              <el-form ref="rasterForm" :model="rasterParams" label-width="100px" size="small">
                <el-form-item label="栅格分辨率">
                  <el-select v-model="rasterParams.resolution" placeholder="请选择栅格分辨率">
                    <el-option label="10米" value="10"></el-option>
                    <el-option label="30米" value="30"></el-option>
                    <el-option label="50米" value="50"></el-option>
                    <el-option label="100米" value="100"></el-option>
                    <el-option label="自定义" value="custom"></el-option>
                  </el-select>
                </el-form-item>

                <el-form-item label="自定义分辨率" v-if="rasterParams.resolution === 'custom'">
                  <el-input-number v-model="rasterParams.customResolution" :min="1" :max="1000" :step="1">
                    <template slot="append">米</template>
                  </el-input-number>
                </el-form-item>

                <el-form-item label="结果名称" prop="resultName">
                  <el-input v-model="rasterParams.resultName" placeholder="请输入结果名称"></el-input>
                </el-form-item>

                <el-form-item>
                  <el-button type="primary" @click="generateRaster" :loading="loading.generate"
                    :disabled="!canGenerateRaster">生成栅格模板</el-button>
                  <el-button @click="resetRasterParams">重置</el-button>
                </el-form-item>
              </el-form>
            </div>
          </el-card>

          <!-- 生成结果卡片 -->
          <el-card class="results-card" shadow="never" v-if="rasterResults.length > 0">
            <div slot="header">
              <span>生成结果</span>
            </div>
            <div class="results-list">
              <div v-for="result in rasterResults" :key="result.id" class="result-item">
                <div class="result-info">
                  <div class="result-name">{{ result.name }}</div>
                  <div class="result-details">
                    <span>分辨率: {{ result.properties.resolution }}米</span>
                    <span>创建时间: {{ result.createdAt }}</span>
                  </div>
                </div>
                <div class="result-actions">
                  <el-button size="mini" @click="viewRasterResult(result)">查看</el-button>
                  <el-button size="mini" @click="downloadRasterResult(result)">下载</el-button>
                </div>
              </div>
            </div>
          </el-card>
        </div>
      </el-aside>
    </el-container>
  </div>
</template>

<script>
import { mapGetters, mapActions } from 'vuex';
import MapView from '@/components/MapView.vue';
import ToolsPanelMixin from '@/mixins/ToolsPanelMixin';
import axios from 'axios';
import DatasetSelector from '@/components/DatasetSelector.vue';

export default {
  name: 'CreateGridView',
  components: {
    MapView,
    DatasetSelector
  },
  mixins: [ToolsPanelMixin],
  data() {
    return {
      selectedDataset: null,
      map: null,
      showTools: true,
      loading: {
        generate: false
      },
      rasterParams: {
        resolution: '30',
        customResolution: 30,
        resultName: '',
        sourceDataset: null
      },
      rasterResults: [],
      apiBaseUrl: process.env.VUE_APP_API_BASE_URL || 'http://localhost:5000'
    };
  },
  computed: {
    canGenerateRaster() {
      return this.rasterParams.sourceDataset && this.rasterParams.resultName.trim();
    }
  },
  mounted() {
    document.documentElement.style.setProperty('--collapse-width', '400px');
  },
  methods: {
    handleMapInitialized(map) {
      this.map = map;
    },

    handleLayerAdded(layer) {
      this.$message.success(`图层 ${layer.name} 已添加到地图`);
    },

    handleLayerError(error) {
      this.$message.error(`添加图层失败: ${error}`);
    },

    handleLayerExists(layerName) {
      this.$message.info(`图层 ${layerName} 已存在于地图中`);
    },

    loadDatasetToMap(dataset) {
      if (!dataset || !this.map) return;

      // 检查是否为面矢量数据
      if (dataset.type !== 'vector') {
        this.$message.warning('请选择面矢量数据集');
        return;
      }
      // 加载数据集到地图
      
      dataset.url = `${this.apiBaseUrl}/api/datasets/${dataset.id}/geojson`;
      this.$refs.mapView.addLayer(dataset);
    },

    handleSelectedDatasetsChange(datasets) {
      if (datasets && datasets.length > 0) {
        const dataset = datasets[0];
        console.log(dataset);
        // 检查是否为面矢量数据
        if (dataset.type !== 'vector') {
          this.$message.warning('请选择面矢量数据集');
          this.rasterParams.sourceDataset = null;
          return;
        }

        this.selectedDataset = dataset;
        this.rasterParams.sourceDataset = dataset.id;
      } else {
        this.selectedDataset = null;
        this.rasterParams.sourceDataset = null;
      }
    },

    generateRaster() {
      if (!this.canGenerateRaster) {
        this.$message.warning('请选择数据集并填写结果名称');
        return;
      }

      this.loading.generate = true;

      // 计算实际分辨率
      const actualResolution = this.rasterParams.resolution === 'custom' ? this.rasterParams.customResolution : parseFloat(this.rasterParams.resolution);

      const params = {
        dataset_id: this.rasterParams.sourceDataset,
        resolution: actualResolution,
        result_name: this.rasterParams.resultName
      };

      this.$http.post(`${this.apiBaseUrl}/api/raster/generate`, params)
        .then(response => {
          this.loading.generate = false;
          if (response.data && response.data.id) {
            this.$message.success('栅格模板生成成功');
            const result = response.data;

            // 添加到结果列表
            this.rasterResults.unshift(result);

            // 加载生成的栅格到地图
            this.viewRasterResult(result);
          } else {
            this.$message.error(response.data.message || '栅格模板生成失败');
          }
        })
        .catch(error => {
          this.loading.generate = false;
          console.error('栅格模板生成失败:', error);
          this.$message.error('栅格模板生成失败，请稍后重试');
        });
    },

    resetRasterParams() {
      this.$refs.datasetSelector.clearSelectedDatasets();
      this.rasterParams = {
        resolution: '30',
        customResolution: 30,
        resultName: '',
        sourceDataset: null
      };
    },


    viewRasterResult(result) {
      if (!result || !result.files || result.files.length === 0) return;

      // 获取第一个文件（栅格文件）
      const file = result.files[0];
      if (!file || !file.url) return;

      // 加载栅格数据到地图
      this.$refs.mapView.addRasterLayer({
        id: file.id,
        name: file.name,
        type: 'raster',
        url: file.url
      });
    },

    downloadRasterResult(result) {
      if (!result || !result.id) return;

      // 下载栅格数据
      window.open(`${this.apiBaseUrl}/api/raster/${result.id}/download`, '_blank');
    }
  }
};
</script>

<style scoped>
.create-raster {
  height: 100%;
  width: 100%;
}

.main-container {
  height: 100%;
  position: relative;
}

.map-main {
  padding: 0;
  height: 100%;
}

.tools-container {
  padding: 10px;
}

.raster-card,
.results-card {
  margin-bottom: 15px;
}

.tools-hidden .toggle-tools-panel {
  right: 0;
}

.results-list {
  max-height: 300px;
  overflow-y: auto;
}

.result-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 0;
  border-bottom: 1px solid #eee;
}

.result-item:last-child {
  border-bottom: none;
}

.result-info {
  flex: 1;
}

.result-name {
  font-weight: bold;
  margin-bottom: 5px;
}

.result-details {
  font-size: 12px;
  color: #666;
}

.result-details span {
  margin-right: 10px;
}

.result-actions {
  display: flex;
  gap: 5px;
}
</style>