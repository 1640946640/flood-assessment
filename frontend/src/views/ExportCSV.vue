<template>
  <div class="export-csv-container">
    <el-container>
      <!-- 左侧数据集列表 -->
      <el-aside width="50%" class="left-panel">
        <el-card shadow="never" class="dataset-card">
          <div slot="header" class="card-header">
            <span>数据集</span>
            <el-button style="float: right; padding: 3px 0" type="text" @click="loadRasterFiles">刷新</el-button>
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
                <span v-if="!data.isFolder" class="node-actions">
                  <el-button
                    size="mini"
                    type="text"
                    @click.stop="handleAddToSelected(data)"
                    :disabled="isFileSelected(data)">
                    添加
                  </el-button>
                </span>
              </span>
            </el-tree>
          </div>
        </el-card>
      </el-aside>

      <!-- 右侧导出配置 -->
      <el-main class="right-panel">
        <el-card shadow="never" class="main-card">
      <div slot="header" class="card-header">
            <span>导出配置</span>
      </div>

          <el-form :model="form" :rules="rules" ref="exportForm" label-width="100px" size="small">
            <!-- 文件名称 -->
            <el-form-item label="文件名称">
              <el-input v-model="form.fileName" placeholder="请输入导出文件名称"></el-input>
        </el-form-item>

            <!-- 对齐方法 -->
            <el-form-item label="对齐方法">
              <el-select v-model="form.alignMethod" style="width: 100%">
                <el-option label="最近邻插值" value="nearest"></el-option>
                <el-option label="双线性插值" value="bilinear"></el-option>
          </el-select>
        </el-form-item>

            <!-- 已选栅格 -->
            <el-form-item label="已选栅格">
              <div class="selected-rasters">
                <div v-if="selectedRasters.length === 0" class="no-selection">
                  请在左侧数据集中选择栅格文件
                </div>
                <el-tag
                  v-for="raster in selectedRasters"
                  :key="raster.id"
                  closable
                  @close="removeRaster(raster)"
                  class="raster-tag">
                  {{ raster.name }}
                </el-tag>
              </div>
        </el-form-item>

        <!-- 操作按钮 -->
        <el-form-item>
          <el-button 
            type="primary" 
            @click="exportCSV" 
            :loading="exporting"
            :disabled="!canExport">
                导出CSV
          </el-button>
          <el-button @click="resetForm">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>
      </el-main>
    </el-container>

    <!-- 进度对话框 -->
    <el-dialog
      title="导出进度"
      :visible.sync="progressDialogVisible"
      width="400px"
      :close-on-click-modal="false"
      :close-on-press-escape="false">
      <div class="progress-content">
        <el-progress 
          :percentage="exportProgress" 
          :status="exportStatus">
        </el-progress>
        <p class="progress-text">{{ progressText }}</p>
      </div>
      <div slot="footer" class="dialog-footer">
        <el-button @click="cancelExport" v-if="exporting">取消导出</el-button>
        <el-button type="primary" @click="progressDialogVisible = false" v-else>确定</el-button>
      </div>
    </el-dialog>
  </div>
</template>

<script>
import axios from 'axios'

