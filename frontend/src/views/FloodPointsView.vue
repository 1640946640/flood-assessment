<template>
  <div class="flood-points">
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
          <!-- DEM数据选择器 -->
          <dataset-selector ref="datasetSelector" :allowedTypes="['raster']" :selectionMode="'single'"
            @load-dataset="loadDatasetToMap" @selected-datasets-change="handleSelectedDatasetsChange"
            :showCheckbox="true" />

          <!-- 易涝点参数配置卡片 -->
          <el-card class="params-card" shadow="never">
            <div slot="header">
              <span>易涝点识别</span>
            </div>
            <div class="params-config">
              <el-form ref="paramsForm" :model="form" label-width="120px" size="small">
                <el-form-item label="汇流累积阈值">
                  <el-input-number
                    v-model="form.accumulationThreshold"
                    :min="1"
                    :max="10000"
                    :step="1">
                  </el-input-number>
                </el-form-item>
                <el-form-item label="坡度阈值(°)">
                  <el-input-number
                    v-model="form.slopeThreshold"
                    :min="0"
                    :max="90"
                    :step="0.1">
                  </el-input-number>
                </el-form-item>
                <el-form-item label="结果名称" prop="resultName">
                  <el-input v-model="form.resultName" placeholder="请输入结果名称"></el-input>
                </el-form-item>
                <el-form-item>
                  <el-button type="primary" @click="calculateFloodPoints" :loading="calculating"
                    :disabled="!canCalculate">开始计算</el-button>
                  <el-button @click="resetParams">重置</el-button>
                </el-form-item>
              </el-form>
            </div>
          </el-card>

          <!-- 计算结果卡片 -->
          <el-card class="results-card" shadow="never" v-if="results.length > 0">
            <div slot="header">
              <span>计算结果</span>
            </div>
            <div class="results-list">
              <el-table :data="results" style="width: 100%">
                <el-table-column prop="name" label="名称" width="120"></el-table-column>
                <el-table-column label="易涝点数量" width="100">
                  <template slot-scope="scope">
                    <span>{{ scope.row.properties && scope.row.properties.pointCount ? scope.row.properties.pointCount + '个' : '未知' }}</span>
                  </template>
                </el-table-column>
                <el-table-column prop="createdAt" label="创建时间" width="150"></el-table-column>
                <el-table-column label="操作" width="120">
                  <template slot-scope="scope">
                    <el-button size="mini" type="text" @click="viewResult(scope.row)">查看</el-button>
                    <el-button size="mini" type="text" @click="downloadResult(scope.row)">下载</el-button>
                  </template>
                </el-table-column>
              </el-table>
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
  name: 'FloodPointsView',
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
      calculating: false,
      form: {
        accumulationThreshold: 100,
        slopeThreshold: 2.0,
        resultName: '',
        sourceDataset: null
      },
      results: [],
      apiBaseUrl: process.env.VUE_APP_API_URL || 'http://localhost:5000'
    };
  },
  computed: {
    canCalculate() {
      return this.form.sourceDataset && this.form.resultName;
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

      // 检查是否为DEM数据
      if (dataset.type !== 'raster') {
        this.$message.warning('请选择DEM数据集');
        return;
      }

      // 加载数据集到地图
      const layerUrl = `/datasets/${dataset.id}/view`;
      this.$refs.mapView.addRasterLayer(layerUrl, dataset.name);
    },

    handleSelectedDatasetsChange(datasets) {
      if (datasets && datasets.length > 0) {
        const dataset = datasets[0];
        // 检查是否为DEM数据
        if (dataset.type !== 'raster') {
          this.$message.warning('请选择DEM数据集');
          this.form.sourceDataset = null;
          return;
        }

        this.selectedDataset = dataset;
        this.form.sourceDataset = dataset.id;
      } else {
        this.selectedDataset = null;
        this.form.sourceDataset = null;
      }
    },

    async calculateFloodPoints() {
      if (!this.canCalculate) {
        this.$message.warning('请先选择DEM数据集并设置结果名称');
        return;
      }

      this.calculating = true;
      try {
        const response = await axios.post('/api/flood-points/calculate', {
          dataset_id: this.form.sourceDataset,
          accumulation_threshold: this.form.accumulationThreshold,
          slope_threshold: this.form.slopeThreshold,
          result_name: this.form.resultName
        });

        if (response.data && response.data.id) {
          this.$message.success('易涝点计算完成');
          this.results.unshift(response.data);
          this.viewResult(response.data);
        } else {
          this.$message.error(response.data.message || '计算失败');
        }
      } catch (error) {
        console.error('易涝点计算失败:', error);
        this.$message.error('计算失败，请稍后重试');
      } finally {
        this.calculating = false;
      }
    },

    resetParams() {
      this.$refs.datasetSelector.clearSelectedDatasets();
      this.form = {
        accumulationThreshold: 100,
        slopeThreshold: 2.0,
        resultName: '',
        sourceDataset: null
      };
    },

    viewResult(result) {
      if (!result || !result.files || result.files.length === 0) return;

      // 获取第一个文件（易涝点GeoJSON文件）
      const file = result.files[0];
      if (!file || !file.url) return;

      // 加载易涝点数据到地图
      this.$refs.mapView.addVectorLayer({
        id: file.id,
        name: file.name,
        type: 'vector',
        url: file.url
      });
    },

    downloadResult(result) {
      if (!result || !result.id) return;

      // 下载易涝点数据
      window.open(`${this.apiBaseUrl}/api/flood-points/${result.id}/download`, '_blank');
    }
  }
};
</script>

<style scoped>
.flood-points {
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

.params-card,
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

.toggle-tools-panel {
  position: absolute;
  right: 400px;
  top: 50%;
  transform: translateY(-50%);
  width: 20px;
  height: 60px;
  background-color: #fff;
  border: 1px solid #dcdfe6;
  border-right: none;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  z-index: 2000;
  border-radius: 4px 0 0 4px;
  transition: right 0.3s;
}

.tools-aside {
  width: 400px !important;
  background-color: #fff;
  border-left: 1px solid #dcdfe6;
  transition: width 0.3s;
  position: relative;
}
</style> 