<template>
  <div class="assessment-result-cards">
    <el-card class="assessment-card">
      <div slot="header" class="assessment-overview">
        <span class="assessment-title">{{ result.name }}</span>
        <el-tag :type="getTypeTag(result.type)" size="small">
          {{ getTypeName(result.type) }}
        </el-tag>
      </div>
      
      <div class="assessment-results-content">
        <!-- 基本信息 -->
        <div class="assessment-info">
          <p><strong>创建时间：</strong>{{ result.createdAt || result.createTime }}</p>
          <p><strong>描述：</strong>{{ result.description }}</p>
        </div>

        <!-- 参数信息 -->
        <div v-if="result.parameters" class="assessment-parameters">
          <h4>评估参数</h4>
          <div class="parameter-list">
            <div v-for="(value, key) in flattenParameters(result.parameters)" :key="key" class="parameter-item">
              <span class="parameter-label">{{ formatParameterLabel(key) }}：</span>
              <span class="parameter-value">{{ formatParameterValue(value) }}</span>
            </div>
          </div>
        </div>

        <!-- 统计信息 -->
        <div v-if="result.statistics" class="assessment-statistics">
          <h4>统计信息</h4>
          <el-row :gutter="16">
            <el-col :span="8" v-if="result.statistics.min !== undefined">
              <div class="stat-item">
                <div class="stat-label">最小值</div>
                <div class="stat-value">{{ formatNumber(result.statistics.min) }}</div>
              </div>
            </el-col>
            <el-col :span="8" v-if="result.statistics.max !== undefined">
              <div class="stat-item">
                <div class="stat-label">最大值</div>
                <div class="stat-value">{{ formatNumber(result.statistics.max) }}</div>
              </div>
            </el-col>
            <el-col :span="8" v-if="result.statistics.mean !== undefined">
              <div class="stat-item">
                <div class="stat-label">平均值</div>
                <div class="stat-value">{{ formatNumber(result.statistics.mean) }}</div>
              </div>
            </el-col>
          </el-row>
          <!-- 添加暴露性模型统计信息 -->
          <div v-if="result.type === 'exposure'">
            <el-descriptions :column="2" size="small" border>
              <el-descriptions-item label="暴露面积">
                {{ formatNumber(result.statistics.flooded_area_km2) }} km² 
                ({{ Math.round(result.statistics.flooded_area_m2).toLocaleString() }} m²)
              </el-descriptions-item>
              <el-descriptions-item label="暴露区域比例">
                {{ (result.statistics.flooded_area_ratio * 100).toFixed(2) }}%
              </el-descriptions-item>
              <el-descriptions-item label="暴露像素数">
                {{ result.statistics.flooded_pixel_count?.toLocaleString() }} / 
                {{ result.statistics.total_pixel_count?.toLocaleString() }}
                (像素大小: {{ result.statistics.pixel_area_m2?.toFixed(2) || 0 }} m²)
              </el-descriptions-item>
              <el-descriptions-item label="暴露值最小/最大/均值/标准差">
                {{ formatNumber(result.statistics.exposure_min) }} / {{ formatNumber(result.statistics.exposure_max) }} / {{ formatNumber(result.statistics.exposure_mean) }} / {{ formatNumber(result.statistics.exposure_std) }}
              </el-descriptions-item>
              <el-descriptions-item v-if="result.statistics.use_slope_model" label="P0点坐标">{{ result.statistics.p0_coord }}</el-descriptions-item>
              <el-descriptions-item v-if="result.statistics.use_slope_model" label="P0点水位">{{ result.statistics.p0_water_level }}</el-descriptions-item>
              <el-descriptions-item v-if="result.statistics.use_slope_model" label="P1点坐标">{{ result.statistics.p1_coord }}</el-descriptions-item>
              <el-descriptions-item v-if="result.statistics.use_slope_model" label="P1点水位">{{ result.statistics.p1_water_level }}</el-descriptions-item>
              <el-descriptions-item v-if="result.statistics.use_slope_model" label="P0-P1距离">{{ result.statistics.p0_p1_distance }}</el-descriptions-item>
              <el-descriptions-item v-if="result.statistics.use_slope_model" label="坡度(PS)">{{ result.statistics.slope_ps }}</el-descriptions-item>
            </el-descriptions>
          </div>
          <!-- 添加淹没区域统计信息（仅危险性模型显示） -->
          <div v-if="result.type === 'hazard' && result.statistics.flooded_area_km2 !== undefined" class="flood-area-stats">
            <h4>淹没区域统计</h4>
            <!-- 调试信息 -->
            <div style="background: #f0f0f0; padding: 10px; margin-bottom: 10px; font-size: 12px;">
              <strong>调试信息:</strong><br>
              淹没面积: {{ result.statistics.flooded_area_km2 }}<br>
              最大水深: {{ result.statistics.max_water_depth }}<br>
              淹没像素数: {{ result.statistics.flooded_pixel_count }}<br>
              像素面积: {{ result.statistics.pixel_area_m2 }}
            </div>
            <el-descriptions :column="2" size="small" border>
              <el-descriptions-item label="淹没面积">
                {{ formatNumber(result.statistics.flooded_area_km2) }} km² 
                ({{ Math.round(result.statistics.flooded_area_m2).toLocaleString() }} m²)
              </el-descriptions-item>
              <el-descriptions-item label="淹没区域比例">
                {{ (result.statistics.flooded_area_ratio * 100).toFixed(2) }}%
              </el-descriptions-item>
              <el-descriptions-item label="最大水深">
                {{ result.statistics.max_water_depth.toFixed(2) }} 米
              </el-descriptions-item>
              <el-descriptions-item label="淹没像素数">
                {{ result.statistics.flooded_pixel_count?.toLocaleString() }} / 
                {{ result.statistics.total_pixel_count?.toLocaleString() }}
                (像素大小: {{ result.statistics.pixel_area_m2?.toFixed(2) || 0 }} m²)
              </el-descriptions-item>
            </el-descriptions>
          </div>
        </div>

        <!-- 文件列表 -->
        <div v-if="result.files && result.files.length > 0" class="assessment-files">
          <h4>结果文件</h4>
          <div class="file-list">
            <div v-for="file in result.files" :key="file.id" class="file-item">
              <el-button 
                type="text" 
                size="small" 
                @click="downloadFile(file)"
                icon="el-icon-download">
                {{ file.name }}.{{ file.format }}
              </el-button>
              <el-tag size="mini" :type="getFileTypeTag(file.format)">{{ file.format.toUpperCase() }}</el-tag>
            </div>
          </div>
        </div>

        <!-- 图表展示区域 -->
        <div v-if="showChart" class="assessment-chart">
          <h4>结果可视化</h4>
          
          <!-- 综合影响评估的多图展示 -->
          <div v-if="result.type === 'comprehensive' && previewSrcList && previewSrcList.length > 1" class="comprehensive-charts">
            <div class="chart-grid">
              <div v-for="(src, index) in previewSrcList" :key="index" class="chart-item">
                <div class="chart-title">{{ getChartTitle(index) }}</div>
                <el-image 
                  :preview-src-list="previewSrcList"
                  :src="src" 
                  :alt="getChartTitle(index)" 
                  class="chart-thumbnail"
                  fit="cover"
                  @error="handleImageError(index, $event)">
                  <div slot="error" class="image-error">
                    <i class="el-icon-picture-outline"></i>
                    <p>{{ getImageErrorMessage(index) }}</p>
                  </div>
                </el-image>
              </div>
            </div>
            <p class="chart-note">💡 点击任意图片可查看大图并浏览所有结果</p>
          </div>
          
          <!-- 其他评估类型的单图展示 -->
          <div v-else-if="previewSrcList && previewSrcList.length > 0" class="chart-placeholder">
            <el-image :preview-src-list="previewSrcList"
            :src="previewSrcList[0]" alt="预览图表" class="interpolation-image" />
            <p v-if="previewSrcList.length > 1" class="chart-note">💡 点击图片查看所有 {{ previewSrcList.length }} 张结果图</p>
          </div>
        </div>

        <!-- 结果解释 -->
        <div class="assessment-explanation">
          <h4>结果解释</h4>
          <p>{{ getResultExplanation() }}</p>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script>
