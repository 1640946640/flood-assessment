<template>
  <div class="statistics-panel" v-show="visible">
    <div class="panel-header">
      <h3>{{ datasetName }} - 数据统计分析</h3>
      <el-button size="mini" icon="el-icon-close" @click="close" circle></el-button>
    </div>

    <div class="loading-container" v-if="loading">
      <el-spinner type="spinner" :size="32"></el-spinner>
      <span>加载中...</span>
    </div>

    <div class="error-container" v-else-if="error">
      <i class="el-icon-warning"></i>
      <p>{{ error }}</p>
    </div>

    <div class="stats-content" v-else>
      <!-- 数据类型切换选项卡 -->
      <el-tabs v-model="activeTab" @tab-click="handleTabChange">
        <!-- 栅格数据统计 -->
        <el-tab-pane label="栅格统计" name="raster" v-if="isRasterData">
          <div class="raster-stats">
            <!-- 基本统计信息 -->
            <el-card shadow="hover" class="basic-stats-card">
              <div slot="header">
                <span>基本信息</span>
              </div>
              <el-row :gutter="20">
                <el-col :span="12">
                  <el-descriptions :column="1" border size="small">
                    <el-descriptions-item label="宽度">{{ statistics.width }}</el-descriptions-item>
                    <el-descriptions-item label="高度">{{ statistics.height }}</el-descriptions-item>
                    <el-descriptions-item label="波段数">{{ statistics.bands }}</el-descriptions-item>
                  </el-descriptions>
                </el-col>
                <el-col :span="12">
                  <el-descriptions :column="1" border size="small">
                    <el-descriptions-item label="最小值">{{ selectedBandStats ? selectedBandStats.min.toFixed(3) : 'N/A'
                    }}</el-descriptions-item>
                    <el-descriptions-item label="最大值">{{ selectedBandStats ? selectedBandStats.max.toFixed(3) : 'N/A'
                    }}</el-descriptions-item>
                    <el-descriptions-item label="平均值">{{ selectedBandStats ? selectedBandStats.mean.toFixed(3) : 'N/A'
                    }}</el-descriptions-item>
                    <el-descriptions-item label="标准差">{{ selectedBandStats ? selectedBandStats.std.toFixed(3) : 'N/A'
                    }}</el-descriptions-item>
                  </el-descriptions>
                </el-col>
              </el-row>
            </el-card>

            <!-- 波段选择 -->
            <div class="band-selector-container" v-if="statistics.stats && statistics.stats.length > 1">
              <div class="selector-label">选择波段：</div>
              <el-radio-group v-model="selectedBand" size="small" @change="updateRasterChart">
                <el-radio-button v-for="stat in statistics.stats" :key="stat.band" :label="stat.band">
                  波段 {{ stat.band }}
                </el-radio-button>
              </el-radio-group>
            </div>

            <!-- 直方图 -->
            <el-card shadow="hover" class="chart-card">
              <div slot="header">
                <span>{{ selectedBandStats ? `波段 ${selectedBand} 灰度直方图` : '灰度直方图' }}</span>
              </div>
              <div class="chart-container">
                <div class="histogram-chart" ref="rasterHistogram"></div>
              </div>
            </el-card>
          </div>
        </el-tab-pane>

        <!-- 矢量数据统计 -->
        <el-tab-pane label="属性统计" name="vector" v-if="isVectorData">
          <div class="vector-stats">
            <!-- 字段选择和图表配置 -->
            <el-card shadow="hover" class="controls-card">
              <div slot="header">
                <span>图表配置</span>
              </div>
              <el-row :gutter="20">
                <el-col :span="8">
                  <div class="control-item">
                    <div class="control-label">字段：</div>
                    <el-select v-model="selectedField" placeholder="选择字段" size="small" @change="fieldChanged">
                      <el-option v-for="field in availableFields" :key="field.field" :label="field.field"
                        :value="field.field">
                      </el-option>
                    </el-select>
                  </div>
                </el-col>
                <el-col :span="8">
                  <div class="control-item">
                    <div class="control-label">图表类型：</div>
                    <el-select v-model="chartType" placeholder="图表类型" size="small" @change="updateVectorChart">
                      <el-option label="柱状图" value="bar"></el-option>
                      <el-option label="折线图" value="line"></el-option>
                      <el-option label="饼图" value="pie"></el-option>
                      <el-option label="散点图" value="scatter" v-if="hasNumericField"></el-option>
                    </el-select>
                  </div>
                </el-col>
                <el-col :span="8">
                  <div class="control-item" v-if="chartType === 'scatter'">
                    <div class="control-label">对比字段：</div>
                    <el-select v-model="secondField" placeholder="选择第二个字段" size="small" @change="updateVectorChart">
                      <el-option v-for="field in numericFields" :key="field.field" :label="field.field"
                        :value="field.field" :disabled="field.field === selectedField">
                      </el-option>
                    </el-select>
                  </div>
                  <div class="control-item" v-else>
                    <div class="control-label">分组字段：</div>
                    <el-select v-model="groupByField" placeholder="分组(可选)" clearable size="small"
                      @change="updateVectorChart">
                      <el-option v-for="field in availableFields" :key="field.field" :label="field.field"
                        :value="field.field" :disabled="field.field === selectedField">
                      </el-option>
                    </el-select>
                  </div>
                </el-col>
              </el-row>
            </el-card>

            <!-- 字段统计信息 -->
            <el-card shadow="hover" class="stats-card" v-if="selectedFieldStats">
              <div slot="header">
                <span>{{ selectedField }} 字段统计</span>
              </div>
              <el-row :gutter="20">
                <el-col :span="isNumericField ? 12 : 24" v-if="isNumericField">
                  <el-descriptions :column="1" border size="small">
                    <el-descriptions-item label="最小值">{{ selectedFieldStats.min.toFixed(3) }}</el-descriptions-item>
                    <el-descriptions-item label="最大值">{{ selectedFieldStats.max.toFixed(3) }}</el-descriptions-item>
                    <el-descriptions-item label="平均值">{{ selectedFieldStats.avg.toFixed(3) }}</el-descriptions-item>
                    <el-descriptions-item label="标准差">{{ selectedFieldStats.std.toFixed(3) }}</el-descriptions-item>
                  </el-descriptions>
                </el-col>
                <el-col :span="isNumericField ? 12 : 24">
                  <el-descriptions :column="1" border size="small">
                    <el-descriptions-item label="记录数">{{ selectedFieldStats.count }}</el-descriptions-item>
                    <el-descriptions-item label="唯一值数" v-if="!isNumericField">{{ selectedFieldStats.unique
                    }}</el-descriptions-item>
                    <el-descriptions-item label="数据类型">{{ selectedFieldStats.type }}</el-descriptions-item>
                  </el-descriptions>
                </el-col>
              </el-row>
            </el-card>

            <!-- 图表 -->
            <el-card shadow="hover" class="chart-card">
              <div slot="header">
                <span>{{ getChartTitle() }}</span>
              </div>
              <div class="chart-container">
                <div class="spinner-container" v-if="chartLoading">
                  <el-spinner type="spinner" :size="24"></el-spinner>
                  <span>图表加载中...</span>
                </div>
                <div v-else-if="chartError" class="chart-error">
                  <i class="el-icon-warning"></i>
                  <p>{{ chartError }}</p>
                </div>
                <div id="vectorChart" class="vector-chart" ref="vectorChart"
                  :style="{ visibility: chartLoading || chartError ? 'hidden' : 'visible' }"></div>
              </div>
            </el-card>
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<script>
import * as echarts from 'echarts/core';
import {
  BarChart, LineChart, PieChart, ScatterChart,
} from 'echarts/charts';
import {
  TitleComponent, TooltipComponent, LegendComponent,
  GridComponent, DatasetComponent, TransformComponent
} from 'echarts/components';
import { LabelLayout, UniversalTransition } from 'echarts/features';
import { CanvasRenderer } from 'echarts/renderers';

