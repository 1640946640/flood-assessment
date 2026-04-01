<template>
  <div class="raster-alignment">
    <el-card shadow="never" class="main-card">
      <div slot="header" class="card-header">
        <span>栅格对齐配置</span>
      </div>
      <el-form :model="alignmentParams" label-width="100px" size="small">
        <el-form-item label="输入目录">
          <el-select v-model="alignmentParams.inputDirectory" placeholder="请选择输入目录" style="width: 100%" @change="onInputDirectoryChange">
            <el-option 
              v-for="dir in directories" 
              :key="dir.id" 
              :label="dir.name" 
              :value="dir.id">
            </el-option>
          </el-select>
          <div class="input-tip">
            <i class="el-icon-info"></i> 选择要对齐的栅格文件所在目录（如：compare_data(7个文件)）
          </div>
        </el-form-item>
        
        <el-form-item label="模板文件">
          <el-input v-model="alignmentParams.templateFileName" placeholder="请选择模板栅格文件"
            readonly @click.native="showTemplateSelector"></el-input>
          <div class="input-tip">
            <i class="el-icon-info"></i> 点击文本框选择作为对齐基准的模板栅格文件
          </div>
        </el-form-item>
        
        <el-form-item label="输出目录">
          <el-input v-model="alignmentParams.outputDirectoryName" placeholder="请输入输出目录名称"></el-input>
          <div class="input-tip">
            <i class="el-icon-info"></i> 输入结果保存的目录名，将创建在data目录下
          </div>
        </el-form-item>
        
        <el-form-item label="重采样方法">
          <el-select v-model="alignmentParams.resampleMethod" placeholder="请选择重采样方法" style="width: 100%">
            <el-option label="最近邻插值" value="nearest"></el-option>
            <el-option label="双线性插值" value="bilinear"></el-option>
            <el-option label="三次卷积" value="cubic"></el-option>
            <el-option label="三次样条插值" value="cubic_spline"></el-option>
            <el-option label="Lanczos算法" value="lanczos"></el-option>
            <el-option label="平均值" value="average"></el-option>
            <el-option label="众数" value="mode"></el-option>
          </el-select>
        </el-form-item>
        
        <el-form-item>
          <el-button type="primary" @click="runAlignment" :loading="loading">开始对齐</el-button>
          <el-button @click="resetForm">重置</el-button>
        </el-form-item>
      </el-form>

      <!-- 结果展示 -->
      <div v-if="currentResult" class="results-section">
        <div class="results-header">
          <h3>对齐结果</h3>
          <el-button size="small" type="primary" icon="el-icon-download" @click="downloadResult(currentResult)">下载结果</el-button>
        </div>

        <div class="statistics-cards">
          <div class="stat-card">
            <div class="stat-value">{{ currentResult.total_files }}</div>
            <div class="stat-label">总文件数</div>
          </div>
          <div class="stat-card success">
            <div class="stat-value">{{ currentResult.success_count }}</div>
            <div class="stat-label">成功</div>
          </div>
          <div class="stat-card error">
            <div class="stat-value">{{ currentResult.error_count }}</div>
            <div class="stat-label">失败</div>
          </div>
        </div>

        <div class="result-files-section">
          <h4>成功对齐的文件:</h4>
          <el-table :data="resultFiles" style="width: 100%" size="small" max-height="400">
            <el-table-column prop="name" label="文件名" width="280"></el-table-column>
            <el-table-column prop="status" label="状态" width="80">
              <template slot-scope="scope">
                <el-tag :type="scope.row.status === '成功' ? 'success' : 'danger'" size="mini">{{ scope.row.status }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="outputPath" label="输出路径" show-overflow-tooltip></el-table-column>
          </el-table>
        </div>
      </div>

      <!-- 历史结果列表 -->
      <div v-if="results.length > 0 && !currentResult" class="results-section">
        <h3>历史对齐结果</h3>
        <el-table :data="results" style="width: 100%">
          <el-table-column prop="name" label="名称" width="180"></el-table-column>
          <el-table-column prop="createdAt" label="创建时间" width="180"></el-table-column>
          <el-table-column label="操作">
            <template slot-scope="scope">
              <el-button size="mini" type="primary" @click="downloadResult(scope.row)">下载</el-button>
              <el-button size="mini" type="success" @click="viewResult(scope.row)">查看</el-button>
              <el-button size="mini" type="warning" @click="compareResult(scope.row)">比较</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-card>

    <!-- 模板文件选择对话框 -->
    <el-dialog title="选择模板文件" :visible.sync="templateSelectorVisible" width="70%">
      <div class="dataset-dialog-content">
        <div v-if="loadingTemplateFiles" class="loading-overlay">
          <i class="el-icon-loading"></i>
          <span>正在加载文件列表...</span>
        </div>
        
        <el-table
          v-if="!loadingTemplateFiles"
          :data="templateFiles"
          height="400"
          @row-click="handleTemplateFileSelect"
          row-class-name="template-file-row"
          highlight-current-row
          ref="templateTable">
          <el-table-column type="radio" width="55"></el-table-column>
          <el-table-column prop="name" label="文件名"></el-table-column>
          <el-table-column prop="size" label="尺寸" width="120"></el-table-column>
          <el-table-column prop="format" label="格式" width="80"></el-table-column>
          <el-table-column label="状态" width="100">
            <template slot-scope="scope">
              <span v-if="isTemplateSelected(scope.row)" style="color: #409EFF">
                <i class="el-icon-check"></i> 已选择
              </span>
            </template>
          </el-table-column>
        </el-table>
        
        <div v-if="!loadingTemplateFiles && templateFiles.length === 0" class="no-files-tip">
          <i class="el-icon-warning-outline"></i>
          <span>当前目录下没有可用的栅格文件</span>
        </div>
      </div>
      <div slot="footer" class="dialog-footer">
        <el-button @click="templateSelectorVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmTemplateSelection" :disabled="!tempSelectedTemplate">确定</el-button>
      </div>
    </el-dialog>

    <!-- 比较对话框 -->
    <el-dialog title="对齐前后比较" :visible.sync="compareVisible" width="80%">
      <div class="compare-container">
        <div class="compare-item">
          <h4>对齐前</h4>
          <img v-if="beforeImageUrl" :src="beforeImageUrl" class="compare-image" />
        </div>
        <div class="compare-item">
          <h4>对齐后</h4>
          <img v-if="afterImageUrl" :src="afterImageUrl" class="compare-image" />
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script>
import axios from 'axios';

export default {
  name: 'RasterAlignment',
  data() {
    return {
      apiBaseUrl: process.env.VUE_APP_API_BASE_URL || '',
      alignmentParams: {
        inputDirectory: '',
        inputDirectoryName: '',
        templateFile: null,
        templateFileName: '',
        outputDirectoryName: '',
        resampleMethod: 'bilinear'
      },
      loading: false,
      loadingFiles: false,
      loadingTemplateFiles: false,
      templateSelectorVisible: false,
      tempSelectedTemplate: null,
      results: [],
      compareVisible: false,
      beforeImageUrl: '',
      afterImageUrl: '',
      folderData: [],
      directories: [], // 存储data目录下的子目录
      templateFiles: [], // 存储当前选中目录下的模板文件
      defaultProps: {
        children: 'children',
        label: 'name',
        isLeaf: 'isLeaf'
      },
      currentResult: null, // 当前显示的详细结果
      resultFiles: [] // 当前结果的文件列表
    };
  },
  created() {
    this.getDirectories();
  },
  methods: {
    // 获取data目录下的子目录
    async getDirectories() {
      try {
        // 使用alignment API的get-directories端点获取目录列表
        const response = await axios.get(`${this.apiBaseUrl}/api/alignment/get-directories`);
        if (response.data.success) {
          // 转换为选择框需要的格式
          this.directories = response.data.directories.map(dir => ({
            id: dir.path,
            name: `${dir.name}(${dir.tif_count}个文件)`
          }));
        } else {
          this.$message.error('获取目录列表失败');
        }
      } catch (error) {
        console.error('获取目录列表失败:', error);
        this.$message.error('获取目录列表失败');
      }
    },
    
    // 输入目录变更时获取该目录下的TIF文件
    async onInputDirectoryChange(value) {
      // 清空已选择的模板文件
      this.alignmentParams.templateFile = null;
      this.alignmentParams.templateFileName = '';
      
      // 更新输入目录名称
      const selectedDir = this.directories.find(dir => dir.id === value);
      if (selectedDir) {
        this.alignmentParams.inputDirectoryName = selectedDir.name;
        
        // 自动生成输出目录名称
        if (!this.alignmentParams.outputDirectoryName) {
          const dirName = selectedDir.name.split('(')[0];
          this.alignmentParams.outputDirectoryName = `${dirName}_aligned`;
        }
      }
    },
    
    // 显示模板文件选择器
    async showTemplateSelector() {
      if (!this.alignmentParams.inputDirectory) {
        this.$message.warning('请先选择输入目录');
        return;
      }
      
      this.loadingTemplateFiles = true;
      this.templateSelectorVisible = true;
      this.tempSelectedTemplate = null;
      
      try {
        // 获取选中目录下的栅格文件
        const response = await axios.post(`${this.apiBaseUrl}/api/alignment/get-raster-files`, {
          directory_path: this.alignmentParams.inputDirectory
        });
        
        if (response.data.success) {
          this.templateFiles = response.data.raster_files.map(file => ({
            name: file.filename,
            path: file.path,
            size: `${file.info?.width || 0} x ${file.info?.height || 0}`,
            format: 'TIF'
          }));
        } else {
          this.$message.error('获取模板文件列表失败');
        }
      } catch (error) {
        console.error('获取模板文件列表失败:', error);
        this.$message.error('获取模板文件列表失败');
      } finally {
        this.loadingTemplateFiles = false;
      }
    },
    
    // 处理模板文件选择
    handleTemplateFileSelect(row) {
      // 设置当前选中行
      this.tempSelectedTemplate = row;
      // 强制表格更新当前选中行的样式
      this.$nextTick(() => {
        this.$refs.templateTable.setCurrentRow(row);
      });
    },
    
    // 确认模板文件选择
    confirmTemplateSelection() {
      if (!this.tempSelectedTemplate) {
        this.$message.warning('请选择一个模板文件');
        return;
      }
      
      this.alignmentParams.templateFile = this.tempSelectedTemplate.path;
      this.alignmentParams.templateFileName = this.tempSelectedTemplate.name;
      this.templateSelectorVisible = false;
    },
    
    isTemplateSelected(file) {
      return this.tempSelectedTemplate && this.tempSelectedTemplate.path === file.path;
    },
    
    async runAlignment() {
      if (!this.alignmentParams.inputDirectory || 
          !this.alignmentParams.templateFile || 
          !this.alignmentParams.outputDirectoryName || 
          !this.alignmentParams.resampleMethod) {
        this.$message.error('请填写所有必要参数');
        return;
      }

      // 创建输出目录路径
      const outputDirectory = `data/${this.alignmentParams.outputDirectoryName}`;

      this.loading = true;
      try {
        const response = await axios.post(`${this.apiBaseUrl}/api/alignment/align-rasters`, {
          input_directory: this.alignmentParams.inputDirectory,
          template_file: this.alignmentParams.templateFile,
          output_directory: outputDirectory,
          resampling_method: this.alignmentParams.resampleMethod
        });

        if (response.data.success) {
          // 构建结果对象
          const resultObj = {
            id: new Date().getTime(), // 使用时间戳作为ID
            name: `对齐结果_${this.alignmentParams.inputDirectoryName.split('(')[0]}_${new Date().toLocaleString()}`,
            createdAt: new Date().toLocaleString(),
            success_count: response.data.success_count,
            error_count: response.data.error_count,
            total_files: response.data.total_files,
            output_directory: outputDirectory
          };
          
          // 处理文件列表
          this.resultFiles = [];
          
          // 添加成功的文件
          if (response.data.results && response.data.results.length > 0) {
            response.data.results.forEach(file => {
              this.resultFiles.push({
                name: file.filename,
                status: '成功',
                outputPath: file.output_path
              });
            });
          }
          
          // 添加失败的文件
          if (response.data.errors && response.data.errors.length > 0) {
            response.data.errors.forEach(file => {
              this.resultFiles.push({
                name: file.filename,
                status: '失败',
                outputPath: '-'
              });
            });
          }
          
          // 更新当前结果和历史结果
          this.currentResult = resultObj;
          this.results.unshift(resultObj);
          
          this.$message.success(`栅格对齐完成，成功: ${response.data.success_count}, 失败: ${response.data.error_count}`);
        } else {
          this.$message.error(`对齐失败: ${response.data.error}`);
        }
      } catch (error) {
        console.error('栅格对齐失败:', error);
        this.$message.error(`栅格对齐失败: ${error.response?.data?.error || error.message}`);
      } finally {
        this.loading = false;
      }
    },
    
    resetForm() {
      this.alignmentParams = {
        inputDirectory: '',
        inputDirectoryName: '',
        templateFile: null,
        templateFileName: '',
        outputDirectoryName: '',
        resampleMethod: 'bilinear'
      };
      this.currentResult = null; // 重置当前详细结果
      this.resultFiles = []; // 重置文件列表
    },
    
    async downloadResult(result) {
      try {
        // 下载ZIP格式的对齐结果
        const response = await axios.post(`${this.apiBaseUrl}/api/alignment/download-aligned`, {
          output_directory: result.output_directory
        }, {
          responseType: 'blob'
        });
        
        // 创建下载链接
        const url = window.URL.createObjectURL(new Blob([response.data]));
        const link = document.createElement('a');
        link.href = url;
        link.setAttribute('download', `aligned_rasters_${new Date().getTime()}.zip`);
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(url);
      } catch (error) {
        console.error('下载失败:', error);
        this.$message.error('下载对齐结果失败');
      }
    },
    
    viewResult(result) {
      this.currentResult = result;
      // 尝试从后端获取详细文件列表
      this.fetchResultFiles(result.output_directory);
    },
    
    async fetchResultFiles(outputDirectory) {
      try {
        // 获取对齐结果文件列表
        const response = await axios.post(`${this.apiBaseUrl}/api/alignment/get-aligned-files`, {
          output_directory: outputDirectory
        });
        
        if (response.data.success) {
          this.resultFiles = response.data.files.map(file => ({
            name: file.filename,
            status: '成功', // 由于已对齐完成，默认为成功
            outputPath: file.path
          }));
        } else {
          this.resultFiles = [];
          this.$message.warning('无法获取文件列表信息');
        }
      } catch (error) {
        console.error('获取文件列表失败:', error);
        this.$message.error('获取文件列表失败');
        this.resultFiles = [];
      }
    },
    
    compareResult(result) {
      this.$message.info('比较功能开发中');
    }
  }
}
</script>

<style scoped>
.raster-alignment {
  height: 100%;
  padding: 20px;
}

.main-card {
  max-width: 900px;
  margin: 0 auto;
  height: 100%;
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
  justify-content: space-around;
  margin-bottom: 15px;
  padding: 10px;
  background-color: #f5f7fa;
  border-radius: 4px;
}

.stat-card {
  text-align: center;
  padding: 10px;
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

.stat-card.success .stat-value {
  color: #67C23A;
}

.stat-card.error .stat-value {
  color: #F56C6C;
}

.result-files-section h4 {
  margin-bottom: 10px;
  font-size: 16px;
}

.result-files-section .el-table {
  border: 1px solid #ebeef5;
  border-radius: 4px;
}

.result-files-section .el-table th {
  background-color: #f5f7fa;
  color: #303133;
  font-weight: bold;
}

.result-files-section .el-table td {
  padding: 8px 12px;
}

.result-files-section .el-table .el-tag {
  margin-right: 5px;
}

h3 {
  margin-bottom: 15px;
  font-size: 18px;
}

.compare-container {
  display: flex;
  justify-content: space-between;
  gap: 20px;
}

.compare-item {
  flex: 1;
  text-align: center;
}

.compare-image {
  max-width: 100%;
  max-height: 50vh;
  border: 1px solid #eee;
}

.dataset-dialog-content {
  width: 100%;
  display: flex;
  flex-direction: column;
  position: relative;
  min-height: 300px;
}

.template-file-row:hover {
  background-color: #f5f7fa;
  cursor: pointer;
}

.no-files-tip {
  text-align: center;
  color: #909399;
  font-size: 14px;
  margin-top: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.no-files-tip i {
  font-size: 20px;
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