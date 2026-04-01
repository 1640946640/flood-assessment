<template>
  <div class="correlation-analysis">
    <el-container>
      <!-- 左侧数据集选择器，占50% -->
      <el-aside width="50%">
        <el-card class="data-card" shadow="never">
          <div slot="header">
            <span>数据集</span>
            <el-button style="float: right; padding: 3px 0" type="text" @click="refreshDatasets">刷新</el-button>
          </div>
          <div class="data-list">
            <el-tree :data="hierarchicalDatasets" node-key="id" :props="{ label: 'name', children: 'children' }"
              @node-click="handleDatasetSelect" :expand-on-click-node="true" :show-checkbox="true"
              @check-change="handleDatasetCheck" ref="datasetTree">
              <span class="custom-tree-node" slot-scope="{ node, data }">
                <span>
                  <i v-if="data.isFolder" class="el-icon-folder" style="margin-right: 5px;"></i>
                  <i v-else-if="data.type === 'raster'" class="el-icon-picture" style="margin-right: 5px;"></i>
                  <i v-else class="el-icon-document" style="margin-right: 5px;"></i>
                  {{ node.label }}
                </span>
              </span>
            </el-tree>
          </div>
        </el-card>
      </el-aside>
      
      <!-- 右侧分析配置和结果展示，占50% -->
      <el-main class="right-main">
        <el-card class="analysis-card" shadow="never">
          <div slot="header">
            <span>相关性分析配置</span>
          </div>
          <el-form :model="analysisParams" label-width="100px" size="small">
            <el-form-item label="分析方法">
              <el-select v-model="analysisParams.method" placeholder="请选择分析方法">
                <el-option label="皮尔逊相关系数" value="pearson"></el-option>
                <el-option label="斯皮尔曼相关系数" value="spearman"></el-option>
              </el-select>
            </el-form-item>
            
            <el-form-item label="结果名称">
              <el-input v-model="analysisParams.analysisName" placeholder="请输入结果名称"></el-input>
            </el-form-item>
            
            <!-- 已选数据集显示 -->
            <el-form-item label="已选数据集">
              <div class="selected-datasets-container">
                <div v-if="selectedDatasets.length === 0" class="no-datasets-selected">
                  请从左侧选择至少两个栅格数据集进行分析
                </div>
                <el-tag
                  v-for="dataset in selectedDatasets"
                  :key="dataset.id"
                  closable
                  @close="removeDataset(dataset)"
                  class="dataset-tag">
                  {{ dataset.name }}
                </el-tag>
              </div>
            </el-form-item>
            
            <el-form-item>
              <el-button type="primary" @click="runAnalysis" :loading="loading">开始分析</el-button>
              <el-button @click="resetForm">重置</el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <!-- 预览图像 -->
        <el-card v-if="previewVisible" class="preview-card" shadow="never">
          <div slot="header">
            <span>{{ previewTitle || '分析结果预览' }}</span>
          </div>
          <div class="preview-container">
            <img v-if="previewImageUrl" :src="previewImageUrl" class="preview-image" />
          </div>
        </el-card>

        <!-- 结果展示 -->
        <el-card v-if="results.length > 0" class="results-card" shadow="never">
          <div slot="header">
            <span>分析结果</span>
          </div>
          <el-table :data="results" style="width: 100%">
            <el-table-column prop="name" label="名称"></el-table-column>
            <el-table-column prop="method" label="分析方法"></el-table-column>
            <el-table-column prop="createdAt" label="创建时间"></el-table-column>
            <el-table-column label="操作">
              <template slot-scope="scope">
                <el-button size="mini" type="primary" @click="downloadResult(scope.row, 'matrix')">下载矩阵</el-button>
                <el-button size="mini" type="success" @click="downloadResult(scope.row, 'report')">下载报告</el-button>
                <el-button size="mini" type="warning" @click="viewResult(scope.row, 'heatmap')">热力图</el-button>
                <el-button size="mini" type="info" @click="viewResult(scope.row, 'scatter')">散点图</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-main>
    </el-container>
  </div>
</template>

<script>
import axios from 'axios';