// 注册必要的组件
echarts.use([
  TitleComponent, TooltipComponent, LegendComponent,
  GridComponent, DatasetComponent, TransformComponent,
  BarChart, LineChart, PieChart, ScatterChart,
  LabelLayout, UniversalTransition,
  CanvasRenderer
]);

export default {
  name: 'StatisticsPanel',
  props: {
    visible: {
      type: Boolean,
      default: false
    },
    datasetId: {
      type: String,
      default: ''
    },
    datasetType: {
      type: String,
      default: ''
    },
    datasetName: {
      type: String,
      default: ''
    },
    apiBaseUrl: {
      type: String,
      default: ''
    }
  },
  data() {
    return {
      loading: false,
      error: null,
      statistics: {},
      activeTab: 'raster',
      // 栅格数据相关
      selectedBand: 1,
      rasterChart: null,
      // 矢量数据相关
      selectedField: '',
      chartType: 'bar',
      secondField: '',
      groupByField: '',
      vectorChart: null,
      chartData: null,
      chartLoading: false,
      chartError: null,
      chartInstance: null,
      resizeObserver: null,
      resizeTimer: null
    };
  },
  computed: {
    isRasterData() {
      return this.datasetType === 'raster';
    },
    isVectorData() {
      return this.datasetType === 'vector' || this.datasetType === 'table';
    },
    availableFields() {
      if (!this.statistics.stats || !Array.isArray(this.statistics.stats)) {
        return [];
      }
      return this.statistics.stats;
    },
    numericFields() {
      if (!this.availableFields.length) return [];
      return this.availableFields.filter(field =>
        field.type &&
        (field.type.includes('int') || field.type.includes('float') || field.type.includes('double'))
      );
    },
    hasNumericField() {
      return this.numericFields.length > 1; // 需要至少两个数值字段才能显示散点图选项
    },
    selectedBandStats() {
      if (!this.statistics.stats || !this.statistics.stats.length) {
        return { min: 0, max: 0, mean: 0, std: 0 };
      }
      const bandStat = this.statistics.stats.find(stat => stat.band === this.selectedBand);
      return bandStat || this.statistics.stats[0];
    },
    selectedFieldStats() {
      if (!this.selectedField || !this.statistics.stats) {
        return null;
      }
      return this.statistics.stats.find(stat => stat.field === this.selectedField);
    },
    isNumericField() {
      if (!this.selectedFieldStats) return false;
      const type = this.selectedFieldStats.type;
      return type && (type.includes('int') || type.includes('float') || type.includes('double'));
    }
  },
  watch: {
    visible(newVal) {
      if (newVal && this.datasetId) {
        this.fetchStatistics();
      }
    },
    datasetId(newVal) {
      if (newVal && this.visible) {
        this.fetchStatistics();
      }
    },
    datasetType(newVal) {
      // 根据数据类型选择默认标签页
      this.activeTab = newVal === 'raster' ? 'raster' : 'vector';
    }
  },
  mounted() {
    if (this.visible && this.datasetId) {
      this.fetchStatistics();
    }

    // 创建ResizeObserver监听容器尺寸变化
    this.resizeObserver = new ResizeObserver(entries => {
      for (let entry of entries) {
        this.resizeCharts();
      }
    });

    // 监听窗口大小变化
    window.addEventListener('resize', this.resizeCharts);
  },
  methods: {
    // 获取图表标题
    getChartTitle() {
      if (!this.selectedField) return '属性分析';

      let title = '';
      switch (this.chartType) {
        case 'pie':
          title = this.groupByField
            ? `${this.selectedField} 按 ${this.groupByField} 分组`
            : `${this.selectedField} 分布`;
          break;
        case 'bar':
        case 'line':
          title = this.groupByField
            ? `${this.selectedField} 按 ${this.groupByField} 分组`
            : `${this.selectedField} 分布`;
          break;
        case 'scatter':
          title = this.secondField
            ? `${this.selectedField} 与 ${this.secondField} 相关性`
            : `${this.selectedField} 散点分布`;
          break;
        default:
          title = `${this.selectedField} 分析`;
      }
      return title;
    },

    // 字段变更处理
    fieldChanged() {
      // 如果选择了散点图模式但字段不是数值型，则切换到柱状图
      if (this.chartType === 'scatter' && this.selectedField) {
        const fieldInfo = this.statistics.stats.find(stat => stat.field === this.selectedField);
        if (fieldInfo && !this.isFieldNumeric(fieldInfo.type)) {
          this.chartType = 'bar';
        }
      }
      this.updateVectorChart();
    },

    // 检查字段是否为数值类型
    isFieldNumeric(type) {
      return type && (type.includes('int') || type.includes('float') || type.includes('double'));
    },

    // 获取统计数据
    fetchStatistics() {
      this.loading = true;
      this.error = null;
      const url = `${this.apiBaseUrl}/api/datasets/${this.datasetId}/statistics`;

      fetch(url)
        .then(response => {
          if (!response.ok) {
            throw new Error(`HTTP错误: ${response.status}`);
          }
          return response.json();
        })
        .then(data => {
          this.statistics = data;
          // 设置默认选择
          if (this.isRasterData) {
            this.activeTab = 'raster';
            this.selectedBand = data.stats && data.stats.length > 0 ? data.stats[0].band : 1;
            this.$nextTick(() => {
              console.log('初始化栅格图表', this.$refs.rasterHistogram);
              this.initRasterChart();
              // 添加ResizeObserver
              const chartDom = this.$refs.rasterHistogram;
              if (chartDom) this.resizeObserver.observe(chartDom);
            });
          } else if (this.isVectorData) {
            console.log('进入矢量数据统计');
            this.activeTab = 'vector';
            // 选择第一个非几何字段
            if (data.stats && data.stats.length > 0) {
              this.selectedField = data.stats[0].field;
              // 默认选择柱状图
              this.chartType = 'bar';
              this.$nextTick(() => {
                this.initVectorChart();
                // 添加ResizeObserver
                const chartDom = this.$refs.vectorChart;
                if (chartDom) this.resizeObserver.observe(chartDom);
              });
            }
          }

          this.loading = false;
        })
        .catch(error => {
          this.error = `获取统计数据失败: ${error.message}`;
          this.loading = false;
          console.error('获取统计数据错误:', error);
        });
    },

    // 关闭面板
    close() {
      this.$emit('close');
    },

    // 标签切换
    handleTabChange() {
      this.$nextTick(() => {
        if (this.activeTab === 'raster' && this.isRasterData) {
          this.initRasterChart();
        } else if (this.activeTab === 'vector' && this.isVectorData) {
          this.initVectorChart();
        }
      });
    },

    // 初始化栅格图表 (直方图)
    initRasterChart() {
      // 清理现有图表
      if (this.rasterChart) {
        this.rasterChart.dispose();
        this.rasterChart = null;
      }

      // 获取容器并检查尺寸
      // const chartDom = this.$refs.rasterHistogram;
      // if (!chartDom) return;

      // 确保DOM已经渲染完成并有尺寸
      // 延迟初始化策略，确保DOM已完全渲染并且有正确尺寸
      this.$nextTick(() => {
        setTimeout(() => {
          // 获取图表容器
          const chartDom = this.$refs.rasterHistogram;
          if (!chartDom) {
            console.warn('矢量图表DOM未找到, refs:', this.$refs);
            this.chartError = '图表容器未找到，请重试';
            return;
          }

          console.log('找到矢量图表DOM, 容器尺寸:', chartDom.offsetWidth, chartDom.offsetHeight);

          try {
            // 强制设置容器高度确保ECharts能正确初始化
            if (chartDom.offsetHeight === 0) {
              chartDom.style.height = '300px';
              console.log('已设置容器高度为300px');
            }

            // 初始化ECharts实例
            this.rasterChart = echarts.init(chartDom);
            console.log('图表实例已创建:', this.rasterChart);
            this.updateRasterChart();
          } catch (e) {
            console.error('初始化矢量图表时出错:', e);
            this.chartError = '图表初始化失败: ' + e.message;
          }
        }, 300); // 给予足够时间让DOM完成渲染
      });

    },

    // 更新栅格图表数据
    updateRasterChart() {
      if (!this.rasterChart || !this.statistics.stats) return;

      const bandStat = this.selectedBandStats;

      if (!bandStat || !bandStat.histogram || !bandStat.histogram.counts || bandStat.histogram.counts.length === 0) {
        // 无数据时显示提示
        this.rasterChart.setOption({
          title: {
            text: '无直方图数据',
            left: 'center'
          }
        });
        return;
      }

      const hist = bandStat.histogram;
      const counts = hist.counts;
      const bins = hist.bins;

      // 构建柱状图数据
      const data = counts.map((count, index) => {
        const binStart = bins[index].toFixed(2);
        const binEnd = bins[index + 1].toFixed(2);
        return [
          `${binStart} - ${binEnd}`,
          count
        ];
      });

      // 优化图表样式和处理横坐标过多问题
      const option = {
        title: {
          text: `波段 ${bandStat.band} 灰度直方图`,
          left: 'center',
          textStyle: {
            fontWeight: 'normal',
            fontSize: 16
          }
        },
        tooltip: {
          trigger: 'axis',
          axisPointer: {
            type: 'shadow'
          },
          formatter: function (params) {
            const param = params[0];
            // ECharts直方图的value可能格式不同
            let pixelCount = '无数据';

            // 判断value的格式并获取正确的值
            if (param.value != null) {
              // 如果value是数组，取第二个元素作为像素数
              if (Array.isArray(param.value)) {
                pixelCount = param.value[1] != null ? param.value[1].toLocaleString() : '0';
              }
              // 如果value是数字，直接使用
              else if (typeof param.value === 'number') {
                pixelCount = param.value.toLocaleString();
              }
            } else if (param.data && param.data.length >= 2) {
              // 有时候数据在data属性中
              pixelCount = param.data[1] != null ? param.data[1].toLocaleString() : '0';
            }

            return `区间: ${param.name}<br/>像素数: ${pixelCount}`;
          }
        },
        grid: {
          left: '5%',
          right: '5%',
          bottom: '15%',
          top: '60px',
          containLabel: true
        },
        dataZoom: [
          {
            type: 'slider',
            show: data.length > 10,
            xAxisIndex: 0,
            start: 0,
            end: 100,
            height: 20,
            bottom: 0,
            borderColor: 'transparent',
            backgroundColor: 'rgba(47,69,84,0.1)',
            handleSize: '80%'
          }
        ],
        xAxis: {
          type: 'category',
          data: data.map(item => item[0]),
          axisLabel: {
            interval: function (index, value) {
              // 如果数据点超过10个，则采用稀疏显示
              return data.length <= 10 || index % Math.max(1, Math.floor(data.length / 10)) === 0;
            },
            rotate: 45,
            fontSize: 10,
            formatter: function (value) {
              // 如果标签太长，则只显示部分
              if (value.length > 10) {
                return value.substring(0, 7) + '...';
              }
              return value;
            }
          }
        },
        yAxis: {
          type: 'value',
          name: '像素数',
          nameTextStyle: {
            fontSize: 12
          },
          axisLabel: {
            formatter: value => value.toLocaleString()
          }
        },
        series: [{
          name: '频率',
          type: 'bar',
          data: data.map(item => item[1]),
          itemStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: '#83bff6' },
              { offset: 0.5, color: '#188df0' },
              { offset: 1, color: '#188df0' }
            ])
          },
          emphasis: {
            itemStyle: {
              color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                { offset: 0, color: '#2378f7' },
                { offset: 0.7, color: '#2378f7' },
                { offset: 1, color: '#83bff6' }
              ])
            }
          },
          barWidth: data.length > 20 ? '60%' : '70%'
        }]
      };

      try {
        this.rasterChart.setOption(option);
        // 确保图表在容器尺寸变化时能够适应
        this.$nextTick(() => {
          this.rasterChart.resize();
        });
      } catch (e) {
        console.error('设置栅格图表选项时出错:', e);
      }
    },

    // 初始化矢量图表
    initVectorChart() {
      console.log('开始初始化矢量图表');
      // 清理现有图表
      if (this.vectorChart) {
        this.vectorChart.dispose();
        this.vectorChart = null;
      }

      // 延迟初始化策略，确保DOM已完全渲染并且有正确尺寸
      this.$nextTick(() => {
        setTimeout(() => {
          // 获取图表容器
          const chartDom = this.$refs.vectorChart;
          if (!chartDom) {
            console.warn('矢量图表DOM未找到, refs:', this.$refs);
            this.chartError = '图表容器未找到，请重试';
            return;
          }

          console.log('找到矢量图表DOM, 容器尺寸:', chartDom.offsetWidth, chartDom.offsetHeight);

          try {
            // 强制设置容器高度确保ECharts能正确初始化
            if (chartDom.offsetHeight === 0) {
              chartDom.style.height = '300px';
              console.log('已设置容器高度为300px');
            }

            // 初始化ECharts实例
            this.vectorChart = echarts.init(chartDom);
            console.log('图表实例已创建:', this.vectorChart);
            this.updateVectorChart();
          } catch (e) {
            console.error('初始化矢量图表时出错:', e);
            this.chartError = '图表初始化失败: ' + e.message;
          }
        }, 300); // 给予足够时间让DOM完成渲染
      });
    },

    // 更新矢量图表数据
    updateVectorChart() {
      if (!this.selectedField) return;

      // 图表未初始化但容器已就绪时，先初始化
      if (!this.vectorChart && this.$refs.vectorChart) {
        this.initVectorChart();
        if (!this.vectorChart) return; // 初始化失败则退出
      }

      if (!this.vectorChart) {
        console.warn('矢量图表未初始化，无法更新数据');
        return;
      }

      // 如果是散点图，需要有第二个字段
      if (this.chartType === 'scatter' && !this.secondField) {
        // 自动选择第一个可用的数值字段
        const availableFields = this.numericFields.filter(f => f.field !== this.selectedField);
        if (availableFields.length > 0) {
          this.secondField = availableFields[0].field;
        } else {
          // 如果没有可用的第二字段，切换回柱状图
          this.chartType = 'bar';
        }
      }

      this.chartLoading = true;
      this.chartError = null;

      // 从API获取图表数据
      let url = `${this.apiBaseUrl}/api/datasets/${this.datasetId}/chart`;

      // 将参数添加为URL查询参数而非请求体
      const queryParams = new URLSearchParams();
      queryParams.append('field', this.selectedField);
      queryParams.append('chartType', this.chartType);

      if (this.secondField) {
        queryParams.append('secondField', this.secondField);
      }

      if (this.groupByField) {
        queryParams.append('groupBy', this.groupByField);
      }

      url = `${url}?${queryParams.toString()}`;

      console.log('请求图表数据:', url);
      fetch(url, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json'
        }
      })
        .then(response => {
          if (!response.ok) {
            throw new Error(`HTTP错误: ${response.status}`);
          }
          return response.json();
        })
        .then(data => {
          console.log('图表数据返回:', data);
          this.chartData = data;
          this.renderVectorChart();
          this.chartLoading = false;
        })
        .catch(error => {
          this.chartError = `获取图表数据失败: ${error.message}`;
          this.chartLoading = false;
          console.error('获取图表数据错误:', error);
        });
    },

    // 渲染矢量图表
    renderVectorChart() {
      if (!this.vectorChart || !this.chartData) return;

      console.log('开始渲染矢量图表:', this.chartType);

      // 检查chartData是否有有效数据
      if (this.chartType === 'pie' && (!this.chartData.series || this.chartData.series.length === 0)) {
        this.vectorChart.setOption({
          title: {
            text: '无数据可展示',
            left: 'center'
          }
        });
        return;
      } else if ((this.chartType === 'bar' || this.chartType === 'line') &&
        (!this.chartData.xAxis || !this.chartData.series || this.chartData.series.length === 0)) {
        this.vectorChart.setOption({
          title: {
            text: '无数据可展示',
            left: 'center'
          }
        });
        return;
      } else if (this.chartType === 'scatter' &&
        (!this.chartData.series || !this.chartData.series[0] || !this.chartData.series[0].data || this.chartData.series[0].data.length === 0)) {
        this.vectorChart.setOption({
          title: {
            text: '无数据可展示',
            left: 'center'
          }
        });
        return;
      }

      let option = {};

      // 根据图表类型设置不同的配置
      switch (this.chartType) {
        case 'pie':
          option = this.getPieChartOption();
          break;
        case 'bar':
          option = this.getBarChartOption();
          break;
        case 'line':
          option = this.getLineChartOption();
          break;
        case 'scatter':
          option = this.getScatterChartOption();
          break;
      }

      try {
        this.vectorChart.setOption(option, true);
        // 设置完数据后立即触发resize，确保在容器尺寸变化后正确渲染
        this.$nextTick(() => {
          if (this.vectorChart) {
            this.vectorChart.resize();
            console.log('矢量图表已渲染完成');
          }
        });
      } catch (e) {
        console.error('设置图表选项时出错:', e);
        this.chartError = '图表渲染失败: ' + e.message;
      }
    },

    // 重置所有图表
    resetCharts() {
      // 销毁现有图表实例
      if (this.rasterChart) {
        this.rasterChart.dispose();
        this.rasterChart = null;
      }

      if (this.vectorChart) {
        this.vectorChart.dispose();
        this.vectorChart = null;
      }
    },

    // 饼图配置
    getPieChartOption() {
      const series = this.chartData.series || [];

      // 限制显示的项数量，如果太多则分类为"其他"
      let displaySeries = [...series];
      const maxSlices = 12; // 最大显示的饼图块数

      if (series.length > maxSlices) {
        // 按值排序并取前(maxSlices-1)项
        const sortedSeries = [...series].sort((a, b) => b.value - a.value);
        const topItems = sortedSeries.slice(0, maxSlices - 1);

        // 剩余项合并为"其他"
        const otherItems = sortedSeries.slice(maxSlices - 1);
        const otherValue = otherItems.reduce((sum, item) => sum + item.value, 0);

        displaySeries = [
          ...topItems,
          { name: '其他', value: otherValue }
        ];
      }

      // 计算总数，用于显示百分比
      const total = displaySeries.reduce((sum, item) => sum + item.value, 0);

      return {
        title: {
          text: this.groupByField
            ? `${this.selectedField} 按 ${this.groupByField} 分组`
            : `${this.selectedField} 分布`,
          left: 'center',
          textStyle: {
            fontWeight: 'normal',
            fontSize: 16
          }
        },
        tooltip: {
          trigger: 'item',
          formatter: params => {
            // 安全处理值和百分比
            const value = params.value != null ? params.value : 0;
            const percent = total > 0 ? ((value / total) * 100).toFixed(2) : '0.00';
            const formattedValue = value != null ? value.toLocaleString() : '无数据';
            return `${params.name}<br/>${formattedValue} (${percent}%)`;
          }
        },
        legend: {
          type: 'scroll',
          orient: displaySeries.length > 6 ? 'vertical' : 'horizontal',
          right: displaySeries.length > 6 ? 10 : 'auto',
          bottom: displaySeries.length > 6 ? 'auto' : 0,
          top: displaySeries.length > 6 ? 20 : 'auto',
          left: displaySeries.length > 6 ? 'auto' : 'center',
          padding: [10, 5],
          formatter: name => {
            if (name.length > 15) {
              return name.substring(0, 12) + '...';
            }
            return name;
          }
        },
        series: [
          {
            name: this.selectedField,
            type: 'pie',
            radius: ['30%', '70%'], // 改为环形图提高可视效果
            center: ['50%', '50%'],
            data: displaySeries,
            emphasis: {
              itemStyle: {
                shadowBlur: 10,
                shadowOffsetX: 0,
                shadowColor: 'rgba(0, 0, 0, 0.5)'
              }
            },
            label: {
              formatter: '{b}: {d}%',
              fontSize: 11
            }
          }
        ]
      };
    },

    // 柱状图配置
    getBarChartOption() {
      const xAxisData = this.chartData.xAxis || [];

      return {
        title: {
          text: this.groupByField
            ? `${this.selectedField} 按 ${this.groupByField} 分组`
            : `${this.selectedField} 分布`,
          left: 'center',
          textStyle: {
            fontWeight: 'normal',
            fontSize: 16
          }
        },
        tooltip: {
          trigger: 'axis',
          axisPointer: {
            type: 'shadow'
          },
          formatter: function (params) {
            let tip = `${params[0].name}<br/>`;
            params.forEach(param => {
              // 安全处理值
              const value = param.value != null ? param.value.toLocaleString() : '无数据';
              tip += `${param.seriesName}: ${value}<br/>`;
            });
            return tip;
          }
        },
        legend: {
          show: this.chartData.series.length > 1,
          bottom: 0,
          padding: [10, 5]
        },
        grid: {
          left: '5%',
          right: '5%',
          bottom: xAxisData.length > 10 ? '20%' : '15%',
          top: '60px',
          containLabel: true
        },
        dataZoom: [
          {
            type: 'slider',
            show: xAxisData.length > 10,
            xAxisIndex: 0,
            start: 0,
            end: xAxisData.length > 20 ? 50 : 100, // 如果数据超过20，只显示前50%
            height: 20,
            bottom: 0,
            borderColor: 'transparent',
            backgroundColor: 'rgba(47,69,84,0.1)',
            handleSize: '80%'
          }
        ],
        xAxis: {
          type: 'category',
          data: xAxisData,
          axisLabel: {
            interval: function (index, value) {
              // 如果数据点超过10个，则采用稀疏显示
              return xAxisData.length <= 10 || index % Math.max(1, Math.floor(xAxisData.length / 10)) === 0;
            },
            rotate: 45,
            fontSize: 10,
            formatter: function (value) {
              // 如果标签太长，则只显示部分
              if (value && value.length > 10) {
                return value.substring(0, 7) + '...';
              }
              return value;
            }
          }
        },
        yAxis: {
          type: 'value',
          nameTextStyle: {
            fontSize: 12
          },
          axisLabel: {
            formatter: value => value != null ? value.toLocaleString() : '0'
          }
        },
        series: this.chartData.series.map(item => ({
          ...item,
          type: 'bar',
          barMaxWidth: 50, // 限制柱子最大宽度
          itemStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: '#83bff6' },
              { offset: 0.5, color: '#188df0' },
              { offset: 1, color: '#188df0' }
            ])
          }
        }))
      };
    },

    // 折线图配置
    getLineChartOption() {
      const xAxisData = this.chartData.xAxis || [];

      return {
        title: {
          text: this.groupByField
            ? `${this.selectedField} 按 ${this.groupByField} 分组`
            : `${this.selectedField} 分布`,
          left: 'center',
          textStyle: {
            fontWeight: 'normal',
            fontSize: 16
          }
        },
        tooltip: {
          trigger: 'axis'
        },
        legend: {
          show: this.chartData.series.length > 1,
          bottom: 0,
          padding: [10, 5]
        },
        grid: {
          left: '5%',
          right: '5%',
          bottom: xAxisData.length > 10 ? '20%' : '15%',
          top: '60px',
          containLabel: true
        },
        dataZoom: [
          {
            type: 'slider',
            show: xAxisData.length > 10,
            xAxisIndex: 0,
            start: 0,
            end: xAxisData.length > 20 ? 50 : 100, // 如果数据超过20，只显示前50%
            height: 20,
            bottom: 0,
            borderColor: 'transparent',
            backgroundColor: 'rgba(47,69,84,0.1)',
            handleSize: '80%'
          }
        ],
        xAxis: {
          type: 'category',
          data: xAxisData,
          boundaryGap: false,
          axisLabel: {
            interval: function (index, value) {
              // 如果数据点超过10个，则采用稀疏显示
              return xAxisData.length <= 10 || index % Math.max(1, Math.floor(xAxisData.length / 10)) === 0;
            },
            rotate: 45,
            fontSize: 10,
            formatter: function (value) {
              // 如果标签太长，则只显示部分
              if (value && value.length > 10) {
                return value.substring(0, 7) + '...';
              }
              return value;
            }
          }
        },
        yAxis: {
          type: 'value',
          nameTextStyle: {
            fontSize: 12
          },
          axisLabel: {
            formatter: value => value != null ? value.toLocaleString() : '0'
          }
        },
        series: this.chartData.series.map(item => ({
          ...item,
          type: 'line',
          smooth: true,
          symbol: 'circle',
          symbolSize: 6,
          sampling: 'average',
          itemStyle: {
            color: '#188df0',
            borderWidth: 2
          },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              {
                offset: 0,
                color: 'rgba(24, 141, 240, 0.3)'
              },
              {
                offset: 1,
                color: 'rgba(24, 141, 240, 0)'
              }
            ])
          }
        }))
      };
    },

    // 散点图配置
    getScatterChartOption() {
      return {
        title: {
          text: `${this.selectedField} 与 ${this.secondField} 相关性`,
          left: 'center',
          textStyle: {
            fontWeight: 'normal',
            fontSize: 16
          }
        },
        grid: {
          left: '5%',
          right: '5%',
          bottom: '10%',
          top: '60px',
          containLabel: true
        },
        tooltip: {
          trigger: 'item',
          formatter: params => {
            // 安全处理散点图坐标值
            const xValue = params.value && params.value[0] != null ? params.value[0].toLocaleString() : '无数据';
            const yValue = params.value && params.value[1] != null ? params.value[1].toLocaleString() : '无数据';
            return `${this.chartData.xAxis.name}: ${xValue}<br/>${this.chartData.yAxis.name}: ${yValue}`;
          }
        },
        xAxis: {
          name: this.chartData.xAxis.name,
          nameLocation: 'middle',
          nameGap: 30,
          nameTextStyle: {
            fontSize: 12
          },
          type: 'value',
          scale: true,
          axisLabel: {
            formatter: value => value != null ? value.toLocaleString() : '0',
            fontSize: 10
          }
        },
        yAxis: {
          name: this.chartData.yAxis.name,
          nameLocation: 'middle',
          nameGap: 40,
          nameTextStyle: {
            fontSize: 12
          },
          type: 'value',
          scale: true,
          axisLabel: {
            formatter: value => value != null ? value.toLocaleString() : '0',
            fontSize: 10
          }
        },
        dataZoom: [
          {
            type: 'inside',
            xAxisIndex: 0
          },
          {
            type: 'inside',
            yAxisIndex: 0
          }
        ],
        series: [
          {
            name: '散点',
            type: 'scatter',
            data: this.chartData.series[0].data,
            symbolSize: 10,
            itemStyle: {
              color: new echarts.graphic.RadialGradient(0.5, 0.5, 0.5, [
                {
                  offset: 0,
                  color: '#1E90FF'
                },
                {
                  offset: 1,
                  color: '#1E90FF'
                }
              ]),
              borderColor: '#0062b0',
              borderWidth: 1,
              shadowBlur: 5,
              shadowColor: 'rgba(0, 0, 0, 0.3)'
            },
            emphasis: {
              itemStyle: {
                borderColor: '#fff',
                borderWidth: 2,
                shadowBlur: 10,
                shadowColor: 'rgba(0, 98, 176, 0.5)'
              }
            }
          }
        ]
      };
    },

    // 窗口大小变化时重新绘制图表
    resizeCharts() {
      // 防抖处理
      if (this.resizeTimer) clearTimeout(this.resizeTimer);

      this.resizeTimer = setTimeout(() => {
        if (this.rasterChart) {
          this.rasterChart.resize();
        }
        if (this.vectorChart) {
          this.vectorChart.resize();
        }
      }, 100);
    }
  },
  beforeDestroy() {
    // 销毁图表实例，避免内存泄漏
    this.resetCharts();

    window.removeEventListener('resize', this.resizeCharts);

    // 移除ResizeObserver
    if (this.resizeObserver) {
      if (this.$refs.rasterHistogram) this.resizeObserver.unobserve(this.$refs.rasterHistogram);
      if (this.$refs.vectorChart) this.resizeObserver.unobserve(this.$refs.vectorChart);
      this.resizeObserver.disconnect();
    }
  },
  created() {
    // 添加resize监听
    window.addEventListener('resize', this.resizeCharts);
  }
}
</script>