export default {
  name: 'AssessmentResultCards',
  props: {
    result: {
      type: Object,
      required: true
    },
    apiBaseUrl: {
      type: String,
      default: 'http://localhost:5000'
    }
  },
  computed: {
    showChart() {
      // 可以根据结果类型决定是否显示图表
      return this.result.type && ['hazard', 'exposure', 'value', 'sensitivity', 'resistance', 'mitigation', 'comprehensive'].includes(this.result.type);

    },
    previewSrcList() {
      if (this.result.preview) {
        const list = [];
        this.result.preview.forEach(element => {
          element = `${this.apiBaseUrl}${element}`
          list.push(element)
        });
        return list;
      }
    }
  },
  methods: {
    // 获取类型标签样式
    getTypeTag(type) {
      const tagMap = {
        'hazard': 'danger',
        'exposure': 'warning', 
        'value': 'success',
        'sensitivity': 'info',
        'prevention': 'primary',
        'mitigation': 'primary',
        'comprehensive': 'danger'
      };
      return tagMap[type] || 'info';
    },

    // 获取类型名称
    getTypeName(type) {
      const nameMap = {
        'hazard': '危险性评估',
        'exposure': '暴露性评估',
        'value': '价值密度评估',
        'sensitivity': '敏感性评估',
        'prevention': '防灾性评估',
        'mitigation': '减灾性评估',
        'comprehensive': '综合评估'
      };
      return nameMap[type] || type;
    },

    // 获取文件类型标签
    getFileTypeTag(format) {
      const tagMap = {
        'geojson': 'success',
        'tif': 'warning',
        'shp': 'info'
      };
      return tagMap[format] || 'info';
    },

    // 扁平化参数对象
    flattenParameters(params, prefix = '') {
      let result = {};
      for (let key in params) {
        if (typeof params[key] === 'object' && params[key] !== null && !Array.isArray(params[key])) {
          Object.assign(result, this.flattenParameters(params[key], prefix + key + '_'));
        } else {
          result[prefix + key] = params[key];
        }
      }
      return result;
    },

    // 格式化参数标签
    formatParameterLabel(key) {
      const labelMap = {
        'water_level': '淹没水位高程',
        'dem_dataset_id': 'DEM数据集',
        'boundary_dataset_id': '边界数据集',
        'hazard_dataset_id': '危险性数据集',
        'population_dataset_id': '人口热力图数据集',
        'building_dataset_id': '建筑面积数据集',
        'other_dataset_id': '其他数据集',
        'total_population': '总人口数T',
        'weights_r1': '权重r1',
        'weights_r2': '权重r2', 
        'weights_r3': '权重r3',
        'economic_values_j_pop': '经济标准J人',
        'economic_values_j_building': '经济标准J建筑',
        'economic_values_j_other': '经济标准J其他'
      };
      return labelMap[key] || key;
    },

    // 格式化参数值
    formatParameterValue(value) {
      if (typeof value === 'number') {
        return this.formatNumber(value);
      }
      return value;
    },

    // 格式化数字
    formatNumber(num) {
      if (typeof num !== 'number') return num;
      return num.toFixed(3);
    },

    // 下载文件
    downloadFile(file) {
      const url = file.download_url.startsWith('http') ? file.download_url : `${this.apiBaseUrl}${file.download_url}`;
      window.open(url, '_blank');
    },

    // 获取综合影响评估中每张图片的标题
    getChartTitle(index) {
      const titles = [
        'I1 - 灾害影响基值',
        'I2 - 工程防灾减量值', 
        'I3 - 工程减灾减量值',
        'IDFi - 综合影响分布',
        'IPIi - 影响强度指数'
      ];
      return titles[index] || `图表 ${index + 1}`;
    },

    // 处理图片加载错误
    handleImageError(index, event) {
      console.warn(`图片加载失败: ${this.getChartTitle(index)}`, event);
    },

    // 获取图片错误信息
    getImageErrorMessage(index) {
      const messages = [
        'I1图生成中...',
        'I2图生成中...',
        'I3数据无变化',
        'IDFi图生成中...',
        'IPIi图生成中...'
      ];
      return messages[index] || '图片加载失败';
    },

    // 获取结果解释
    getResultExplanation() {
      const explanations = {
        'hazard': '危险性评估结果反映了研究区域内洪涝灾害的潜在威胁程度。数值越高表示该区域面临的洪涝风险越大，需要重点关注和防护。',
        'exposure': '暴露性评估结果显示了研究区域内人员、财产等暴露在洪涝灾害威胁下的程度。高暴露性区域在灾害发生时可能面临更大的损失。',
        'value': '价值密度评估结果基于人口热力图、建筑面积和其他要素，通过加权计算得出各区域的综合价值密度。结果反映了研究区域内经济价值的空间分布，高价值密度区域在遭受洪涝灾害时可能造成更大的经济损失，应优先进行防护。',
        'sensitivity': '敏感性评估结果表明了不同区域对洪涝灾害的敏感程度，考虑了人口结构、社会经济条件等因素。',
        'prevention': '防灾性评估结果评价了研究区域的工程防灾能力，包括堤防、排水系统等基础设施的防护效果。',
        'mitigation': '减灾性评估结果反映了研究区域的灾害应对和恢复能力，包括应急设施、救援能力等。',
        'comprehensive': '综合评估结果整合了H、E、V、S、R、M六个模型，通过I1（灾害影响基值）、I2（工程防灾减量值）、I3（工程减灾减量值）的计算，得出IDFi和IPIi综合影响分析结果。IDFi = I1-I2-I3，IPIi = (I1-I2-I3)/I1，提供全面的洪涝灾害影响分析。'
      };
      return explanations[this.result.type] || '该评估结果提供了重要的决策支持信息，有助于制定针对性的防灾减灾措施。';
    }
  }
};
</script>

