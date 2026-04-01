<template>
  <!-- 数据集选择器, 卡片不浮动 -->
  <el-card class="data-card" shadow='never'>
    <div slot="header">
      <span>数据集</span>
      <el-button style="float: right; padding: 3px 0" type="text" @click="refreshDatasets">刷新</el-button>
    </div>
    <div class="data-list">
      <el-tree :data="hierarchicalDatasets" node-key="id" :props="{ label: 'name', children: 'children' }"
        @node-click="handleDatasetSelect" :expand-on-click-node="true" :show-checkbox="showCheckbox"
        @check-change="handleDatasetCheck" :check-strictly="selectionMode === 'single'" ref="datasetTree">
        <span class="custom-tree-node" slot-scope="{ node, data }">
          <span>
            <i v-if="data.isFolder" class="el-icon-folder" style="margin-right: 5px;"></i>
            <i v-else-if="data.format === 'csv'" class="el-icon-document-copy"
              style="margin-right: 5px; color: #67c23a;"></i>
            <i v-else-if="data.format === 'xls' || data.format === 'xlsx'" class="el-icon-document"
              style="margin-right: 5px; color: #409eff;"></i>
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
    <div class="selected-datasets" v-if="showCheckbox && selectedDatasets.length > 0">
      <div class="selected-datasets-title">已选择 {{ selectedDatasets.length }} 个数据集:</div>
      <div class="selected-dataset-item" v-for="(dataset, index) in selectedDatasets" :key="dataset.id">
        <span class="selected-dataset-name">
          <i v-if="dataset.type === 'raster'" class="el-icon-picture" style="margin-right: 5px;"></i>
          <i v-else-if="dataset.type === 'vector'" class="el-icon-map-location" style="margin-right: 5px;"></i>
          <i v-else class="el-icon-document" style="margin-right: 5px;"></i>
          {{ dataset.name }}
        </span>
      </div>
    </div>
  </el-card>

</template>

<script>
import axios from 'axios';

