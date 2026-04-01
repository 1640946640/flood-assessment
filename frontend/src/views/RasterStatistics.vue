<template>
  <div class="raster-statistics">
    <el-container>
      <!-- 左侧数据集列表 -->
      <el-aside width="50%" class="left-panel">
        <el-card shadow="never" class="dataset-card">
          <div slot="header" class="card-header">
            <span>数据集</span>
            <el-button style="float: right; padding: 3px 0" type="text" @click="refreshDatasets">刷新</el-button>
          </div>
          <div class="dataset-tree-container">
            <div v-if="loadingFiles" class="loading-overlay">
              <i class="el-icon-loading"></i>
              <span>正在加载文件列表...</span>
            </div>
            <el-tree
              v-if="!loadingFiles"
              :data="folderData"
              :props="defaultProps"
              @node-click="handleNodeClick"
              :expand-on-click-node="false"
              ref="dataTree"
              node-key="id">
              <span class="custom-tree-node" slot-scope="{ node, data }">
                <span>
                  <i :class="getIconForFile(data)" style="margin-right: 5px;"></i>
                  {{ node.label }}
                </span>
              </span>
            </el-tree>
          </div>
        </el-card>
      </el-aside>

      <!-- 右侧配置面板 -->
      <el-main class="right-panel">
        <el-card shadow="never" class="main-card">
          <div slot="header" class="card-header">
            <span>栅格统计配置</span>
          </div>
          <el-form :model="statisticsParams" label-width="100px" size="small">
            <el-form-item label="统计类型">
              <el-radio-group v-model="statisticsParams.statisticsType">
                <el-radio label="single_value">单一值统计</el-radio>
                <el-radio label="range_value">范围值统计</el-radio>
              </el-radio-group>
            </el-form-item>

            <el-form-item label="栅格数据集">
              <el-input v-model="statisticsParams.rasterDisplayName" placeholder="请从左侧数据集中选择栅格文件"
                readonly></el-input>
              <div class="input-tip">
                <i class="el-icon-info"></i> 请从左侧数据集树中选择要统计的栅格文件
              </div>
            </el-form-item>
            
            <template v-if="statisticsParams.statisticsType === 'single_value'">
              <el-form-item label="单一值">
                <el-input-number v-model="statisticsParams.singleValue" :precision="16" :step="0.000001" :min="-Infinity" :controls-position="'right'" style="width: 100%"></el-input-number>
                <div class="input-tip">
                  <i class="el-icon-info"></i> 将统计栅格中等于该值的像元数量
                </div>
              </el-form-item>
            </template>
            
            <template v-else>
              <el-form-item label="最小值">
                <el-input-number v-model="statisticsParams.minValue" :precision="16" :step="0.000001" :min="-Infinity" :controls-position="'right'" style="width: 100%"></el-input-number>
              </el-form-item>
              
              <el-form-item label="最大值">
                <el-input-number v-model="statisticsParams.maxValue" :precision="16" :step="0.000001" :min="-Infinity" :controls-position="'right'" style="width: 100%"></el-input-number>
                <div class="input-tip">
                  <i class="el-icon-info"></i> 将统计栅格中值在该范围内的像元数量
                </div>
              </el-form-item>
            </template>
            
            <el-form-item label="结果名称">
              <el-input v-model="statisticsParams.resultName" placeholder="请输入结果名称"></el-input>
            </el-form-item>
            
            <el-form-item>
              <el-button type="primary" @click="runStatistics" :loading="loading">开始统计</el-button>
              <el-button @click="resetForm">重置</el-button>
            </el-form-item>
          </el-form>

          <!-- 当前统计结果 -->
          <div v-if="currentResult" class="results-section">
            <div class="results-header">
              <h3>统计结果</h3>
              <el-button size="small" type="primary" icon="el-icon-download" @click="downloadCurrentResult">下载CSV</el-button>
            </div>

            <div class="statistics-cards">
              <div class="stat-card">
                <div class="stat-value">{{ formatNumber(currentResult.statistics.totalCount) }}</div>
                <div class="stat-label">总像元数</div>
              </div>
              <div class="stat-card">
                <div class="stat-value">{{ formatNumber(currentResult.statistics.validCount) }}</div>
                <div class="stat-label">有效像元数</div>
              </div>
              <div class="stat-card highlight">
                <div class="stat-value">{{ formatNumber(currentResult.statistics.targetCount) }}</div>
                <div class="stat-label">目标像元数</div>
              </div>
              <div class="stat-card">
                <div class="stat-value">{{ formatPercent(currentResult.statistics.targetRatio) }}</div>
                <div class="stat-label">目标占比</div>
              </div>
            </div>

            <el-card shadow="never" class="statistics-detail-card">
              <div class="stat-detail-section">
                <h4>详细统计信息</h4>
                <el-descriptions :column="2" border size="small">
                  <el-descriptions-item label="数据集名称">{{ currentResult.statistics.datasetName }}</el-descriptions-item>
                  <el-descriptions-item label="统计类型">
                    {{ currentResult.statistics.statisticsType === 'single_value' ? '单一值统计' : '范围值统计' }}
                  </el-descriptions-item>
                  <el-descriptions-item label="统计值/范围">
                    <template v-if="currentResult.statistics.statisticsType === 'single_value'">
                      {{ currentResult.statistics.singleValue }}
                    </template>
                    <template v-else>
                      {{ currentResult.statistics.minValue }} ~ {{ currentResult.statistics.maxValue }}
                    </template>
                  </el-descriptions-item>
                  <el-descriptions-item label="坐标系">{{ currentResult.statistics.coordinateSystem }}</el-descriptions-item>
                  <el-descriptions-item label="像元大小">{{ currentResult.statistics.pixelSizeInfo }}</el-descriptions-item>
                  <el-descriptions-item label="像元面积">{{ formatArea(currentResult.statistics.pixelArea) }}</el-descriptions-item>
                  <el-descriptions-item label="调整后面积">{{ formatArea(currentResult.statistics.adjustedArea) }}</el-descriptions-item>
                  <el-descriptions-item label="有效面积">{{ formatArea(currentResult.statistics.validArea) }}</el-descriptions-item>
                  <el-descriptions-item label="总面积">{{ formatArea(currentResult.statistics.totalArea) }}</el-descriptions-item>
                </el-descriptions>
              </div>
            </el-card>
          </div>

          <!-- 历史统计结果 -->
          <div v-else-if="results.length > 0" class="results-section">
            <h3>历史统计结果</h3>
            <el-table :data="results" style="width: 100%">
              <el-table-column prop="name" label="名称" width="180"></el-table-column>
              <el-table-column prop="createdAt" label="创建时间" width="180"></el-table-column>
              <el-table-column label="操作">
                <template slot-scope="scope">
                  <el-button size="mini" type="primary" icon="el-icon-download" @click="downloadResult(scope.row)">下载CSV</el-button>
                  <el-button size="mini" type="success" @click="viewStatistics(scope.row)">查看结果</el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-card>
      </el-main>
    </el-container>
  </div>
