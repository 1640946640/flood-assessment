<template>
  <div class="raster-compare">
    <el-card class="analysis-card" shadow="never">
      <div slot="header">
        <span>栅格比较分析</span>
      </div>
      <el-form :model="compareParams" label-width="100px" size="small">
        <el-form-item label="分析方法">
          <el-select v-model="compareParams.method" placeholder="请选择分析方法">
            <el-option label="差值分析" value="difference"></el-option>
            <el-option label="比率分析" value="ratio"></el-option>
            <el-option label="归一化差值" value="normalized_difference"></el-option>
          </el-select>
        </el-form-item>
        
        <el-form-item label="基准栅格">
          <el-input v-model="compareParams.baseRasterDisplayName" placeholder="请选择基准栅格数据集"
            readonly @click.native="showDatasetSelector('baseRaster')"></el-input>
          <div class="input-tip" v-if="!compareParams.baseRasterDisplayName">
            <i class="el-icon-info"></i> 点击文本框选择要用作基准的栅格数据集
          </div>
        </el-form-item>
        
        <el-form-item label="目标栅格">
          <el-input v-model="compareParams.targetRasterDisplayName" placeholder="请选择目标栅格数据集"
            readonly @click.native="showDatasetSelector('targetRaster')"></el-input>
          <div class="input-tip" v-if="!compareParams.targetRasterDisplayName">
            <i class="el-icon-info"></i> 点击文本框选择要进行比较的栅格数据集（可多选）
          </div>
          <!-- 显示已选择的目标栅格 -->
          <div v-if="compareParams.targetRasterDatasets && compareParams.targetRasterDatasets.length > 0" class="selected-datasets">
            <el-tag
              v-for="(dataset, index) in compareParams.targetRasterDatasets"
              :key="index"
              closable
              @close="removeTargetDataset(index)"
              class="target-dataset-tag">
              {{ dataset.name }}
            </el-tag>
          </div>
        </el-form-item>
        
        <el-form-item label="结果名称">
          <el-input v-model="compareParams.analysisName" placeholder="请输入结果名称"></el-input>
        </el-form-item>
        
        <el-form-item>
          <el-button type="primary" @click="runCompare" :loading="loading">开始分析</el-button>
          <el-button @click="resetForm">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 数据集选择器对话框 -->
    <el-dialog :title="datasetSelectorTitle" :visible.sync="datasetSelectorVisible" width="70%">
      <div class="dataset-dialog-content">
        <div v-if="loadingFiles" class="loading-overlay">
          <i class="el-icon-loading"></i>
          <span>正在加载文件列表...</span>
        </div>
        
        <!-- 使用树形结构显示文件夹和文件 -->
        <el-tree
          v-if="!loadingFiles"
          :data="folderData"
          :props="defaultProps"
          @node-click="handleNodeClick"
          :expand-on-click-node="false"
          ref="dataTree"
          node-key="path">
          <span class="custom-tree-node" slot-scope="{ node, data }">
            <span>
              <i :class="getIconForFile(data)" style="margin-right: 5px;"></i>
              {{ node.label }}
            </span>
            <span v-if="currentSelectorType === 'targetRaster' && !data.isFolder" class="node-actions">
              <el-checkbox 
                v-model="data.selected" 
                @change="(val) => handleDatasetCheckChange(val, data)"></el-checkbox>
            </span>
          </span>
        </el-tree>
        
        <!-- 显示当前选择的文件 -->
        <div v-if="currentSelectorType === 'targetRaster'" class="selected-files-panel">
          <h4>已选择的文件</h4>
          <el-tag
            v-for="(file, index) in tempSelectedTargetDatasets"
            :key="index"
            closable
            @close="removeFromSelected(file)"
            class="selected-file-tag">
            {{ file.name }}
          </el-tag>
          <div v-if="tempSelectedTargetDatasets.length === 0" class="no-files-selected">
            未选择文件
          </div>
        </div>
      </div>
      <div slot="footer" class="dialog-footer">
        <el-button @click="datasetSelectorVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmDatasetSelection">确定</el-button>
      </div>
    </el-dialog>

    <!-- 预览图像 -->
    <el-card v-if="previewVisible" class="preview-card" shadow="never">
      <div slot="header">
        <span>分析结果预览</span>
      </div>
      <div class="preview-container">
        <img v-if="previewImageUrl" :src="previewImageUrl" class="preview-image" />
        <div v-if="previewData" class="preview-data">
          <h4>统计信息</h4>
          <el-descriptions :column="2" border>
            <el-descriptions-item label="最小值">{{ previewData.min }}</el-descriptions-item>
            <el-descriptions-item label="最大值">{{ previewData.max }}</el-descriptions-item>
            <el-descriptions-item label="平均值">{{ previewData.mean }}</el-descriptions-item>
            <el-descriptions-item label="标准差">{{ previewData.std }}</el-descriptions-item>
            <el-descriptions-item label="相关系数">{{ previewData.correlation }}</el-descriptions-item>
            <el-descriptions-item label="RMSE">{{ previewData.rmse }}</el-descriptions-item>
          </el-descriptions>
        </div>
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
            <el-button size="mini" type="primary" @click="downloadResult(scope.row, 'report')">下载报告</el-button>
            <el-button size="mini" type="success" @click="downloadResult(scope.row, 'csv')">下载CSV</el-button>
            <el-button size="mini" type="warning" @click="viewResult(scope.row)">查看结果</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script>