<style scoped>
.assessment-result-cards {
  margin-top: 20px;
}

.assessment-results-content {
  display: flex;
  flex-direction: column;
  gap: 15px;
}

.assessment-overview {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: 10px;
  border-bottom: 1px solid #ebeef5;
}

.assessment-title {
  font-size: 16px;
  font-weight: bold;
}

.assessment-info p {
  margin: 5px 0;
  color: #606266;
}

.assessment-parameters h4,
.assessment-statistics h4,
.assessment-files h4,
.assessment-chart h4,
.assessment-explanation h4 {
  margin-top: 0;
  margin-bottom: 10px;
  font-size: 15px;
  font-weight: 500;
  color: #303133;
}

.parameter-list {
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
}

.parameter-item {
  display: flex;
  justify-content: space-between;
  padding: 5px 0;
  border-bottom: 1px solid #f5f7fa;
}

.parameter-label {
  color: #909399;
  font-size: 13px;
}

.parameter-value {
  color: #303133;
  font-weight: 500;
  font-size: 13px;
}

.stat-item {
  text-align: center;
  padding: 10px;
  background: #f5f7fa;
  border-radius: 4px;
}

.stat-label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 5px;
}

.stat-value {
  font-size: 16px;
  font-weight: bold;
  color: #303133;
}