export default {
  name: 'ExportCSV',
  data() {
    return {
      apiBaseUrl: process.env.VUE_APP_API_BASE_URL || '',
      form: {
        fileName: '多栅格导出',
        alignMethod: 'nearest',
        exportOptions: ['includeZeroValues', 'alignRasters']
      },
      rules: {
        fileName: [
          { required: true, message: '请输入文件名称', trigger: 'blur' }
        ]
      },
      rasterFiles: [],
      selectedRasters: [],
      exporting: false,
      loadingFiles: false,
      progressDialogVisible: false,
      exportProgress: 0,
      exportStatus: '',
      progressText: '',
      cancelToken: null,
      // 树形结构相关
      folderData: [],
      defaultProps: {
        children: 'children',
        label: 'name',
        isLeaf: 'isLeaf'
      }
    }
  },
  computed: {
    canExport() {
      return this.selectedRasters.length > 0 && !this.exporting
    }
  },
  mounted() {
    this.loadRasterFiles()
  },
  methods: {
    async loadRasterFiles() {
      this.loadingFiles = true;
      try {
        // 加载所有数据集
        const response = await axios.get(`${this.apiBaseUrl}/api/datasets`)
        this.folderData = response.data || [];
        
        // 递归处理数据集，为每个节点添加属性
        this.processDatasets(this.folderData);
        
        // 扁平化数据集用于其他操作
        this.rasterFiles = this.flattenDatasets(response.data).filter(file => file.type === 'raster')
        console.log('栅格文件:', this.rasterFiles)
      } catch (error) {
        console.error('加载栅格文件列表失败:', error)
        this.$message.error('加载文件列表失败')
      } finally {
        this.loadingFiles = false;
      }
    },

    processDatasets(datasets) {
      // 递归处理数据集，为每个节点添加属性
      const processNode = (node) => {
        if (node.isFolder && node.children) {
          // 如果是文件夹，递归处理子节点
          node.children.forEach(child => processNode(child));
        } else if (!node.isFolder) {
          // 如果是文件，添加格式判断
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

    handleNodeClick(data) {
      // 如果是文件夹，不执行任何操作
      if (data.isFolder) return;
      
      // 非TIF文件不操作
      if (!data.format || data.format.toLowerCase() !== 'tif') {
        this.$message.warning('只能选择TIF格式的栅格文件');
        return;
      }
    },

    isFileSelected(data) {
      // 检查文件是否已选择
      return this.selectedRasters.some(r => r.id === data.id);
    },

    handleAddToSelected(data) {
      if (data.isFolder) return;
      
      // 非TIF文件不操作
      if (!data.format || data.format.toLowerCase() !== 'tif') {
        this.$message.warning('只能选择TIF格式的栅格文件');
        return;
      }

      // 检查是否已添加
      if (this.selectedRasters.some(r => r.id === data.id)) {
        this.$message.info(`"${data.name}"已在列表中`);
        return;
      }
      
      // 添加到数据栅格
      this.selectedRasters.push({
        id: data.id,
        name: data.name,
        path: data.id
      });
      
      this.$message.success(`已添加"${data.name}"`);
    },

    flattenDatasets(data) {
      // 递归展平数据集结构
      let result = []
      
      const flatten = (items) => {
        items.forEach(item => {
          if (item.isFolder && item.children) {
            flatten(item.children)
          } else if (!item.isFolder) {
            result.push(item)
          }
        })
      }
      
      flatten(data)
      return result
    },

    removeRaster(raster) {
      const index = this.selectedRasters.findIndex(r => r.id === raster.id);
      if (index !== -1) {
        this.selectedRasters.splice(index, 1);
      }
    },

    async exportCSV() {
      if (!this.canExport) return;

      this.exporting = true;
      this.progressDialogVisible = true;
      this.exportProgress = 0;
      this.exportStatus = '';
      this.progressText = '开始导出...';

        // 创建取消令牌
      const CancelToken = axios.CancelToken;
      this.cancelToken = CancelToken.source();

        try {
        const rasterIds = this.selectedRasters.map(r => r.id);
        const rasterNames = this.selectedRasters.map(r => r.name);
        
        // 修改API端点和请求参数格式
        const response = await axios.post(`${this.apiBaseUrl}/api/export/multi-raster-csv`, {
          raster_files: rasterIds,
          raster_names: rasterNames,
          align_method: this.form.alignMethod,
          file_name: this.form.fileName
          }, {
            responseType: 'blob',
            cancelToken: this.cancelToken.token,
            onDownloadProgress: (progressEvent) => {
              if (progressEvent.lengthComputable) {
              this.exportProgress = Math.round((progressEvent.loaded * 100) / progressEvent.total);
              this.progressText = `下载中... ${this.exportProgress}%`;
            }
          }
        });

          // 创建下载链接
        const blob = new Blob([response.data], { type: 'text/csv' });
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
          
        // 使用用户指定的文件名
        const fileName = this.form.fileName.endsWith('.csv') 
          ? this.form.fileName 
          : `${this.form.fileName}.csv`;
        
        link.download = fileName;
          
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(url);

        this.exportProgress = 100;
        this.exportStatus = 'success';
        this.progressText = 'CSV文件导出成功！';
        this.$message.success('CSV文件导出成功');

        } catch (error) {
          if (axios.isCancel(error)) {
          this.progressText = '导出已取消';
          this.$message.info('导出已取消');
          } else {
          console.error('导出失败:', error);
          this.exportStatus = 'exception';
          this.progressText = '导出失败: ' + (error.response?.data?.error || error.message);
          this.$message.error('导出失败: ' + (error.response?.data?.error || error.message));
          }
        } finally {
        this.exporting = false;
        this.cancelToken = null;
        }
    },

    cancelExport() {
      if (this.cancelToken) {
        this.cancelToken.cancel('用户取消导出');
      }
    },

    resetForm() {
      this.$refs.exportForm.resetFields();
      this.selectedRasters = [];
    }
  }
}
</script>

<style scoped>
.export-csv-container {
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

.selected-rasters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: flex-start;
  min-height: 100px;
  max-height: 200px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  padding: 10px 15px;
  background-color: #f5f7fa;
  overflow-y: auto;
}

.raster-tag {
  margin-bottom: 5px;
}

.no-selection {
  color: #909399;
  font-style: italic;
}

.progress-content {
  text-align: center;
}

.progress-text {
  margin-top: 15px;
  color: #606266;
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
  display: none;
}

.el-tree-node:hover .node-actions {
  display: inline-block;
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