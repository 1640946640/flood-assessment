<template>
  <!-- 分析结果图片选择器 -->
  <el-card class="data-card" shadow='never'>
    <div slot="header">
      <span>{{ title || '图片列表' }}</span>
      <el-button style="float: right; padding: 3px 0" type="text" @click="refreshImages">刷新</el-button>
    </div>
    <div class="image-list" v-loading="loading.images">
      <div v-if="images.length === 0" class="no-images">
        {{ emptyText || '暂无图片' }}
      </div>
      <div v-else class="image-grid">
        <div v-for="(image, index) in images" :key="image.id" class="image-item" @click="previewImage(image)">
          <div class="image-container">
            <img :src="image.previewUrl" :alt="image.name" class="image-thumbnail" />
            <div class="image-overlay">
              <i class="el-icon-zoom-in"></i>
            </div>
          </div>
          <div class="image-name">{{ image.name }}</div>
        </div>
      </div>
    </div>

    <!-- 图片预览对话框 -->
    <el-dialog :visible.sync="dialogVisible" :title="currentImage ? currentImage.name : ''" width="80%" append-to-body>
      <div class="image-preview-container">
        <img v-if="currentImage" :src="currentImage.url" :alt="currentImage.name" class="preview-image" />
      </div>
      <div class="image-info" v-if="currentImage">
        <p><strong>文件名:</strong> {{ currentImage.name }}</p>
        <p><strong>创建时间:</strong> {{ currentImage.createTime }}</p>
        <p><strong>文件大小:</strong> {{ formatFileSize(currentImage.size) }}</p>
      </div>
    </el-dialog>
  </el-card>
</template>

<script>
import axios from 'axios';

export default {
  name: 'ImgSelector',
  props: {
    // 图片资源路径
    path: {
      type: String,
      required: true
    },
    // 卡片标题
    title: {
      type: String,
      default: ''
    },
    // 空数据提示文本
    emptyText: {
      type: String,
      default: ''
    }
  },
  data() {
    return {
      images: [],
      loading: {
        images: false
      },
      dialogVisible: false,
      currentImage: null
    };
  },
  watch: {
    path: {
      handler(newPath) {
        this.fetchImages();
      },
      immediate: true
    }
  },
  methods: {
    // 从后端获取图片列表
    fetchImages() {
      this.loading.images = true;

      // 使用axios请求后端API
      axios.get(`/api/datasets/images/${this.path}`)
        .then(response => {
          console.log('图片列表响应:', response);
          // 确保数据是正确的格式
          let images = response.data.data || [];

          // 处理图片数据
          this.images = images.map(img => ({
            ...img,
            previewUrl: `/api/datasets/images/${img.id}/preview`,
            url: `/api/datasets/images/${img.id}`
          }));

          this.loading.images = false;
        })
        .catch(error => {
          console.error('获取图片失败:', error);
          this.$message.error('获取图片失败，请稍后重试');
          this.loading.images = false;
        });
    },
    refreshImages() {
      this.fetchImages();
    },
    // 预览图片
    previewImage(image) {
      this.currentImage = image;
      this.dialogVisible = true;
    },
    // 格式化文件大小
    formatFileSize(size) {
      if (size < 1024) {
        return size + ' B';
      } else if (size < 1024 * 1024) {
        return (size / 1024).toFixed(2) + ' KB';
      } else if (size < 1024 * 1024 * 1024) {
        return (size / (1024 * 1024)).toFixed(2) + ' MB';
      } else {
        return (size / (1024 * 1024 * 1024)).toFixed(2) + ' GB';
      }
    }
  }
}
</script>

<style scoped>
.data-card {
  margin-bottom: 15px;
  transition: all 0.3s;
  overflow: hidden;
}

.image-list {
  height: 100%;
  overflow-y: auto;
}

.no-images {
  padding: 20px;
  text-align: center;
  color: #909399;
}

.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 10px;
  padding: 10px;
}

.image-item {
  cursor: pointer;
  transition: all 0.3s;
  border-radius: 4px;
  overflow: hidden;
}

.image-item:hover {
  transform: translateY(-3px);
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
}

.image-container {
  position: relative;
  width: 100%;
  padding-top: 75%; /* 4:3 宽高比 */
  overflow: hidden;
}

.image-thumbnail {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.image-overlay {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background-color: rgba(0, 0, 0, 0.3);
  display: flex;
  justify-content: center;
  align-items: center;
  opacity: 0;
  transition: opacity 0.3s;
}

.image-overlay i {
  color: white;
  font-size: 24px;
}

.image-container:hover .image-overlay {
  opacity: 1;
}

.image-name {
  padding: 5px;
  text-align: center;
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.image-preview-container {
  display: flex;
  justify-content: center;
  align-items: center;
  max-height: 70vh;
  overflow: hidden;
}

.preview-image {
  max-width: 100%;
  max-height: 70vh;
  object-fit: contain;
}

.image-info {
  margin-top: 15px;
  padding-top: 15px;
  border-top: 1px solid #ebeef5;
}
</style>