import axios from 'axios';

export default {
  name: 'RasterCompare',
  data() {
    return {
      apiBaseUrl: process.env.VUE_APP_API_BASE_URL || '',
      compareParams: {
        analysisName: '栅格比较分析',
        baseRasterDataset: null,
        baseRasterDisplayName: '',
        targetRasterDatasets: [],
        targetRasterDisplayName: '',
        method: 'difference'
      },
      loading: false,
      loadingFiles: false,
      datasetSelectorVisible: false,
      datasetSelectorTitle: '选择数据集',
      currentSelectorType: '',
      tempSelectedDataset: null,
      tempSelectedTargetDatasets: [],
      results: [],
      previewVisible: false,
      previewImageUrl: '',
      previewData: null,
      // 树形结构的属性定义
      defaultProps: {
        children: 'children',
        label: 'name',
        isLeaf: 'isLeaf'
      },
      // 文件夹数据
      folderData: []
    };
  },
  methods: {
    async fetchAllFiles() {
      this.loadingFiles = true;
      try {
        // 获取数据集列表
        const response = await axios.get(`${this.apiBaseUrl}/api/datasets`);
        
        // 将数据处理成树形结构
        const datasets = response.data || [];
        
        // 处理数据，添加selected属性
        this.processDatasets(datasets);
        
        // 更新文件夹数据
        this.folderData = datasets;
        
      } catch (error) {
        console.error('获取文件列表失败:', error);
        this.$message.error('获取文件列表失败，请刷新页面重试');
      } finally {
        this.loadingFiles = false;
      }
    },
    
    processDatasets(datasets) {
      // 递归处理数据集，为每个节点添加selected属性
      const processNode = (node) => {
        if (node.isFolder && node.children) {
          // 如果是文件夹，递归处理子节点
          node.children.forEach(child => processNode(child));
        } else if (!node.isFolder) {
          // 如果是文件，添加selected属性
          node.selected = this.tempSelectedTargetDatasets.some(item => item.path === node.id);
          
          // 只保留栅格文件（.tif扩展名）
          if (node.format && node.format.toLowerCase() === 'tif') {
            node.isTif = true;
          }
        }
      };
      
      // 处理所有节点
      datasets.forEach(node => processNode(node));
    },
    
    getIconForFile(data) {
      if (data.isFolder) {
        return 'el-icon-folder';
      } else if (data.format && data.format.toLowerCase() === 'tif') {
        return 'el-icon-picture';
      } else {
        return 'el-icon-document';
      }
    },
    
    showDatasetSelector(type) {
      this.currentSelectorType = type;
      
      if (type === 'baseRaster') {
        this.datasetSelectorTitle = '选择基准栅格数据集';
        this.tempSelectedDataset = null;
      } else if (type === 'targetRaster') {
        this.datasetSelectorTitle = '选择目标栅格数据集（可多选）';
        this.tempSelectedTargetDatasets = [...this.compareParams.targetRasterDatasets];
      }
      
      // 获取文件列表
      this.fetchAllFiles();
      
      this.datasetSelectorVisible = true;
    },
    
    handleNodeClick(data) {
      // 如果是文件夹，不执行任何操作
      if (data.isFolder) return;
      
      // 只处理TIF文件
      if (!data.format || data.format.toLowerCase() !== 'tif') {
        this.$message.warning('只能选择TIF格式的栅格文件');
        return;
      }
      
      // 处理文件点击
      if (this.currentSelectorType === 'baseRaster') {
        // 基准栅格是单选的，直接替换
        this.tempSelectedDataset = {
          id: data.id,
          name: data.name,
          path: data.id
        };
      } else if (this.currentSelectorType === 'targetRaster') {
        // 目标栅格是多选的，切换选中状态
        data.selected = !data.selected;
        this.handleDatasetCheckChange(data.selected, data);
      }
    },
    
    handleDatasetCheckChange(checked, data) {
      if (this.currentSelectorType === 'targetRaster') {
        if (checked) {
          // 添加到临时选中列表
          if (!this.tempSelectedTargetDatasets.some(item => item.id === data.id)) {
            this.tempSelectedTargetDatasets.push({
              id: data.id,
              name: data.name,
              path: data.id
            });
          }
        } else {
          // 从临时选中列表中移除
          this.tempSelectedTargetDatasets = this.tempSelectedTargetDatasets.filter(item => item.id !== data.id);
        }
      }
    },
    
    removeFromSelected(file) {
      // 从临时选中列表中移除文件
      this.tempSelectedTargetDatasets = this.tempSelectedTargetDatasets.filter(item => item.id !== file.id);
      
      // 更新树中的选中状态
      this.updateTreeSelection();
    },
    
    updateTreeSelection() {
      // 递归更新树中的选中状态
      const updateNode = (nodes) => {
        if (!nodes) return;
        
        for (const node of nodes) {
          if (node.isFolder && node.children) {
            updateNode(node.children);
          } else if (!node.isFolder) {
            // 更新文件的选中状态
            node.selected = this.tempSelectedTargetDatasets.some(item => item.id === node.id);
          }
        }
      };
      
      // 更新所有节点
      updateNode(this.folderData);
    },
    
    confirmDatasetSelection() {
      if (this.currentSelectorType === 'baseRaster') {
        if (!this.tempSelectedDataset) {
          this.$message.warning('请选择一个基准栅格数据集');
          return;
        }
        
        this.compareParams.baseRasterDataset = this.tempSelectedDataset.path;
        this.compareParams.baseRasterDisplayName = this.tempSelectedDataset.name;
      } else if (this.currentSelectorType === 'targetRaster') {
        if (this.tempSelectedTargetDatasets.length === 0) {
          this.$message.warning('请至少选择一个目标栅格数据集');
          return;
        }
        
        this.compareParams.targetRasterDatasets = [...this.tempSelectedTargetDatasets];
        // 更新显示名称
        if (this.tempSelectedTargetDatasets.length === 1) {
          this.compareParams.targetRasterDisplayName = this.tempSelectedTargetDatasets[0].name;
        } else {
          this.compareParams.targetRasterDisplayName = `已选择 ${this.tempSelectedTargetDatasets.length} 个目标栅格`;
        }
      }
      
      // 自动更新分析名称
      this.updateAnalysisName();
      this.datasetSelectorVisible = false;
    },
    
    removeTargetDataset(index) {
      // 移除指定索引的目标数据集
      this.compareParams.targetRasterDatasets.splice(index, 1);
      
      // 更新显示名称
      if (this.compareParams.targetRasterDatasets.length === 0) {
        this.compareParams.targetRasterDisplayName = '';
      } else if (this.compareParams.targetRasterDatasets.length === 1) {
        this.compareParams.targetRasterDisplayName = this.compareParams.targetRasterDatasets[0].name;
      } else {
        this.compareParams.targetRasterDisplayName = `已选择 ${this.compareParams.targetRasterDatasets.length} 个目标栅格`;
      }
      
      // 更新分析名称
      this.updateAnalysisName();
    },
    
    updateAnalysisName() {
      if (this.compareParams.baseRasterDisplayName) {
        if (this.compareParams.targetRasterDatasets.length === 1) {
          // 单个目标栅格时的命名
          this.compareParams.analysisName = 
            `${this.compareParams.baseRasterDisplayName.substring(0, 15)}_vs_${this.compareParams.targetRasterDatasets[0].name.substring(0, 15)}_${this.compareParams.method}`;
        } else if (this.compareParams.targetRasterDatasets.length > 1) {
          // 多个目标栅格时的命名
          this.compareParams.analysisName = 
            `${this.compareParams.baseRasterDisplayName.substring(0, 15)}_对比${this.compareParams.targetRasterDatasets.length}个栅格_${this.compareParams.method}`;
        } else {
          // 只有基准栅格时的命名
          this.compareParams.analysisName = `${this.compareParams.baseRasterDisplayName.substring(0, 15)}_栅格比较`;
        }
      } else {
        this.compareParams.analysisName = '栅格比较分析';
      }
    },
    
    async runCompare() {
      if (!this.compareParams.analysisName || 
          !this.compareParams.baseRasterDataset || 
          this.compareParams.targetRasterDatasets.length === 0 ||
          !this.compareParams.method) {
        this.$message.error('请填写所有必要参数');
        return;
      }

      // 检查基准栅格是否与任一目标栅格相同
      if (this.compareParams.targetRasterDatasets.some(d => d.path === this.compareParams.baseRasterDataset)) {
        this.$message.error('基准栅格和目标栅格不能相同');
        return;
      }

      this.loading = true;
      
      try {
        // 为每个目标栅格执行分析
        const results = [];
        for (const targetDataset of this.compareParams.targetRasterDatasets) {
          // 为多个目标栅格时调整名称
          let analysisName = this.compareParams.analysisName;
          if (this.compareParams.targetRasterDatasets.length > 1) {
            analysisName = `${this.compareParams.baseRasterDisplayName.substring(0, 15)}_vs_${targetDataset.name.substring(0, 15)}_${this.compareParams.method}`;
          }
          
          const response = await axios.post(`${this.apiBaseUrl}/api/raster/compare`, {
            analysis_name: analysisName,
            base_dataset_id: this.compareParams.baseRasterDataset,
            compare_dataset_id: targetDataset.path,
            method: this.compareParams.method
          });
          
          results.push(response.data);
        }
        
        // 将结果添加到结果列表
        this.results = [...results, ...this.results];
        
        this.$message.success('栅格比较分析完成');
        
        // 自动显示第一个结果
        if (results.length > 0) {
          this.viewResult(results[0]);
        }
      } catch (error) {
        console.error('栅格比较分析失败:', error);
        this.$message.error(`栅格比较分析失败: ${error.response?.data?.error || error.message}`);
      } finally {
        this.loading = false;
      }
    },
    
    resetForm() {
      this.compareParams = {
        analysisName: '栅格比较分析',
        baseRasterDataset: null,
        baseRasterDisplayName: '',
        targetRasterDatasets: [],
        targetRasterDisplayName: '',
        method: 'difference'
      };
      
      this.previewVisible = false;
    },
    
    downloadResult(result, type) {
      let downloadUrl = '';
      if (type === 'report' && result.files) {
        const reportFile = result.files.find(f => f.name.includes('报告') || f.name.includes('report'));
        if (reportFile) {
          downloadUrl = `${this.apiBaseUrl}${reportFile.download_url}`;
        }
      } else if (type === 'csv' && result.files) {
        const csvFile = result.files.find(f => f.format === 'csv');
        if (csvFile) {
          downloadUrl = `${this.apiBaseUrl}${csvFile.download_url}`;
        }
      }

      if (downloadUrl) {
        window.open(downloadUrl, '_blank');
      } else {
        this.$message.warning('找不到下载文件');
      }
    },
    
    async viewResult(result) {
      if (!result.preview || result.preview.length === 0) {
        this.$message.warning('没有可用的预览图');
        return;
      }

      this.previewImageUrl = `${this.apiBaseUrl}${result.preview[0]}`;
      
      // 获取分析结果的统计信息
      try {
        const response = await axios.get(`${this.apiBaseUrl}/api/raster/compare/${result.id}/statistics`);
        this.previewData = response.data;
      } catch (error) {
        console.error('获取统计信息失败:', error);
        this.previewData = null;
      }
      
      this.previewVisible = true;
    }
  }
};
</script>

<style scoped>
.raster-compare {
  padding: 20px;
  max-width: 800px;
  margin: 0 auto;
}

.analysis-card, .preview-card, .results-card {
  margin-bottom: 20px;
}

.input-tip {
  color: #909399;
  font-size: 12px;
  margin-top: 5px;
}

.selected-datasets {
  margin-top: 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.target-dataset-tag {
  margin-right: 5px;
  margin-bottom: 5px;
}

.dataset-dialog-content {
  width: 100%;
  display: flex;
  flex-direction: column;
  position: relative;
  min-height: 300px;
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

.selected-files-panel {
  margin-top: 20px;
  padding-top: 10px;
  border-top: 1px solid #dcdfe6;
}

.selected-file-tag {
  margin-right: 5px;
  margin-bottom: 5px;
}

.no-files-selected {
  color: #909399;
  font-size: 14px;
  margin-top: 5px;
}

.preview-container {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.preview-image {
  max-width: 100%;
  max-height: 400px;
}

.preview-data {
  margin-top: 20px;
}

.custom-tree-node {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-right: 8px;
}

.node-actions {
  margin-left: 8px;
}
</style> 