.file-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.file-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px;
  background: #f5f7fa;
  border-radius: 4px;
}

.assessment-chart {
  margin: 15px 0;
}

.chart-placeholder {
  text-align: center;
  padding: 40px;
  background: #f5f7fa;
  border-radius: 4px;
  color: #909399;
}

.chart-placeholder i {
  font-size: 48px;
  margin-bottom: 10px;
  display: block;
}

.assessment-explanation p {
  margin: 10px 0;
  line-height: 1.6;
  color: #606266;
  text-align: justify;
}

.assessment-explanation strong {
  color: #303133;
  font-weight: 500;
}

/* 综合影响评估的多图网格布局 */
.comprehensive-charts {
  margin-top: 16px;
}

.chart-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 16px;
  margin-bottom: 16px;
}

.chart-item {
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  padding: 12px;
  background: #fafafa;
  transition: all 0.3s ease;
}

.chart-item:hover {
  border-color: #409eff;
  box-shadow: 0 2px 8px rgba(64, 158, 255, 0.15);
  transform: translateY(-2px);
}

.chart-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  text-align: center;
  margin-bottom: 8px;
  padding: 4px 8px;
  background: linear-gradient(90deg, #f0f9ff 0%, #e0f2fe 100%);
  border-radius: 4px;
  border-left: 3px solid #409eff;
}

.chart-thumbnail {
  width: 100%;
  height: 200px;
  border-radius: 4px;
  cursor: pointer;
  transition: transform 0.2s ease;
}

.chart-thumbnail:hover {
  transform: scale(1.02);
}

.chart-note {
  font-size: 12px;
  color: #909399;
  text-align: center;
  margin: 8px 0 0 0;
  font-style: italic;
}

.interpolation-image {
  width: 100%;
  max-height: 400px;
  object-fit: contain;
}

.image-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 200px;
  background: #f5f5f5;
  color: #909399;
  border-radius: 4px;
}

.image-error i {
  font-size: 48px;
  margin-bottom: 8px;
}

.image-error p {
  margin: 0;
  font-size: 12px;
  text-align: center;
}
</style>