export default {
  name: 'CorrelationAnalysis',
  data() {
    return {
      apiBaseUrl: process.env.VUE_APP_API_BASE_URL || '',
      analysisParams: {
        analysisName: '相关性分析',
        method: 'pearson',
        datasets: []
      },
      loading: false,
      selectedDatasets: [],
      results: [],
      previewVisible: false,
      previewTitle: '',
      previewImageUrl: '',
      datasets: []
    };
  },
  computed: {
    hierarchicalDatasets() {
      // 处理后端返回的数据，确保是数组格式
      const datasets = this.$store.state.datasets || this.datasets;
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
    }
  },
  created() {
    this.fetchDatasets();
  },
  methods: {
    async fetchDatasets() {
      try {
        const response = await axios.get(`${this.apiBaseUrl}/api/datasets`);
        this.datasets = response.data;
        // 同时更新到store
        this.$store.commit('SET_DATASETS', response.data);
      } catch (error) {
        console.error('获取数据集失败:', error);
        this.$message.error('获取数据集失败');
      }
    },
    refreshDatasets() {
      this.fetchDatasets();
    },
    handleDatasetSelect(data) {
      // 如果是文件夹，不做任何操作
      if (data.isFolder || data.type === 'folder') return;
      
      // 如果不是栅格类型，显示提示
      if (data.type !== 'raster') {
        this.$message.warning('只能选择栅格类型数据进行相关性分析');
        return;
      }
    },
    handleDatasetCheck(data, checked) {
      if (data.isFolder || data.type === 'folder') return;
      
      if (data.type !== 'raster') {
        if (checked) {
          // 如果选中了非栅格类型，取消选中
          this.$refs.datasetTree.setChecked(data.id, false);
          this.$message.warning('只能选择栅格类型数据进行相关性分析');
        }
        return;
      }
      
      if (checked) {
        // 添加到选中列表，避免重复
        if (!this.selectedDatasets.find(item => item.id === data.id)) {
          this.selectedDatasets.push(data);
          this.analysisParams.datasets.push(data.id);
        }
      } else {
        // 从选中列表中移除
        this.selectedDatasets = this.selectedDatasets.filter(item => item.id !== data.id);
        this.analysisParams.datasets = this.analysisParams.datasets.filter(id => id !== data.id);
      }
      
      // 根据选择的数据集更新分析名称
      this.updateAnalysisName();
    },
    removeDataset(dataset) {
      // 从选中列表中移除
      this.selectedDatasets = this.selectedDatasets.filter(item => item.id !== dataset.id);
      this.analysisParams.datasets = this.analysisParams.datasets.filter(id => id !== dataset.id);
      
      // 取消树中的选中状态
      if (this.$refs.datasetTree) {
        this.$refs.datasetTree.setChecked(dataset.id, false);
      }
      
      // 更新分析名称
      this.updateAnalysisName();
    },
    updateAnalysisName() {
      if (this.selectedDatasets.length > 0) {
        const firstDataset = this.selectedDatasets[0];
        this.analysisParams.analysisName = this.selectedDatasets.length > 1 
          ? `${firstDataset.name}_等${this.selectedDatasets.length}个数据集_相关性分析` 
          : `${firstDataset.name}_相关性分析`;
      } else {
        this.analysisParams.analysisName = '相关性分析';
      }
    },
    async runAnalysis() {
      if (!this.analysisParams.analysisName || !this.analysisParams.method || this.analysisParams.datasets.length < 2) {
        this.$message.error('请选择分析方法并至少添加两个数据集');
        return;
      }

      this.loading = true;
      try {
        const response = await axios.post(`${this.apiBaseUrl}/api/correlation/analyze`, {
          analysis_name: this.analysisParams.analysisName,
          method: this.analysisParams.method,
          dataset_ids: this.analysisParams.datasets
        });

        this.results.unshift(response.data);
        this.$message.success('相关性分析完成');
        
        // 自动显示热力图结果
        if (response.data.preview) {
          const heatmapImage = response.data.preview.find(p => p.includes('heatmap'));
          if (heatmapImage) {
            this.previewImageUrl = `${this.apiBaseUrl}${heatmapImage}`;
            this.previewTitle = '相关性热力图';
            this.previewVisible = true;
          }
        }
      } catch (error) {
        console.error('相关性分析失败:', error);
        this.$message.error(`相关性分析失败: ${error.response?.data?.error || error.message}`);
      } finally {
        this.loading = false;
      }
    },
    resetForm() {
      this.analysisParams = {
        analysisName: '相关性分析',
        method: 'pearson',
        datasets: []
      };
      
      // 清空数据集选择
      if (this.$refs.datasetTree) {
        this.$refs.datasetTree.setCheckedKeys([]);
      }
      
      this.selectedDatasets = [];
      this.previewVisible = false;
    },
    downloadResult(result, type) {
      let downloadUrl = '';
      if (type === 'matrix' && result.files) {
        const matrixFile = result.files.find(f => f.name.includes('矩阵') || f.name.includes('matrix'));
        if (matrixFile) {
          downloadUrl = `${this.apiBaseUrl}${matrixFile.download_url}`;
        }
      } else if (type === 'report' && result.files) {
        const reportFile = result.files.find(f => f.name.includes('报告') || f.name.includes('report'));
        if (reportFile) {
          downloadUrl = `${this.apiBaseUrl}${reportFile.download_url}`;
        }
      }

      if (downloadUrl) {
        window.open(downloadUrl, '_blank');
      } else {
        this.$message.warning('找不到下载文件');
      }
    },
    viewResult(result, type) {
      let imageUrl = '';
      
      if (type === 'heatmap' && result.preview) {
        const heatmapImage = result.preview.find(p => p.includes('heatmap'));
        if (heatmapImage) {
          imageUrl = `${this.apiBaseUrl}${heatmapImage}`;
          this.previewTitle = '相关性热力图';
        }
      } else if (type === 'scatter' && result.preview) {
        const scatterImage = result.preview.find(p => p.includes('scatter'));
        if (scatterImage) {
          imageUrl = `${this.apiBaseUrl}${scatterImage}`;
          this.previewTitle = '散点矩阵图';
        }
      }

      if (imageUrl) {
        this.previewImageUrl = imageUrl;
        this.previewVisible = true;
      } else {
        this.$message.warning('找不到预览图');
      }
    }
  }
};
</script>

<style scoped>
.correlation-analysis {
  height: 100%;
  display: flex;
}

.el-container {
  height: 100%;
  width: 100%;
}

.el-aside {
  background-color: #f5f7fa;
  border-right: 1px solid #e6e6e6;
  padding: 10px;
  overflow-y: auto;
}

.el-main.right-main {
  padding: 10px;
  overflow-y: auto;
}

.data-card, .analysis-card, .preview-card, .results-card {
  margin-bottom: 20px;
}

.data-list {
  height: calc(100vh - 200px);
  overflow-y: auto;
}

.selected-datasets-container {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  min-height: 32px;
  padding: 5px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
}

.no-datasets-selected {
  color: #909399;
  font-size: 14px;
}

.dataset-tag {
  margin-right: 5px;
  margin-bottom: 5px;
}

.preview-container {
  display: flex;
  justify-content: center;
  align-items: center;
  margin: 10px 0;
}

.preview-image {
  max-width: 100%;
  max-height: 500px;
}

.custom-tree-node {
  width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style> 