</template>

<script>
import axios from 'axios';

export default {
  name: 'RasterStatistics',
  data() {
    return {
      apiBaseUrl: process.env.VUE_APP_API_BASE_URL || '',
      statisticsParams: {
        rasterDataset: null,
        rasterDisplayName: '',
        statisticsType: 'single_value',
        singleValue: 1,
        minValue: 0,
        maxValue: 10,
        resultName: '栅格统计结果'
      },
      loading: false,
      loadingFiles: false,
      datasets: [],
      results: [],
      currentResult: null,
      // 文件树相关数据
      folderData: [],
      defaultProps: {
        children: 'children',
        label: 'name',
        isLeaf: 'isLeaf'
      }
    };
  },
  created() {
    this.fetchDatasets();
  },
  methods: {
    async fetchDatasets() {
      this.loadingFiles = true;
      try {
        const response = await axios.get(`${this.apiBaseUrl}/api/datasets`);
        this.datasets = response.data;
        
        // 处理数据集树结构
        this.folderData = response.data || [];
        this.processDatasets(this.folderData);
      } catch (error) {
        console.error('获取数据集失败:', error);
        this.$message.error('获取数据集失败');
      } finally {
        this.loadingFiles = false;
      }
    },
    
    refreshDatasets() {
      this.fetchDatasets();
    },
    
    // 处理数据集，添加图标标识等
    processDatasets(datasets) {
      const processNode = (node) => {
        if (node.isFolder && node.children) {
          node.children.forEach(child => processNode(child));
        }
      };
      
      datasets.forEach(node => processNode(node));
    },
    
    // 获取文件图标
    getIconForFile(data) {
      if (data.isFolder) {
        return 'el-icon-folder';
      } else if (data.format && data.format.toLowerCase() === 'tif') {
        return 'el-icon-picture';
      } else {
        return 'el-icon-document';
      }
    },
    
    // 处理树节点点击
    handleNodeClick(data) {
      if (!data.isFolder && data.type === 'raster') {
        this.statisticsParams.rasterDataset = data.id;
        this.statisticsParams.rasterDisplayName = data.name;
      }
    },
    
    async runStatistics() {
      if (!this.statisticsParams.rasterDataset || !this.statisticsParams.resultName) {
        this.$message.error('请选择数据集并输入结果名称');
        return;
      }

      this.loading = true;
      try {
        const params = {
          dataset_id: this.statisticsParams.rasterDataset,
          statistics_type: this.statisticsParams.statisticsType,
          result_name: this.statisticsParams.resultName
        };

        // 根据统计类型添加参数
        if (this.statisticsParams.statisticsType === 'single_value') {
          params.single_value = this.statisticsParams.singleValue;
        } else {
          params.min_value = this.statisticsParams.minValue;
          params.max_value = this.statisticsParams.maxValue;
          
          if (params.min_value > params.max_value) {
            this.$message.error('最小值不能大于最大值');
            this.loading = false;
            return;
          }
        }

        const response = await axios.post(`${this.apiBaseUrl}/api/raster-statistics/analyze`, params);
        
        // 更新当前结果和历史结果
        this.currentResult = response.data;
        this.results.unshift(response.data);
        
        this.$message.success('栅格统计分析完成');
      } catch (error) {
        console.error('栅格统计分析失败:', error);
        this.$message.error(`栅格统计分析失败: ${error.response?.data?.message || error.message}`);
      } finally {
        this.loading = false;
      }
    },
    
    resetForm() {
      this.statisticsParams = {
        rasterDataset: null,
        rasterDisplayName: '',
        statisticsType: 'single_value',
        singleValue: 0,
        minValue: 0,
        maxValue: 10,
        resultName: '栅格统计结果'
      };
      this.currentResult = null;
    },
    
    downloadResult(result) {
      if (result && result.csvUrl) {
        window.open(`${this.apiBaseUrl}${result.csvUrl}`, '_blank');
      } else {
        this.$message.warning('找不到CSV文件');
      }
    },
    
    viewStatistics(result) {
      this.currentResult = result;
    },

    downloadCurrentResult() {
      this.downloadResult(this.currentResult);
    },
    
    formatArea(area) {
      if (area === undefined || area === null) return '-';
      
      // 如果面积小于1平方公里，显示平方米
      if (area < 1000000) {
        return `${area.toFixed(2)} m²`;
      }
      
      // 否则显示平方公里
      return `${(area / 1000000).toFixed(2)} km²`;
    },
    
    formatNumber(num) {
      if (num === undefined || num === null) return '-';
      return num.toLocaleString();
    },
    
    formatPercent(value) {
      if (value === undefined || value === null) return '-';
      return `${(value * 100).toFixed(2)}%`;
    }
  }
};
</script>

