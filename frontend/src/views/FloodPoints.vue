<template>
  <div class="flood-points">
    <el-card class="control-panel">
      <div slot="header">
        <span>易涝点识别参数设置</span>
      </div>
      <el-form :model="form" label-width="120px" size="small">
        <el-form-item label="DEM数据">
          <el-upload
            class="dem-uploader"
            action="/api/flood-points/upload-dem"
            :on-success="handleDemUploadSuccess"
            :before-upload="beforeDemUpload"
            accept=".tif,.img"
            :limit="1">
            <el-button type="primary">选择DEM文件</el-button>
            <div slot="tip" class="el-upload__tip">请上传GeoTIFF格式的DEM数据</div>
          </el-upload>
        </el-form-item>
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
        <el-form-item>
          <el-button type="primary" @click="calculateFloodPoints" :loading="calculating">
            开始计算
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card class="result-panel" v-if="hasResults">
      <div slot="header">
        <span>计算结果</span>
      </div>
      <div class="result-content">
        <div class="statistics">
          <el-descriptions :column="2" border>
            <el-descriptions-item label="识别的易涝点数量">
              {{ results.pointCount }}
            </el-descriptions-item>
            <el-descriptions-item label="平均高程">
              {{ results.averageElevation }} m
            </el-descriptions-item>
          </el-descriptions>
        </div>
        <div class="map-container">
          <!-- 地图容器将在后续添加 -->
        </div>
      </div>
    </el-card>
  </div>
</template>

<script>
export default {
  name: 'FloodPoints',
  data() {
    return {
      form: {
        accumulationThreshold: 100,
        slopeThreshold: 2.0
      },
      calculating: false,
      hasResults: false,
      results: {
        pointCount: 0,
        averageElevation: 0
      },
      demFile: null
    }
  },
  methods: {
    handleDemUploadSuccess(response) {
      if (response.success) {
        this.demFile = response.data.filename
        this.$message.success('DEM文件上传成功')
      } else {
        this.$message.error(response.message || '上传失败')
      }
    },
    beforeDemUpload(file) {
      const isValidFormat = ['.tif', '.img'].some(ext => 
        file.name.toLowerCase().endsWith(ext)
      )
      if (!isValidFormat) {
        this.$message.error('请上传GeoTIFF格式的DEM数据')
        return false
      }
      return true
    },
    async calculateFloodPoints() {
      if (!this.demFile) {
        this.$message.warning('请先上传DEM数据')
        return
      }

      this.calculating = true
      try {
        const response = await this.$http.post('/api/flood-points/calculate', {
          demFile: this.demFile,
          accumulationThreshold: this.form.accumulationThreshold,
          slopeThreshold: this.form.slopeThreshold
        })

        if (response.data.success) {
          this.results = response.data.results
          this.hasResults = true
          this.$message.success('易涝点计算完成')
        } else {
          this.$message.error(response.data.message || '计算失败')
        }
      } catch (error) {
        this.$message.error('计算过程发生错误')
        console.error(error)
      } finally {
        this.calculating = false
      }
    }
  }
}
</script>

<style scoped>
.flood-points {
  padding: 20px;
  height: 100%;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.control-panel {
  flex: 0 0 auto;
}

.result-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.result-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.statistics {
  flex: 0 0 auto;
}

.map-container {
  flex: 1;
  min-height: 400px;
  background-color: #f5f7fa;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
}

.dem-uploader {
  display: inline-block;
}

.el-upload__tip {
  margin-top: 5px;
  color: #909399;
}
</style> 