export default {
  name: 'DatasetSelector',
  data() {
    return {
      selectedDataset: null,
      selectedDatasets: [],
    };
  },
  props: {
    showCheckbox: {
      type: Boolean,
      default: false,
    },
    selectionMode: {
      type: String,
      default: 'multiple', // 'single' or 'multiple'
    },
    allowedTypes: {
      type: Array,
      default: () => [], // e.g., ['vector', 'raster', 'table']
    },
  },
  mounted() {
    this.fetchDatasets();
  },
  methods: {
    // 从后端获取数据集列表
    fetchDatasets() {
      // this.loading.datasets = true;

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
          // this.loading.datasets = false;
        })
        .catch(error => {
          console.error('获取数据集失败:', error);
          this.$message.error('获取数据集失败，请稍后重试');
          this.loading.datasets = false;
        });
    },
    refreshDatasets() {
      this.fetchDatasets();
      this.selectedDatasets = [];
    },

    handleDatasetSelect(dataset) {
      // 如果是单选模式且不是文件夹，则选中该数据集并加载
      if (this.selectionMode === 'single' && !dataset.isFolder && dataset.type !== 'folder') {
        // 检查是否允许选择该类型
        if (this.allowedTypes.length > 0 && !this.allowedTypes.includes(dataset.type)) {
          this.$message.warning(`不支持选择 ${dataset.type} 类型的数据集`);
          return;
        }
        this.selectedDataset = dataset;
        this.selectedDatasets = [dataset]; // 单选模式下只保留当前选中的数据集
        this.$emit('selected-datasets-change', this.selectedDatasets);
        this.loadDatasetToMap(dataset);
        return;
      }

      // 如果是文件夹，加载文件夹下所有数据 (多选模式或单选模式下的文件夹)
      if (dataset.isFolder || dataset.type === 'folder') {
        // this.$message.info(`正在加载文件夹: ${dataset.name}`);

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

    // // 获取数据集字段信息
    // fetchDatasetFields(dataset) {

    //   axios.get(`/datasets/${dataset.id}/fields`)
    //     .then(response => {
    //       this.availableFields = response.data;
    //       this.loading.fields = false;
    //     })
    //     .catch(error => {
    //       console.error('获取字段信息失败:', error);
    //       this.$message.error('获取字段信息失败');
    //     });
    // },

    handleDatasetCheck(data, checked) {
      // 检查是否是文件夹或不允许的类型
      if (((this.allowedTypes.length > 0 && !this.allowedTypes.includes(data.type)) && !(data.isFolder && this.selectionMode === 'multiple'))) {
        if (checked) {
          // 如果是勾选操作，则取消勾选并提示
          this.$refs.datasetTree.setChecked(data.id, false);
          this.$message.warning(`不支持选择 ${data.type || '文件夹'} 类型的数据集`);
        }
        return;
      }

      if (this.selectionMode === 'single') {
        // 单选模式
        if (checked) {
          if (data.isFolder) {
            // 如果是勾选操作，则取消勾选并提示
            this.$refs.datasetTree.setChecked(data.id, false);
            this.$message.warning(`当前为单选模式，不支持选择 ${data.type || '文件夹'} 类型的数据集`);
          }

          // 如果当前节点被勾选
          // 清空之前选中的数据集
          if (this.selectedDatasets.length > 0) {
            const prevSelected = this.selectedDatasets[0];
            if (prevSelected.id !== data.id) {
              this.$refs.datasetTree.setChecked(prevSelected.id, false);
            }
          }
          // 设置当前数据集为选中
          this.selectedDatasets = [data];
        } else {
          // 如果当前节点被取消勾选，且它是当前选中的节点
          if (this.selectedDatasets.length > 0 && this.selectedDatasets[0].id === data.id) {
            this.selectedDatasets = [];
          }
        }
      } else {
        // 多选模式
        if (checked) {
          // 如果是文件夹，加载文件夹下所有数据 (多选模式或单选模式下的文件夹)
          if (data.isFolder || data.type === 'folder') {

            // 开始加载文件夹中的所有数据集
            if (data.children && Array.isArray(data.children) && data.children.length > 0) {
              this.loadFolderDatasets(data.children, true);
            }

            return;
          } else {
            // 添加到选中列表，避免重复
            if (!this.selectedDatasets.find(item => item.id === data.id)) {
              this.selectedDatasets.push(data);
            }
          }

        } else {
          if (data.isFolder || data.type === 'folder') {

            // 开始卸载文件夹中的所有数据集
            if (data.children && Array.isArray(data.children) && data.children.length > 0) {
              this.unloadFolderDatasets(data.children);
            }

            return;
          } else {
            // 从选中列表中移除
            this.selectedDatasets = this.selectedDatasets.filter(item => item.id !== data.id);
          }

        }
      }
      // if (!checked) {
      //   // 如果取消勾选，更新选择图层
      //   this.selectedDatasets = this.selectedDatasets.filter(item => item.id !== data.id);

      // }
      // // 更新分析参数中的数据集列表 (如果需要)
      // this.analysisParams.datasets = this.selectedDatasets.map(dataset => dataset.id);

      // // 如果有选中的数据集，更新结果名称 (如果需要)
      // if (this.selectedDatasets.length > 0) {
      //   const firstDataset = this.selectedDatasets[0];
      //   let resultName = firstDataset.name;

      //   if (this.selectedDatasets.length > 1) {
      //     resultName += `_等${this.selectedDatasets.length}个数据集`;
      //   }
      // }

      // // 如果只选中了一个数据集，获取其字段信息 (如果需要)
      // if (this.selectedDatasets.length === 1) {
      //   this.fetchDatasetFields(this.selectedDatasets[0]);
      // } else {
      //   // 多个数据集时清空字段信息
      //   this.availableFields = [];
      // }
    },
    // 递归函数，用于加载文件夹中的所有数据集
    loadFolderDatasets(items, isTopLevel = true, unsupportedTypes = new Set()) {
      if (!items || !Array.isArray(items)) return;
      
      for (const item of items) {
        if (item.isFolder || item.type === 'folder') {
          // 如果是文件夹，递归加载其子项，传递unsupportedTypes集合
          if (item.children && Array.isArray(item.children) && item.children.length > 0) {
            this.loadFolderDatasets(item.children, false, unsupportedTypes);
          }
        } else {
          // 如果是数据集，添加到选中列表，避免重复
          if (this.allowedTypes.find(type => type === item.type) && !this.selectedDatasets.find(i =>  item.id === i.id )) {
            this.selectedDatasets.push(item);
          } else if (!item.isFolder && item.type) {
            // 如果不支持该类型，取消勾选并记录类型
            this.$refs.datasetTree.setChecked(item.id, false);
            unsupportedTypes.add(item.type);
          }
        }
      }

      // 只在顶层调用时显示消息
      if (isTopLevel && unsupportedTypes.size > 0) {
        const typeList = Array.from(unsupportedTypes).join('、');
        this.$message.warning(`文件夹中包含不支持的数据集类型：${typeList}`);
      }
    },

    unloadFolderDatasets(items) {
      if (!items || !Array.isArray(items)) return;

      for (const item of items) {
        if (item.isFolder || item.type === 'folder') {
          // 如果是文件夹，递归加载其子项
          if (item.children && Array.isArray(item.children) && item.children.length > 0) {
            this.unloadFolderDatasets(item.children);
          }
        } else {
          // this.selectedDatasets.find(i => { if(item.id === i.id){ console.log('remove dataset', item.id); return true; } });

          // 如果是数据集，添加到选中列表，避免重复
          this.selectedDatasets = this.selectedDatasets.filter(i => item.id !== i.id);
        }
      }
    },

    // 将数据集加载到地图上的方法
    loadDatasetToMap(dataset) {
      this.$emit('load-dataset', dataset);
    },

    // 取消选择数据集，要从el-tree中移除
    clearSelectedDatasets() {
      this.selectedDataset = null;
      this.selectedDatasets = [];
      this.$refs.datasetTree.setCheckedKeys([]);
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
  },

  watch: {
    selectedDatasets: {
      handler(newValue, oldValue) {
        this.$emit('selected-datasets-change', newValue);
      },
      deep: true,
    },
  }
}
</script>

<style scoped>
.data-card {
  margin-bottom: 15px;
  transition: all 0.3s;
  overflow: hidden;
}

.data-list {
  height: 100%;
  /* max-height: 250px; */
  overflow-y: auto;
}

.selected-datasets {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid #eee;
}

.selected-datasets-title {
  font-weight: bold;
  margin-bottom: 5px;
}

.selected-dataset-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 5px 0;
  border-bottom: 1px dashed #eee;
}

.selected-dataset-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>