<style scoped>
.statistics-panel {
  display: flex;
  flex-direction: column;
  background-color: var(--background-color, #fff);
  color: var(--primary-text, #303133);
  /* border-radius: 8px; */
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
  width: 100%;
  height: 100%;
  overflow: hidden;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 15px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.1);
}

.panel-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 500;
}

.loading-container,
.error-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px;
  color: var(--secondary-text, #909399);
  height: 300px;
}

.loading-container span {
  margin-top: 15px;
}

.error-container i {
  font-size: 32px;
  color: #f56c6c;
  margin-bottom: 15px;
}

.stats-content {
  flex: 1;
  overflow-y: auto;
  padding: 15px;
}

.raster-stats,
.vector-stats {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* 卡片样式 */
.basic-stats-card,
.stats-card,
.chart-card,
.controls-card {
  margin-bottom: 20px;
  width: 100%;
}

.chart-card {
  margin-top: 10px;
}

/* 选择器容器 */
.band-selector-container,
.field-selector {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-bottom: 15px;
  padding: 10px;
  background-color: rgba(0, 0, 0, 0.02);
  border-radius: 4px;
}

.selector-label {
  font-weight: 500;
  margin-right: 5px;
  font-size: 14px;
}

/* 控制项样式 */
.control-item {
  display: flex;
  flex-direction: column;
  margin-bottom: 10px;
}

.control-label {
  font-size: 14px;
  margin-bottom: 5px;
  color: var(--secondary-text, #606266);
}

/* 图表容器样式 */
.chart-container {
  width: 100%;
  height: 380px !important;
  /* 使用!important确保高度优先级 */
  margin-top: 20px;
  position: relative;
}

.histogram-chart,
.vector-chart {
  /* width: 100%; */
  height: 350px !important;
  /* 使用确定的高度而非百分比 */
  border: 1px solid #ebeef5;
  background-color: #fff;
  border-radius: 4px;
  padding: 10px;
}

/* 加载和错误状态 */
.spinner-container,
.chart-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  width: 100%;
}

.spinner-container span {
  margin-top: 10px;
  color: #909399;
}

.chart-error {
  color: #f56c6c;
}

.chart-error i {
  font-size: 24px;
  margin-bottom: 10px;
}

html[data-theme='dark'] ::deep .el-descriptions :not(.is-bordered) .el-descriptions-item__cell {
  color: #fff !important;
  background-color: #1e1e1e !important;
}

/* 深色主题适配 */
html[data-theme='dark'] .statistics-panel {
  background-color: #1e1e1e;
  color: #fff;
}

html[data-theme='dark'] .panel-header {
  border-bottom-color: rgba(255, 255, 255, 0.1);
}

html[data-theme='dark'] .loading-container,
html[data-theme='dark'] .error-container {
  color: rgba(255, 255, 255, 0.7);
}

html[data-theme='dark'] .vector-chart,
html[data-theme='dark'] .histogram-chart {
  background-color: #1e1e1e;
  border-color: #3e3e3e;
}

html[data-theme='dark'] .control-label {
  color: rgba(255, 255, 255, 0.7);
}

html[data-theme='dark'] .band-selector-container,
html[data-theme='dark'] .field-selector {
  background-color: rgba(255, 255, 255, 0.05);
}

:deep(.el-tabs__content) {
  overflow: unset !important;
}
</style>