<style scoped>
.raster-statistics {
  height: 100%;
}

.el-container {
  height: 100%;
  overflow: hidden;
}

.left-panel, .right-panel {
  padding: 10px;
  height: 100%;
  overflow-y: auto;
}

.dataset-card, .main-card {
  height: 100%;
}

.dataset-tree-container {
  height: calc(100vh - 120px);
  overflow-y: auto;
  position: relative;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.results-section {
  margin-top: 20px;
}

.input-tip {
  color: #909399;
  font-size: 12px;
  margin-top: 5px;
}

.results-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
}

.statistics-cards {
  display: flex;
  justify-content: space-between;
  margin-bottom: 15px;
  padding: 10px;
  background-color: #f5f7fa;
  border-radius: 4px;
}

.stat-card {
  text-align: center;
  padding: 10px;
  flex: 1;
  border-right: 1px solid #ebeef5;
}

.stat-card:last-child {
  border-right: none;
}

.stat-card .stat-value {
  font-size: 24px;
  font-weight: bold;
  color: #409EFF;
  margin-bottom: 5px;
}

.stat-card .stat-label {
  font-size: 14px;
  color: #606266;
}

.stat-card.highlight .stat-value {
  color: #E6A23C;
}

.statistics-detail-card {
  margin-top: 15px;
}

.stat-detail-section h4 {
  margin-bottom: 15px;
  font-size: 16px;
  font-weight: normal;
}

h3 {
  margin-bottom: 15px;
  font-size: 18px;
}

.custom-tree-node {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-right: 8px;
}

.loading-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(255, 255, 255, 0.7);
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  z-index: 10;
}

.loading-overlay i {
  font-size: 32px;
  margin-bottom: 10px;
}
</style> 