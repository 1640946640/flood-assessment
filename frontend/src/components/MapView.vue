<template>
  <div class="map-container">
    <div id="map" ref="map"></div>
    <div class="map-tools">
      <el-button-group class="zoom-tools">
        <el-button size="mini" icon="el-icon-plus" @click="zoomIn" title="放大"></el-button>
        <el-button size="mini" icon="el-icon-minus" @click="zoomOut" title="缩小"></el-button>
        <el-button size="mini" icon="el-icon-refresh-right" @click="resetView" title="重置视图"></el-button>
      </el-button-group>
      <el-divider direction="vertical"></el-divider>
      <el-button-group class="draw-tools">
        <el-button size="mini" icon="el-icon-edit" @click="activateTool('draw', 'Point')" title="绘制点"></el-button>
        <el-button size="mini" icon="el-icon-connection" @click="activateTool('draw', 'LineString')"
          title="绘制线"></el-button>
        <el-button size="mini" icon="el-icon-crop" @click="activateTool('draw', 'Polygon')" title="绘制多边形"></el-button>
        <el-button size="mini" icon="el-icon-delete" @click="clearDrawings" title="清除绘制"></el-button>
      </el-button-group>
      <el-divider direction="vertical"></el-divider>
      <el-button-group class="measure-tools">
        <el-button size="mini" icon="el-icon-position" @click="activateTool('measure', 'distance')"
          title="测量距离"></el-button>
        <el-button size="mini" icon="el-icon-full-screen" @click="activateTool('measure', 'area')"
          title="测量面积"></el-button>
      </el-button-group>
      <!-- <el-divider direction="vertical"></el-divider> -->
      <!-- <el-button-group class="analysis-tools">
        <el-button size="mini" icon="el-icon-data-analysis" @click="showStatistics" title="统计分析"></el-button>
      </el-button-group> -->
    </div>

    <div class="basemap-selector">
      <el-dropdown trigger="click" @command="switchBasemap" size="large">
        <el-button size="large" icon="el-icon-map-location">
          底图 <i class="el-icon-arrow-down el-icon--right"></i>
        </el-button>
        <el-dropdown-menu slot="dropdown">
          <el-dropdown-item command="osm">OpenStreetMap</el-dropdown-item>
          <el-dropdown-item command="satellite">卫星影像</el-dropdown-item>
          <el-dropdown-item command="terrain">地形图</el-dropdown-item>
          <el-dropdown-item command="dark">暗黑模式</el-dropdown-item>
          <el-dropdown-item command="light">亮色模式</el-dropdown-item>
        </el-dropdown-menu>
      </el-dropdown>
    </div>

    <div class="layer-control" v-if="showLayerControl">
      <div class="layer-header">
        <h4>图层管理器</h4>
        <div class="layer-header-buttons">
          <el-button size="mini" icon="el-icon-delete" @click="removeAllLayers" circle title="清除所有图层"></el-button>
          <el-button size="mini" icon="el-icon-refresh" @click="refreshLayers" circle title="刷新图层"></el-button>
        </div>
      </div>
      <el-input size="mini" v-model="layerFilter" placeholder="搜索图层" prefix-icon="el-icon-search" clearable
        class="layer-search"></el-input>
      <el-tree :data="filteredLayers" node-key="id" @node-click="handleLayerSelect" default-expand-all
        :props="{ label: 'name' }" :filter-node-method="filterNode" class="layer-tree" ref="layerTree"
        :highlight-current="true" :current-node-key="selectedLayerId">
        <span class="custom-tree-node" slot-scope="{ node, data }">
          <span class="layer-name" :title="data.name">
            <i v-if="data.type === 'vector'" class="el-icon-map-location"></i>
            <i v-else-if="data.type === 'raster'" class="el-icon-picture"></i>
            <i v-else-if="data.type === 'table' && data.format === 'csv'" class="el-icon-document-copy"
              style="color: #67c23a;"></i>
            <i v-else-if="data.type === 'table' && ['xls', 'xlsx'].includes(data.format)" class="el-icon-document"
              style="color: #409eff;"></i>
            <i v-else class="el-icon-document"></i>
            <span class="layer-name-text">{{ data.name }}</span>
            <span v-if="data.format" class="layer-format">({{ data.format }})</span>
          </span>
          <span class="layer-controls">
            <i v-if="data.type !== 'table'" class="el-icon-view" 
              :class="{ 'layer-visible': isLayerVisible(data.id), 'layer-hidden': !isLayerVisible(data.id) }" 
              @click.stop="toggleLayerVisibility(data.id)"></i>
            <el-button v-if="data.type !== 'table'" type="text" size="mini" icon="el-icon-zoom-in" title="缩放至图层"
              @click.stop="zoomToLayer(data.id)">
            </el-button>
            <el-button type="text" size="mini" icon="el-icon-data-analysis" title="统计分析"
              @click.stop="showLayerStatistics(data)">
            </el-button>
            <el-dropdown trigger="click" @command="handleLayerCommand" class="layer-dropdown">
              <span class="el-dropdown-link">
                <i class="el-icon-more"></i>
              </span>
              <el-dropdown-menu slot="dropdown">
                <el-dropdown-item :command="{ type: 'up', id: data.id }">
                  <i class="el-icon-top"></i> 上移
                </el-dropdown-item>
                <el-dropdown-item :command="{ type: 'down', id: data.id }">
                  <i class="el-icon-bottom"></i> 下移
                </el-dropdown-item>
                <el-dropdown-item :command="{ type: 'style', id: data.id }">
                  <i class="el-icon-brush"></i> 样式设置
                </el-dropdown-item>
                <el-dropdown-item :command="{ type: 'remove', id: data.id }">
                  <i class="el-icon-delete"></i> 移除图层
                </el-dropdown-item>
              </el-dropdown-menu>
            </el-dropdown>
          </span>
        </span>
      </el-tree>
      
      <!-- 图例显示区域 -->
      <div v-if="selectedLayerId && layers[selectedLayerId]" class="layer-legend">
        <div class="legend-header">
          <h4>图例 - {{ getLayerName(selectedLayerId) }}</h4>
        </div>
        <div class="legend-content">
          <!-- 矢量图层图例 -->
          <div v-if="getLayerType(selectedLayerId) === 'vector'" class="vector-legend">
            <!-- 单一符号样式图例 -->
            <div v-if="!layerStyleConfigs[selectedLayerId] || layerStyleConfigs[selectedLayerId].type === 'simple'">
              <div v-if="layerStyleConfigs[selectedLayerId] && layerStyleConfigs[selectedLayerId].legend && layerStyleConfigs[selectedLayerId].legend.length > 0" class="legend-item">
                <div class="legend-symbol vector-symbol" :style="{backgroundColor: layerStyleConfigs[selectedLayerId].legend[0].color, borderColor: layerStyleConfigs[selectedLayerId].legend[0].stroke, borderWidth: '2px', borderStyle: 'solid'}"></div>
                <div class="legend-label">{{ layerStyleConfigs[selectedLayerId].legend[0].label }}</div>
              </div>
               <div v-else class="legend-item"> 
              <div class="legend-symbol vector-symbol" :style="getVectorStyle(selectedLayerId)"></div>
              <div class="legend-label">{{ getLayerName(selectedLayerId) }}</div>
              </div>
            </div>
            
            <!-- 分类样式图例 -->
            <div v-else-if="layerStyleConfigs[selectedLayerId].type === 'categorized'">
              <div class="legend-subtitle">字段: {{ layerStyleConfigs[selectedLayerId].field }}</div>
              <div v-for="(item, index) in layerStyleConfigs[selectedLayerId].legend" :key="`cat-${index}`" class="legend-item">
                <div class="legend-symbol vector-symbol" :style="{backgroundColor: item.color, borderColor: item.stroke || item.color, borderWidth: '2px', borderStyle: 'solid'}"></div>
                <div class="legend-label">{{ item.label }}</div>
              </div>
            </div>
            
            <!-- 分级样式图例 -->
            <div v-else-if="layerStyleConfigs[selectedLayerId].type === 'graduated'">
              <div class="legend-subtitle">字段: {{ layerStyleConfigs[selectedLayerId].field }}</div>
              <div v-for="(item, index) in layerStyleConfigs[selectedLayerId].legend" :key="`grad-${index}`" class="legend-item">
                <div class="legend-symbol vector-symbol" :style="{backgroundColor: item.color, borderColor: item.stroke || item.color, borderWidth: '2px', borderStyle: 'solid'}"></div>
                <div class="legend-label">{{ item.label }}</div>
              </div>
            </div>
          </div>
          <!-- 栅格图层图例 -->
          <div v-else-if="getLayerType(selectedLayerId) === 'raster'" class="raster-legend">
            <div class="legend-item">
              <div class="legend-value-min">{{ getRasterMinValue(selectedLayerId) }}</div>
            <div class="raster-gradient" :style="getRasterGradientStyle(selectedLayerId)"></div>
            <div class="legend-value-max">{{ getRasterMaxValue(selectedLayerId) }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>
    <div class="measure-tooltip" v-show="measureValue">{{ measureValue }}</div>

    <!-- 坐标信息显示 -->
    <div class="coordinate-display">
      <span>经度: {{ mousePosition.lon.toFixed(6) }}</span>
      <span>纬度: {{ mousePosition.lat.toFixed(6) }}</span>
    </div>

    <!-- 统计分析面板 -->
    <el-dialog title="统计分析" :visible.sync="statisticsVisible" width="80%" :before-close="closeStatistics"
      custom-class="statistics-dialog" top="10vh">
      <statistics-panel :visible="statisticsVisible" :dataset-id="currentDataset.id" :dataset-type="currentDataset.type"
        :dataset-name="currentDataset.name" :api-base-url="apiBaseUrl" @close="closeStatistics"></statistics-panel>
    </el-dialog>
  </div>
</template>

<script>
import 'ol/ol.css';
import Map from 'ol/Map';
import View from 'ol/View';
import TileLayer from 'ol/layer/Tile';
import ImageLayer from 'ol/layer/Image';
import OSM from 'ol/source/OSM';
import XYZ from 'ol/source/XYZ';
import ImageStatic from 'ol/source/ImageStatic';
import { fromLonLat, toLonLat, transformExtent, get as getProjection } from 'ol/proj';
import Draw from 'ol/interaction/Draw';
import VectorLayer from 'ol/layer/Vector';
import VectorSource from 'ol/source/Vector';
import { Style, Stroke, Fill, Circle } from 'ol/style';
import { LineString, Polygon } from 'ol/geom';
import { getLength, getArea } from 'ol/sphere';
import GeoJSON from 'ol/format/GeoJSON';
import * as olLoadingstrategy from 'ol/loadingstrategy';
import { initProjections, parseProjection } from '@/utils/projectionUtils';
import StatisticsPanel from './StatisticsPanel.vue';
import Vue from 'vue';
import axios from 'axios';

export default {
  name: 'MapView',
  components: {
    StatisticsPanel
  },
  props: {
    showLayerControl: {
      type: Boolean,
      default: true
    },
    center: {
      type: Array,
      default: () => [104.5, 35.0] // 中国中心点
    },
    zoom: {
      type: Number,
      default: 4
    }
  },
  data() {
    return {
      map: null,
      layerTree: [],
      layers: {},
      basemapLayers: {},
      currentBasemap: 'osm',
      draw: null,
      measure: null,
      source: null,
      vector: null,
      activeTool: null,
      measureValue: '',
      layerFilter: '',
      mousePosition: {
        lon: 0,
        lat: 0
      },
      apiBaseUrl: process.env.VUE_APP_API_URL || '', // API基础URL
      statisticsVisible: false,
      currentDataset: {
        id: '',
        type: '',
        name: ''
      },
      selectedLayerId: null, // 添加选中图层ID
      layerStyles: {}, // 存储图层样式
      layerStyleConfigs: {} // 存储图层样式配置
    }
  },
  computed: {
    filteredLayers() {
      return this.layerTree;
    }
  },
  mounted() {
    // 初始化坐标系定义
    initProjections();
    this.initMap();

    // 监听图层添加事件
    this.$on('layer-added', (layerInfo) => {
      console.log('收到图层添加事件:', layerInfo);
      if (layerInfo.type === 'table') {
        // 对于表格数据，直接添加到图层树中
        this.addLayerToTree(layerInfo);
      }
    });
  },
  watch: {
    layerFilter(val) {
      this.$refs.layerTree?.filter(val);
    }
  },
  methods: {
    initMap() {
      // 创建矢量图层用于绘制和测量
      this.source = new VectorSource();
      this.vector = new VectorLayer({
        source: this.source,
        style: new Style({
          fill: new Fill({
            color: 'rgba(255, 255, 255, 0.2)'
          }),
          stroke: new Stroke({
            color: '#1890ff',
            width: 2
          }),
          image: new Circle({
            radius: 7,
            fill: new Fill({
              color: '#1890ff'
            })
          })
        }),
        zIndex: 100 // 确保绘制图层始终在顶部
      });

      // 初始化底图图层
      this.initBasemapLayers();

      this.map = new Map({
        target: this.$refs.map,
        layers: [
          this.basemapLayers.osm,
          this.vector
        ],
        view: new View({
          center: fromLonLat(this.center),
          zoom: this.zoom
        })
      });

      // 添加坐标显示功能
      this.map.on('pointermove', (e) => {
        const coords = toLonLat(e.coordinate);
        this.mousePosition.lon = coords[0];
        this.mousePosition.lat = coords[1];
      });

      // 发送初始化完成事件
      this.$emit('map-initialized', this.map);
    },

    // 初始化底图图层
    initBasemapLayers() {
      // OpenStreetMap (使用 Esri World Street Map 替代以解决连接超时问题)
      this.basemapLayers.osm = new TileLayer({
        source: new XYZ({
          url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
          maxZoom: 19,
          attributions: 'Tiles © <a href="https://services.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer">ArcGIS</a>'
        }),
        zIndex: 0,
        visible: true
      });

      // 卫星影像
      this.basemapLayers.satellite = new TileLayer({
        source: new XYZ({
          url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
          maxZoom: 19
        }),
        zIndex: 0,
        visible: false
      });

      // 地形图
      this.basemapLayers.terrain = new TileLayer({
        source: new XYZ({
          url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}',
          maxZoom: 19
        }),
        zIndex: 0,
        visible: false
      });

      // 暗黑模式底图
      this.basemapLayers.dark = new TileLayer({
        source: new XYZ({
          url: 'https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
          maxZoom: 19
        }),
        zIndex: 0,
        visible: false
      });

      // 亮色模式底图
      this.basemapLayers.light = new TileLayer({
        source: new XYZ({
          url: 'https://basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
          maxZoom: 19
        }),
        zIndex: 0,
        visible: false
      });
    },

    // 切换底图
    switchBasemap(basemapType) {
      // 隐藏所有底图图层
      Object.keys(this.basemapLayers).forEach(key => {
        this.basemapLayers[key].setVisible(false);
      });

      // 显示选定的底图
      if (this.basemapLayers[basemapType]) {
        this.basemapLayers[basemapType].setVisible(true);
        this.currentBasemap = basemapType;

        // 如果地图已初始化，确保底图图层已添加到地图中
        if (this.map) {
          const mapLayers = this.map.getLayers().getArray();
          Object.keys(this.basemapLayers).forEach(key => {
            const layer = this.basemapLayers[key];
            if (!mapLayers.includes(layer)) {
              this.map.addLayer(layer);
            }
          });
        }
      }
    },

    // 激活工具 (绘制或测量)
    activateTool(toolType, geometryType) {
      // 清除当前激活的工具
      this.deactivateCurrentTool();

      if (toolType === 'draw') {
        this.activateDrawTool(geometryType);
      } else if (toolType === 'measure') {
        this.activateMeasureTool(geometryType);
      }

      this.activeTool = { type: toolType, geometry: geometryType };
    },

    // 停用当前工具
    deactivateCurrentTool() {
      if (this.draw) {
        this.map.removeInteraction(this.draw);
        this.draw = null;
      }

      if (this.measure) {
        this.map.removeInteraction(this.measure);
        this.measure = null;
      }

      this.measureValue = '';
      this.activeTool = null;
    },

    // 激活绘制工具
    activateDrawTool(geometryType) {
      this.draw = new Draw({
        source: this.source,
        type: geometryType
      });

      this.map.addInteraction(this.draw);
    },

    // 激活测量工具
    activateMeasureTool(measureType) {
      let geometryType = measureType === 'distance' ? 'LineString' : 'Polygon';

      this.measure = new Draw({
        source: this.source,
        type: geometryType,
        style: new Style({
          fill: new Fill({
            color: 'rgba(255, 255, 255, 0.2)'
          }),
          stroke: new Stroke({
            color: 'rgba(0, 0, 0, 0.5)',
            lineDash: [10, 10],
            width: 2
          }),
          image: new Circle({
            radius: 5,
            stroke: new Stroke({
              color: 'rgba(0, 0, 0, 0.7)'
            }),
            fill: new Fill({
              color: 'rgba(255, 255, 255, 0.2)'
            })
          })
        })
      });

      // 添加测量事件
      this.measure.on('drawstart', () => {
        this.measureValue = '';
      });

      this.measure.on('drawend', (evt) => {
        let value = '';
        const geometry = evt.feature.getGeometry();

        if (measureType === 'distance') {
          const length = getLength(geometry);
          if (length > 1000) {
            value = (Math.round(length / 1000 * 100) / 100) + ' km';
          } else {
            value = (Math.round(length * 100) / 100) + ' m';
          }
        } else if (measureType === 'area') {
          const area = getArea(geometry);
          if (area > 10000) {
            value = (Math.round(area / 1000000 * 100) / 100) + ' km²';
          } else {
            value = (Math.round(area * 100) / 100) + ' m²';
          }
        }

        this.measureValue = value;
      });

      this.map.addInteraction(this.measure);
    },

    // 清除绘制
    clearDrawings() {
      this.deactivateCurrentTool();
      this.source.clear();
    },

    // 添加矢量图层 (SHP)
    addVectorLayer(layerConfig) {
      try {
        console.log('Adding vector layer:', layerConfig);

        // 检查图层是否已存在
        if (this.layers[layerConfig.id]) {
          console.log(`图层 ${layerConfig.id} 已存在，将缩放到该图层`);
          this.zoomToLayer(layerConfig.id);

          // 发送图层已存在的事件
          this.$emit('layer-exists', {
            id: layerConfig.id,
            type: 'vector',
            name: layerConfig.name
          });

          return this.layers[layerConfig.id];
        }

        // 构建图层URL - 确保URL正确
        let layerUrl = layerConfig.url;
        if (!layerUrl) {
          // 如果没有提供完整URL，则构建API路径
          console.log('apiBaseUrl', this.apiBaseUrl);
          layerUrl = `${this.apiBaseUrl}/api/datasets/${layerConfig.id}/geojson`;
          console.log('Vector layer URL:', layerUrl);
        }

        // 计算新图层的zIndex - 确保新图层在最上层
        const maxZIndex = Math.max(
          ...Object.values(this.layers)
            .filter(layer => typeof layer.getZIndex === 'function')
            .map(layer => layer.getZIndex() || 0),
          50 // 基础值
        );
        const newZIndex = maxZIndex + 1;

        // 创建矢量图层
        const vectorSource = new VectorSource({
          format: new GeoJSON(),
          loader: (extent, resolution, projection) => {
            console.log('请求矢量数据URL:', layerUrl);

            // 设置请求头和更好的错误处理
            const xhr = new XMLHttpRequest();
            xhr.open('GET', layerUrl);
            xhr.setRequestHeader('Accept', 'application/json');
            xhr.responseType = 'text';  // 确保以文本形式接收响应

            xhr.onload = () => {
              if (xhr.status === 200) {
                try {
                  console.log('收到响应类型:', xhr.getResponseHeader('Content-Type'));
                  const responseText = xhr.responseText;

                  // 检查响应是否是HTML
                  if (responseText.trim().startsWith('<!DOCTYPE html>') ||
                    responseText.trim().startsWith('<html>')) {
                    console.error('收到HTML而不是JSON:', responseText.substring(0, 200));
                    this.handleLayerError(layerConfig, {
                      message: '服务器返回了HTML而不是GeoJSON数据'
                    });
                    return;
                  }

                  // 尝试解析JSON
                  const geojson = JSON.parse(responseText);

                  // 检查是否是有效的GeoJSON
                  if (!geojson.type || !geojson.features) {
                    console.error('响应不是有效的GeoJSON:', geojson);
                    this.handleLayerError(layerConfig, {
                      message: '服务器返回的不是有效的GeoJSON数据'
                    });
                    return;
                  }

                  // 获取数据的坐标系信息
                  let dataProjection = 'EPSG:4326'; // 默认WGS84
                  
                  // 如果GeoJSON中包含坐标系信息，使用它
                  if (geojson.crs && geojson.crs.properties && geojson.crs.properties.name) {
                    dataProjection = parseProjection(geojson.crs.properties.name);
                    console.log(`从GeoJSON中检测到坐标系: ${dataProjection}`);
                  }
                  
                  // 如果后端返回的元数据中包含坐标系信息，优先使用它
                  if (geojson.metadata && geojson.metadata.crs) {
                    dataProjection = parseProjection(geojson.metadata.crs);
                    console.log(`从元数据中检测到坐标系: ${dataProjection}`);
                  }
                  
                  // 解析GeoJSON并添加要素，进行坐标系转换
                  const features = vectorSource.getFormat().readFeatures(
                    geojson,
                    { dataProjection: dataProjection, featureProjection: projection }
                  );
                  vectorSource.addFeatures(features);
                  console.log(`成功加载 ${features.length} 个要素`);

                  // 缩放到图层范围
                  if (features.length > 0) {
                    const extent = vectorSource.getExtent();
                    if (extent && !isNaN(extent[0])) {
                      this.map.getView().fit(extent, {
                        padding: [50, 50, 50, 50],
                        duration: 1000
                      });
                    }
                  }
                } catch (e) {
                  console.error('Error parsing GeoJSON:', e);
                  console.log('Response:', xhr.responseText.substring(0, 200) + '...');
                  this.handleLayerError(layerConfig, {
                    message: '数据格式错误，无法加载图层'
                  });
                }
              } else {
                console.error(`Error loading vector layer: ${xhr.status}`);
                this.handleLayerError(layerConfig, {
                  message: `无法加载图层数据 (${xhr.status})`
                });
              }
            };

            xhr.onerror = () => {
              console.error('Network error loading vector layer');
              this.handleLayerError(layerConfig, {
                message: '网络错误，无法加载图层'
              });
            };

            xhr.send();
          },
          strategy: olLoadingstrategy.all
        });

        const vectorLayer = new VectorLayer({
          source: vectorSource,
          style: new Style({
            fill: new Fill({
              color: 'rgba(255, 255, 255, 0.2)'
            }),
            stroke: new Stroke({
              color: '#1890ff',
              width: 2
            }),
            image: new Circle({
              radius: 7,
              fill: new Fill({
                color: '#1890ff'
              })
            })
          }),
          zIndex: newZIndex
        });

        // 设置图层ID和名称
        vectorLayer.set('id', layerConfig.id);
        vectorLayer.set('name', layerConfig.name);
        vectorLayer.set('type', 'vector');

        // 添加到地图和图层管理中
        this.map.addLayer(vectorLayer);
        this.layers[layerConfig.id] = vectorLayer;

        // 更新图层树 - 添加到最前面
        this.layerTree.unshift({
          id: layerConfig.id,
          name: layerConfig.name,
          type: 'vector',
          opacity: 1
        });

        // 发送图层添加事件
        this.$emit('layer-added', {
          id: layerConfig.id,
          type: 'vector',
          name: layerConfig.name
        });

        return vectorLayer;
      } catch (error) {
        console.error('Error adding vector layer:', error);
        this.handleLayerError(layerConfig, {
          message: '添加图层失败: ' + error.message
        });
        return null;
      }
    },

    // 添加栅格图层 (TIF)
    addRasterLayer(layerConfig) {
      try {
        console.log('Adding raster layer:', layerConfig);

        // 检查图层是否已存在
        if (this.layers[layerConfig.id]) {
          console.log(`图层 ${layerConfig.id} 已存在，将缩放到该图层`);
          this.zoomToLayer(layerConfig.id);

          // 发送图层已存在的事件
          this.$emit('layer-exists', {
            id: layerConfig.id,
            type: 'raster',
            name: layerConfig.name
          });

          return this.layers[layerConfig.id];
        }

        // 构建图层URL - 确保URL正确
        let imageUrl = layerConfig.url;
        console.log('Raster image URL:', imageUrl);
        if (!imageUrl) {
          // 如果没有提供完整URL，则构建API路径获取完整图像
          imageUrl = `${this.apiBaseUrl}/api/datasets/${layerConfig.id}/image`;
          console.log('Raster image URL:', imageUrl);
        }

        // 先获取数据集信息，包括边界范围
        this.fetchDatasetMetadata(layerConfig.id).then(metadata => {
          // 获取边界信息
          let bounds = null;
          if (metadata.metadata && metadata.metadata.bounds) {
            bounds = metadata.metadata.bounds;
          } else if (metadata.properties && metadata.properties.bounds) {
            bounds = metadata.properties.bounds;
          } else if (metadata.bounds) {
            bounds = metadata.bounds;
          }
          if (!bounds || bounds.length !== 4) {
            console.error(`未能获取到栅格图层 ${layerConfig.id} 的范围信息`);
            this.handleLayerError(layerConfig, {
              message: '缺少范围信息，无法加载栅格图层'
            });
            return;
          }

          // 获取数据的坐标系信息
          let dataProjection = 'EPSG:4326'; // 默认WGS84
          
          // 如果元数据中包含坐标系信息，使用它
          if (metadata.metadata && metadata.metadata.crs) {
            dataProjection = parseProjection(metadata.metadata.crs);
            console.log(`从元数据中检测到栅格坐标系: ${dataProjection}`);
          } else if (metadata.properties && metadata.properties.crs) {
            dataProjection = parseProjection(metadata.properties.crs);
            console.log(`从属性中检测到栅格坐标系: ${dataProjection}`);
          }
          
          // 转换边界坐标到地图投影
          const extent = this.transformExtent(
            bounds,
            dataProjection,
            this.map.getView().getProjection().getCode()
          );

          console.log(`栅格图层 ${layerConfig.id} 范围:`, extent);

          // 创建静态图像图层
          const imageSource = new ImageStatic({
            url: imageUrl,
            crossOrigin: 'anonymous',
            imageExtent: extent,
            projection: this.map.getView().getProjection()
          });

          // 提取栅格数据的最大最小值
          let minValue = null;
          let maxValue = null;
          
          // 从元数据中获取最大最小值
          if (metadata.metadata && metadata.metadata.statistics) {
            minValue = metadata.metadata.statistics.min;
            maxValue = metadata.metadata.statistics.max;
          } else if (metadata.properties && metadata.properties.statistics) {
            minValue = metadata.properties.statistics.min;
            maxValue = metadata.properties.statistics.max;
          } else if (metadata.statistics) {
            minValue = metadata.statistics.min;
            maxValue = metadata.statistics.max;
          }
          
          // 计算新图层的zIndex - 确保新图层在最上层
          const maxZIndex = Math.max(
            ...Object.values(this.layers)
              .filter(layer => typeof layer.getZIndex === 'function')
              .map(layer => layer.getZIndex() || 0),
            40 // 基础值
          );
          const newZIndex = maxZIndex + 1;
          
          const rasterLayer = new ImageLayer({
            source: imageSource,
            opacity: 1,
            zIndex: newZIndex
          });
          
          // 保存栅格元数据，包括最大最小值
          rasterLayer.set('metadata', {
            min: minValue !== null ? minValue : 0,
            max: maxValue !== null ? maxValue : 255
          });
          
          // 设置默认颜色映射（从蓝色到红色的渐变）
          rasterLayer.set('colormap', [
            '#000000', // 蓝色（低值）
            '#00FFFF', // 青色
            '#00FF00', // 绿色
            '#FFFF00', // 黄色
            '#FFFFFF'  // 红色（高值）
          ]);
          // 图像加载错误处理
          const sourceOnError = function (e) {
            console.error('栅格图像加载失败:', e);
            this.handleLayerError(layerConfig, {
              message: '无法加载栅格图像'
            });
          }.bind(this);

          imageSource.on('imageloaderror', sourceOnError);

          // 设置图层ID和名称
          rasterLayer.set('id', layerConfig.id);
          rasterLayer.set('name', layerConfig.name);
          rasterLayer.set('type', 'raster');

          // 保存元数据信息
          rasterLayer.set('metadata', {
            bounds: bounds,
            crs: dataProjection,
            min: metadata.properties?.min || metadata.metadata?.min,
            max: metadata.properties?.max || metadata.metadata?.max,

          });

          // 添加到地图和图层管理中
          this.map.addLayer(rasterLayer);
          this.layers[layerConfig.id] = rasterLayer;

          // 更新图层树
          this.layerTree.unshift({
            id: layerConfig.id,
            name: layerConfig.name,
            type: 'raster',
            opacity: 1
          });

          // 发送图层添加事件
          this.$emit('layer-added', {
            id: layerConfig.id,
            type: 'raster',
            name: layerConfig.name
          });

          // 缩放到图层范围
          this.map.getView().fit(extent, {
            padding: [50, 50, 50, 50],
            duration: 1000
          });

          return rasterLayer;
        }).catch(error => {
          console.error(`获取栅格图层 ${layerConfig.id} 元数据失败:`, error);
          this.handleLayerError(layerConfig, {
            message: '无法加载图层数据'
          });
          return null;
        });

        // 返回一个占位符，实际图层将在Promise中创建
        return null;
      } catch (error) {
        console.error('Error adding raster layer:', error);
        this.handleLayerError(layerConfig, {
          message: '添加图层失败: ' + error.message
        });
        return null;
      }
    },

    addLayer(layerConfig) {
      switch (layerConfig.type) {
        case 'raster':
          return this.addRasterLayer(layerConfig);
        case 'vector':
          return this.addVectorLayer(layerConfig);
        default:
          console.error(`未知图层类型: ${layerConfig.type}`);
          return null;
      }
    },

    // 获取数据集元数据
    async fetchDatasetMetadata(datasetId) {
      try {
        // 构建API URL
        const url = `${this.apiBaseUrl}/api/datasets/${datasetId}`;
        console.log('Fetching dataset metadata:', url);
        // 使用axios发送请求
        const response = await axios.get(url);
        
        console.log("数据集元数据:", response.data);
        return response.data;
      } catch (error) {
        console.error('获取数据集元数据失败:', error);
        throw new Error(error.response ? `HTTP错误: ${error.response.status}` : '网络错误');
      }
    },

    // 添加GeoJSON图层
    addGeoJSONLayer(layerConfig) {
      // 这里将来会实现GeoJSON图层的加载逻辑
      this.$emit('layer-added', {
        id: layerConfig.id,
        type: 'geojson'
      });

      // 更新图层树
      this.layerTree.unshift({
        id: layerConfig.id,
        name: layerConfig.name,
        type: 'geojson',
        opacity: 1
      });
    },

    // 添加表格数据图层 (CSV, Excel) - 仅在图层管理器中显示，不加载到地图上
    addTableLayer(layerConfig) {
      try {
        console.log('Adding table layer to layer manager:', layerConfig);

        // 检查图层是否已存在
        if (this.layers[layerConfig.id]) {
          console.log(`表格数据 ${layerConfig.id} 已存在`);

          // 发送图层已存在的事件
          this.$emit('layer-exists', {
            id: layerConfig.id,
            type: 'table',
            name: layerConfig.name
          });

          return this.layers[layerConfig.id];
        }

        // 创建一个虚拟图层对象用于管理
        const tableFormat = layerConfig.format || 'csv';
        const tableObj = {
          isTable: true,
          id: layerConfig.id,
          name: layerConfig.name || '未命名表格',
          type: 'table',
          format: tableFormat,
          getVisible: () => true, // 始终可见，因为不在地图上显示
          setVisible: () => { } // 空方法，因为不需要控制地图上的可见性
        };

        // 添加到图层管理中
        this.layers[layerConfig.id] = tableObj;

        // 更新图层树
        this.layerTree.unshift({
          id: layerConfig.id,
          name: layerConfig.name,
          type: 'table',
          format: tableFormat,
          opacity: 1
        });

        // 发送图层添加事件
        this.$emit('layer-added', {
          id: layerConfig.id,
          type: 'table',
          name: layerConfig.name,
          format: tableFormat
        });

        return tableObj;
      } catch (error) {
        console.error('Error adding table layer:', error);
        return null;
      }
    },

    // 移除图层
    removeLayer(layerId) {
      console.log('移除图层:', this.layers);
      if (this.layers[layerId]) {
        // 如果是普通图层，从地图上移除
        if (!this.layers[layerId].isTable) {
        this.map.removeLayer(this.layers[layerId]);
        }
        
        delete this.layers[layerId];
        
        // 如果删除的是当前选中的图层，清除选中状态
        if (this.selectedLayerId === layerId) {
          this.selectedLayerId = null;
        }
      }

        // 更新图层树
        const index = this.layerTree.findIndex(layer => layer.id === layerId);
        if (index !== -1) {
          this.layerTree.splice(index, 1);
        }

        this.$emit('layer-removed', { id: layerId });
    },

    // 刷新图层列表
    refreshLayers() {
      // 刷新图层逻辑
      this.$emit('refresh-layers');
    },

    // 更新图层透明度
    updateLayerOpacity(layerId, opacity) {
      if (this.layers[layerId]) {
        this.layers[layerId].setOpacity(opacity);
      }
    },

    // 图层操作
    handleLayerCommand(command) {
      const { type, id } = command;

      switch (type) {
        case 'up':
          this.moveLayerUp(id);
          break;
        case 'down':
          this.moveLayerDown(id);
          break;
        case 'style':
          this.editLayerStyle(id);
          break;
        case 'remove':
          this.removeLayer(id);
          break;
      }
    },

    // 图层上移
    moveLayerUp(layerId) {
      const index = this.layerTree.findIndex(layer => layer.id === layerId);
      if (index > 0) {
        // 在图层树中上移
        const newLayerTree = [...this.layerTree];
        const temp = newLayerTree.splice(index, 1)[0];
        newLayerTree.splice(index - 1, 0, temp);
        this.layerTree = newLayerTree;
        
        // 调整所有图层的z-index
        this.adjustLayerZIndex();
      }
    },

    // 图层下移
    moveLayerDown(layerId) {
      const index = this.layerTree.findIndex(layer => layer.id === layerId);
      if (index >= 0 && index < this.layerTree.length - 1) {
        // 在图层树中下移
        const newLayerTree = [...this.layerTree];
        const temp = newLayerTree.splice(index, 1)[0];
        newLayerTree.splice(index + 1, 0, temp);
        this.layerTree = newLayerTree;
        
        // 调整所有图层的z-index
        this.adjustLayerZIndex();
      }
    },
    
    // 调整图层z-index
    adjustLayerZIndex() {
      // 从上到下遍历图层树，设置z-index
      // 最上面的图层z-index最大，确保在地图上显示在最上层
      let zIndex = 100 + this.layerTree.length; // 起始值足够大
      
      this.layerTree.forEach((layerInfo, index) => {
        const layer = this.layers[layerInfo.id];
        if (layer && typeof layer.setZIndex === 'function') {
          layer.setZIndex(zIndex - index);
        }
      });
    },
    
    // 编辑图层样式
    editLayerStyle(layerId) {
      const layer = this.layers[layerId];
      if (!layer) return;
      
      const layerType = this.getLayerType(layerId);
      
      // 矢量图层样式设置
      if (layerType === 'vector') {
        // 获取图层属性字段
        this.getLayerFields(layerId).then(fields => {
          // 获取当前样式配置
          const styleConfig = this.layerStyleConfigs[layerId] || {
            type: 'simple',
            field: '',
            colorRamp: 'blues'
          };
          
          // 过滤可用于渲染的字段
          const renderFields = fields.filter(field => 
            field.name !== 'geometry' && 
            field.name !== 'geom' && 
            field.name !== 'the_geom'
          );
          
          // 使用响应式数据对象
          const vm = new Vue({
            data: {
              formData: {
                styleType: styleConfig.type || 'simple',
                field: styleConfig.field || '',
                colorRamp: styleConfig.colorRamp || 'blues'
              }
            },
            methods: {
              updateDialog() {
                // 强制对话框内容更新
                if (this.styleDialog) {
                  const dialog = document.querySelector('.vector-style-dialog');
                  if (dialog) {
                    // 查找并更新字段选择器和颜色方案选择器的显示状态
                    const fieldSelector = dialog.querySelector('#fieldSelector');
                    const colorSelector = dialog.querySelector('#colorSelector');
                    
                    if (fieldSelector) {
                      fieldSelector.style.display = this.formData.styleType === 'simple' ? 'none' : 'block';
                    }
                    
                    if (colorSelector) {
                      colorSelector.style.display = this.formData.styleType === 'simple' ? 'none' : 'block';
                    }
                  }
                }
              }
            }
          });
          
          // 创建样式设置对话框
          const h = this.$createElement;
          
          // 创建表单内容
          const dialogContent = h('div', { 
            style: {
              textAlign: 'left',
              padding: '10px'
            }
          }, [
            // 样式类型选择
            h('div', { style: { marginBottom: '15px' } }, [
              h('div', { style: { marginBottom: '10px', fontWeight: 'bold' } }, '渲染方式:'),
              h('div', { style: { display: 'flex', gap: '15px' } }, [
                // 单一符号
                h('label', { style: { display: 'flex', alignItems: 'center', cursor: 'pointer' } }, [
                  h('input', {
                    attrs: {
                      type: 'radio',
                      name: 'styleType',
                      value: 'simple'
                    },
                    domProps: {
                      checked: vm.formData.styleType === 'simple'
                    },
                    on: {
                      change: (e) => {
                        vm.formData.styleType = 'simple';
                        // 延迟执行以确保DOM已更新
                        setTimeout(() => {
                          // 手动强制更新显示
                          const fieldSelector = document.querySelector('#fieldSelector');
                          const colorSelector = document.querySelector('#colorSelector');
                          if (fieldSelector) fieldSelector.style.display = 'none';
                          if (colorSelector) colorSelector.style.display = 'none';
                        }, 10);
                      }
                    },
                    style: { marginRight: '5px' }
                  }),
                  h('span', '单一符号')
                ]),
                
                // 分类符号
                h('label', { style: { display: 'flex', alignItems: 'center', cursor: 'pointer' } }, [
                  h('input', {
                    attrs: {
                      type: 'radio',
                      name: 'styleType',
                      value: 'categorized'
                    },
                    domProps: {
                      checked: vm.formData.styleType === 'categorized'
                    },
                    on: {
                      change: (e) => {
                        vm.formData.styleType = 'categorized';
                        // 延迟执行以确保DOM已更新
                        setTimeout(() => {
                          // 手动强制更新显示
                          const fieldSelector = document.querySelector('#fieldSelector');
                          const colorSelector = document.querySelector('#colorSelector');
                          if (fieldSelector) fieldSelector.style.display = 'block';
                          if (colorSelector) colorSelector.style.display = 'block';
                        }, 10);
                      }
                    },
                    style: { marginRight: '5px' }
                  }),
                  h('span', '分类')
                ]),
                
                // 分级符号
                h('label', { style: { display: 'flex', alignItems: 'center', cursor: 'pointer' } }, [
                  h('input', {
                    attrs: {
                      type: 'radio',
                      name: 'styleType',
                      value: 'graduated'
                    },
                    domProps: {
                      checked: vm.formData.styleType === 'graduated'
                    },
                    on: {
                      change: (e) => {
                        vm.formData.styleType = 'graduated';
                        // 延迟执行以确保DOM已更新
                        setTimeout(() => {
                          // 手动强制更新显示
                          const fieldSelector = document.querySelector('#fieldSelector');
                          const colorSelector = document.querySelector('#colorSelector');
                          if (fieldSelector) fieldSelector.style.display = 'block';
                          if (colorSelector) colorSelector.style.display = 'block';
                        }, 10);
                      }
                    },
                    style: { marginRight: '5px' }
                  }),
                  h('span', '分级')
                ])
              ])
            ]),
            
            // 字段选择器 (独立div，通过style控制显示隐藏)
            h('div', { 
              attrs: { id: 'fieldSelector' },
              style: { 
                marginBottom: '15px',
                display: vm.formData.styleType === 'simple' ? 'none' : 'block'
              } 
            }, [
              h('div', { style: { marginBottom: '10px', fontWeight: 'bold' } }, '属性字段:'),
              h('select', {
                attrs: {
                  id: 'styleField'
                },
                domProps: {
                  value: vm.formData.field
                },
                on: {
                  change: (e) => {
                    vm.formData.field = e.target.value;
                  }
                },
                style: {
                  width: '100%',
                  padding: '8px',
                  borderRadius: '4px',
                  backgroundColor: 'rgba(255,255,255,0.1)',
                  color: 'var(--primary-text)',
                  border: '1px solid rgba(255,255,255,0.2)'
                }
              }, [
                h('option', { attrs: { value: '' } }, '-- 请选择字段 --'),
                ...renderFields.map(field => 
                  h('option', { 
                    attrs: { value: field.name }
                  }, `${field.name} (${field.type})`)
                )
              ])
            ]),
            
            // 颜色方案选择器 (独立div，通过style控制显示隐藏)
            h('div', { 
              attrs: { id: 'colorSelector' },
              style: { 
                marginBottom: '15px',
                display: vm.formData.styleType === 'simple' ? 'none' : 'block'
              } 
            }, [
              h('div', { style: { marginBottom: '10px', fontWeight: 'bold' } }, '颜色方案:'),
              h('select', {
                attrs: {
                  id: 'colorRamp'
                },
                domProps: {
                  value: vm.formData.colorRamp
                },
                on: {
                  change: (e) => {
                    vm.formData.colorRamp = e.target.value;
                  }
                },
                style: {
                  width: '100%',
                  padding: '8px',
                  borderRadius: '4px',
                  backgroundColor: 'rgba(255,255,255,0.1)',
                  color: 'var(--primary-text)',
                  border: '1px solid rgba(255,255,255,0.2)'
                }
              }, [
                h('option', { attrs: { value: 'blues' } }, '蓝色系'),
                h('option', { attrs: { value: 'reds' } }, '红色系'),
                h('option', { attrs: { value: 'greens' } }, '绿色系'),
                h('option', { attrs: { value: 'spectral' } }, '光谱'),
                h('option', { attrs: { value: 'jet' } }, '彩虹'),
                h('option', { attrs: { value: 'random' } }, '随机')
              ])
            ])
          ]);
          
          // 显示样式设置对话框
          this.$msgbox({
            title: '矢量样式设置',
            message: dialogContent,
            showCancelButton: true,
          confirmButtonText: '应用',
          cancelButtonText: '取消',
            customClass: 'vector-style-dialog',
          center: true,
            distinguishCancelAndClose: true,
            beforeClose: (action, instance, done) => {
              if (action === 'confirm') {
                // 根据选择的样式类型应用样式
                if (vm.formData.styleType === 'simple') {
                  this.applySimpleStyle(layerId);
                } else if (vm.formData.styleType === 'categorized' && vm.formData.field) {
                  this.applyCategorizedStyle(layerId, vm.formData.field, vm.formData.colorRamp);
                } else if (vm.formData.styleType === 'graduated' && vm.formData.field) {
                  this.applyGraduatedStyle(layerId, vm.formData.field, vm.formData.colorRamp);
                } else {
                  // 如果选择了分类或分级但没有选择字段，提示用户
                  if (vm.formData.styleType !== 'simple' && !vm.formData.field) {
                    this.$message.warning('请选择属性字段');
                    return false; // 阻止对话框关闭
                  }
                }
                this.$message.success('图层样式已更新');
              }
              done(); // 关闭对话框
            }
          }).catch(() => {
            // 用户取消，不做任何操作
            this.$message.info('已取消样式设置');
          });
          
          // 保存对话框引用到vm实例中，方便更新
          vm.styleDialog = true;
          
        }).catch(error => {
          console.error('获取图层属性字段失败:', error);
          this.$message.error('获取图层字段失败，无法设置属性渲染。');
        });
      } else if (layerType === 'raster') {
        // 栅格样式设置保持不变
        this.$prompt('输入栅格颜色方案 (e.g., #0000FF,#FFFFFF)', '栅格样式设置', {
          confirmButtonText: '应用',
          cancelButtonText: '取消',
          inputValue: layer.get('colormap') ? layer.get('colormap').join(',') : '#0000FF,#00FFFF,#00FF00,#FFFF00,#FF0000',
          inputPattern: /^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})(,#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3}))*$/,
          inputErrorMessage: '颜色格式不正确，请使用逗号分隔的十六进制颜色代码 (例如: #FF0000,#00FF00)'
        }).then(({ value }) => {
          const colormap = value.split(',');
          layer.set('colormap', colormap);
          layer.getSource().refresh(); // 刷新图层以应用新颜色
          this.$message.success('栅格图层样式已更新');
        }).catch(() => {
          this.$message.info('已取消栅格样式设置');
        });
      }
    },

    // 过滤图层
    filterNode(value, data) {
      if (!value) return true;
      return data.name.toLowerCase().indexOf(value.toLowerCase()) !== -1;
    },

    // 缩放控制
    zoomIn() {
      const view = this.map.getView();
      const zoom = view.getZoom();
      view.setZoom(zoom + 1);
    },

    zoomOut() {
      const view = this.map.getView();
      const zoom = view.getZoom();
      view.setZoom(zoom - 1);
    },

    resetView() {
      const view = this.map.getView();
      view.setCenter(fromLonLat(this.center));
      view.setZoom(this.zoom);
    },

    // 图层显示控制
    handleLayerToggle(checkedNodes, info) {
      const { id, checked } = info;
      const layer = this.layers[id];

      if (layer) {
        // 对于普通图层，控制可见性
        if (typeof layer.setVisible === 'function') {
        layer.setVisible(checked);
        }
      }
    },

    // 缩放到指定图层
    zoomToLayer(layerId) {
      const layer = this.layers[layerId];
      if (!layer) {
        console.warn(`图层 ${layerId} 不存在`);
        return;
      }

      try {
        const layerType = layer.get('type');
        console.log(`尝试缩放到图层: ${layerId}, 类型: ${layerType}`);

        if (layerType === 'vector') {
          // 矢量图层 - 使用图层范围
          const source = layer.getSource();
          if (source.getExtent) {
            const extent = source.getExtent();
            if (extent && !isNaN(extent[0]) && extent[0] !== Infinity) {
              this.map.getView().fit(extent, {
                padding: [50, 50, 50, 50],
                duration: 1000
              });
              console.log(`已缩放到矢量图层: ${layerId}`, extent);
            } else {
              console.warn(`无法获取矢量图层 ${layerId} 的范围`);
            }
          }
        } else if (layerType === 'raster') {
          // 栅格图层 - 使用元数据中的范围
          const metadata = layer.get('metadata');
          console.log(`尝试缩放到栅格图层: ${layerId}`, metadata);
          if (metadata && metadata.bounds) {
            // 如果图层对象中存储了bounds
            const bounds = metadata.bounds;
            const crs = metadata.crs || 'EPSG:4326'; // 使用元数据中的坐标系，默认为EPSG:4326
            const extent = [bounds[0], bounds[1], bounds[2], bounds[3]];

            // 转换为地图投影
            const mapExtent = this.transformExtent(extent, crs, this.map.getView().getProjection().getCode());

            this.map.getView().fit(mapExtent, {
              padding: [50, 50, 50, 50],
              duration: 1000
            });
            console.log(`已缩放到栅格图层(使用元数据): ${layerId}`, extent, `坐标系: ${crs}`);
          } else {
            // 如果没有元数据，向后端请求数据集信息
            const datasetId = layer.get('id');
            if (datasetId) {
              this.fetchDatasetExtent(datasetId)
                .then(result => {
                  if (result && result.bounds) {
                    const { bounds, crs } = result;
                    // 转换为地图投影
                    const mapExtent = this.transformExtent(bounds, crs, this.map.getView().getProjection().getCode());

                    this.map.getView().fit(mapExtent, {
                      padding: [50, 50, 50, 50],
                      duration: 1000
                    });

                    // 缓存范围和坐标系到图层对象
                    layer.set('metadata', { bounds, crs });

                    console.log(`已缩放到栅格图层(从后端获取): ${layerId}`, bounds, `坐标系: ${crs}`);
                  } else {
                    this.zoomToDefaultView();
                  }
                })
                .catch(error => {
                  console.error(`获取栅格图层 ${layerId} 范围失败:`, error);
                  this.zoomToDefaultView();
                });
            } else {
              this.zoomToDefaultView();
            }
          }
        } else {
          // 其他类型图层 - 使用默认视图
          this.zoomToDefaultView();
        }
      } catch (error) {
        console.error(`缩放到图层 ${layerId} 时出错:`, error);
        this.zoomToDefaultView();
      }
    },

    // 转换坐标系
    transformExtent(extent, sourceProj, targetProj) {
      if (sourceProj === targetProj) return extent;

      try {
        // 解析坐标系字符串，确保使用正确的EPSG代码
        const sourceProjCode = parseProjection(sourceProj);
        const targetProjCode = parseProjection(targetProj);
        
        console.log(`转换坐标系: ${sourceProjCode} -> ${targetProjCode}`);
        return transformExtent(extent, sourceProjCode, targetProjCode);
      } catch (error) {
        console.error('转换范围坐标系失败:', error);
        return extent;
      }
    },

    // 获取数据集范围
    fetchDatasetExtent(datasetId) {
      return new Promise((resolve, reject) => {
        // 构建API URL
        const url = `${this.apiBaseUrl}/api/datasets/${datasetId}`;

        // 发送请求
        const xhr = new XMLHttpRequest();
        xhr.open('GET', url);
        xhr.responseType = 'json';

        xhr.onload = () => {
          if (xhr.status === 200 && xhr.response) {
            const dataset = xhr.response;

            // 尝试从不同位置获取范围和坐标系
            let bounds = null;
            let crs = 'EPSG:4326'; // 默认坐标系

            if (dataset.metadata && dataset.metadata.bounds) {
              bounds = dataset.metadata.bounds;
              crs = dataset.metadata.crs || 'EPSG:4326';
            } else if (dataset.properties && dataset.properties.bounds) {
              bounds = dataset.properties.bounds;
              crs = dataset.properties.crs || 'EPSG:4326';
            } else if (dataset.bounds) {
              bounds = dataset.bounds;
            }

            if (bounds && bounds.length === 4) {
              resolve({ bounds, crs });
            } else {
              console.warn(`未找到数据集 ${datasetId} 的范围信息`);
              resolve(null);
            }
          } else {
            console.error(`获取数据集 ${datasetId} 信息失败:`, xhr.status);
            reject(new Error(`HTTP错误: ${xhr.status}`));
          }
        };

        xhr.onerror = () => {
          reject(new Error('网络错误'));
        };

        xhr.send();
      });
    },

    // 设置默认视图
    zoomToDefaultView() {
      // 中国范围
      const chinaExtent = [73.5, 18.0, 135.0, 53.5];
      const mapExtent = this.transformExtent(chinaExtent, 'EPSG:4326', this.map.getView().getProjection().getCode());

      this.map.getView().fit(mapExtent, {
        padding: [50, 50, 50, 50],
        duration: 1000
      });
      console.log('已缩放到默认范围');
    },

    // 显示统计分析面板 - 当点击主工具栏统计按钮时
    showStatistics() {
      // 如果没有选择图层，显示提示
      if (Object.keys(this.layers).length === 0) {
        this.$message({
          message: '请先添加并选择一个图层进行分析',
          type: 'warning'
        });
        return;
      }
      
      // 使用第一个可见图层
      const visibleLayers = Object.values(this.layers).filter(layer => layer.getVisible());
      if (visibleLayers.length === 0) {
        this.$message({
          message: '请先设置一个图层为可见状态',
          type: 'warning'
        });
        return;
      }
      
      const firstLayer = visibleLayers[0];
      const layerInfo = {
        id: firstLayer.get('id'),
        type: firstLayer.get('type'),
        name: firstLayer.get('name')
      };
      
      this.showLayerStatistics(layerInfo);
    },
    
    // 显示图层统计信息 - 当点击图层上的统计按钮时
    showLayerStatistics(layerInfo) {
      console.log('显示图层统计信息:', layerInfo);

      if (!layerInfo || !layerInfo.id) {
        this.$message({
          message: '图层信息不完整，无法分析',
          type: 'error'
        });
        return;
      }

      // 获取图层类型
      let layerType = layerInfo.type;
      if (!layerType && this.layers[layerInfo.id]) {
        layerType = this.layers[layerInfo.id].get ? this.layers[layerInfo.id].get('type') : this.layers[layerInfo.id].type;
      }

      // 对于表格数据，设置特殊类型
      if (layerType === 'table') {
        console.log(`显示表格数据统计: ${layerInfo.name} (${layerInfo.format || 'csv'})`);
      }

      let layerName = layerInfo.name;
      if (!layerName) {
        if (this.layers[layerInfo.id]) {
          if (typeof this.layers[layerInfo.id].get === 'function') {
            layerName = this.layers[layerInfo.id].get('name');
          } else {
            layerName = this.layers[layerInfo.id].name;
          }
        }
        if (!layerName) {
          layerName = layerInfo.id;
        }
      }
      
      this.currentDataset = {
        id: layerInfo.id,
        type: layerType || 'vector',
        name: layerName,
        format: layerInfo.format
      };
      
      console.log('当前数据集信息:', this.currentDataset);
      this.statisticsVisible = true;
    },
    
    // 关闭统计面板
    closeStatistics() {
      this.statisticsVisible = false;
    },

    // 处理图层加载错误 - 添加方法
    handleLayerError(layerConfig, error) {
      // 检查是否是表格文件格式（CSV/Excel），如果是则不显示错误
      const isTableFile = layerConfig && layerConfig.format &&
        ['csv', 'xls', 'xlsx'].includes(layerConfig.format.toLowerCase());

      if (isTableFile) {
        console.log(`表格文件 ${layerConfig.name} 不需要加载到地图，忽略图层错误`);
        return;
      }

      // 对于其他类型的图层，正常发出错误事件
      console.error('Layer error:', error);
      this.$emit('layer-error', {
        id: layerConfig.id,
        message: error.message || '图层加载失败'
      });
    },

    // 在图层树中添加图层
    addLayerToTree(layerConfig) {
      if (!layerConfig || !layerConfig.id) return;

      // 检查图层是否已存在于图层树中
      const existingIndex = this.layerTree.findIndex(layer => layer.id === layerConfig.id);
      if (existingIndex === -1) {
        // 不存在则添加
        this.layerTree.unshift({
          id: layerConfig.id,
          name: layerConfig.name || '未命名图层',
          type: layerConfig.type || 'vector',
          format: layerConfig.format,
          opacity: 1
        });

        console.log(`图层已添加到图层树: ${layerConfig.id} (${layerConfig.type})`);
      } else {
        console.log(`图层已存在于图层树中: ${layerConfig.id}`);
      }
    },

    // 处理图层选中事件
    handleLayerSelect(data) {
      this.selectedLayerId = data.id;
      console.log('选中图层:', data);
      
      // 如果是栅格图层，检查是否有最大最小值信息
      if (data.type === 'raster') {
        const layer = this.layers[data.id];
        if (layer && (!layer.get('metadata') || layer.get('metadata').min === undefined)) {
          // 如果没有最大最小值信息，尝试从后端获取
          this.fetchDatasetMetadata(data.id).then(metadata => {
            let minValue = null;
            let maxValue = null;
            
            // 从元数据中获取最大最小值
            if (metadata.metadata && metadata.metadata.statistics) {
              minValue = metadata.metadata.statistics.min;
              maxValue = metadata.metadata.statistics.max;
            } else if (metadata.properties && metadata.properties.statistics) {
              minValue = metadata.properties.statistics.min;
              maxValue = metadata.properties.statistics.max;
            } else if (metadata.statistics) {
              minValue = metadata.statistics.min;
              maxValue = metadata.statistics.max;
            }
            
            if (minValue !== null && maxValue !== null) {
              // 更新图层元数据
              layer.set('metadata', {
                min: minValue,
                max: maxValue
              });
              
              // 强制更新视图
              this.$forceUpdate();
            }
          }).catch(error => {
            console.error('获取栅格元数据失败:', error);
          });
        }
      }
    },
    
    // 切换图层可见性
    toggleLayerVisibility(layerId) {
      const layer = this.layers[layerId];
      if (layer && typeof layer.getVisible === 'function') {
        const currentVisible = layer.getVisible();
        layer.setVisible(!currentVisible);
      }
    },
    
    // 检查图层是否可见
    isLayerVisible(layerId) {
      const layer = this.layers[layerId];
      if (layer) {
        if (typeof layer.getVisible === 'function') {
          return layer.getVisible();
        }
        return true; // 表格数据默认视为可见
      }
      return false;
    },
    
    // 获取图层名称
    getLayerName(layerId) {
      const layer = this.layers[layerId];
      if (layer) {
        if (typeof layer.get === 'function') {
          return layer.get('name') || layerId;
        }
        return layer.name || layerId;
      }
      return layerId;
    },
    
    // 获取图层类型
    getLayerType(layerId) {
      const layer = this.layers[layerId];
      if (layer) {
        if (typeof layer.get === 'function') {
          return layer.get('type');
        }
        return layer.type;
      }
      return 'unknown';
    },
    
    // 获取矢量图层样式 (简化版)
    getVectorStyle(layerId) {
      // 从图层样式或默认样式中获取
      const style = this.layerStyles[layerId] || {
        strokeColor: '#1890ff',
        fillColor: 'rgba(255, 255, 255, 0.2)'
      };
      
      return {
        backgroundColor: style.fillColor,
        borderColor: style.strokeColor,
        borderWidth: '2px',
        borderStyle: 'solid'
      };
    },
    
    // 获取栅格图层渐变样式
    getRasterGradientStyle(layerId) {
      const layer = this.layers[layerId];
      let colorStart = '#000000';
      let colorEnd = '#FFFFFF';
      
      // 根据图层类型设置不同的渐变色
      if (layer && layer.get && layer.get('colormap')) {
        console.log(`使用图层 ${layer.get('colormap')} 的色带`);
        const colormap = layer.get('colormap');
        if (colormap && colormap.length >= 2) {
          colorStart = colormap[0];
          colorEnd = colormap[colormap.length - 1];
        }
      }
      
      // 创建渐变
      return {
        background: `linear-gradient(to right, ${colorStart}, ${colorEnd})`,
        height: '20px',
        width: '100%',
        borderRadius: '3px',
        // border: '1px solid rgba(255, 255, 255, 0.2)'
      };
    },
    
    // 获取栅格最小值
    getRasterMinValue(layerId) {
      const layer = this.layers[layerId];
      if (layer && layer.get && layer.get('metadata')) {
        const metadata = layer.get('metadata');
        if (metadata.min !== undefined) {
          return metadata.min.toFixed(2);
        }
      }
      return '无数据';
    },
    
    // 获取栅格最大值
    getRasterMaxValue(layerId) {
      const layer = this.layers[layerId];
      if (layer && layer.get && layer.get('metadata')) {
        const metadata = layer.get('metadata');
        if (metadata.max !== undefined) {
          return metadata.max.toFixed(2);
        }
      }
      return '无数据';
    },

    // 获取图层的属性字段
    getLayerFields(layerId) {
      return new Promise((resolve, reject) => {
        try {
          const layer = this.layers[layerId];
          if (!layer) {
            reject(new Error('图层不存在'));
            return;
          }
          
          // 获取图层源
          const source = layer.getSource();
          if (!source || typeof source.getFeatures !== 'function') {
            reject(new Error('图层不包含矢量数据'));
            return;
          }
          
          // 获取要素
          const features = source.getFeatures();
          if (!features || features.length === 0) {
            reject(new Error('图层不包含要素数据'));
            return;
          }
          
          // 从第一个要素中获取属性字段
          const firstFeature = features[0];
          const properties = firstFeature.getProperties();
          
          // 转换为字段列表
          const fields = [];
          for (const key in properties) {
            if (properties.hasOwnProperty(key)) {
              // 跳过几何字段
              if (key === 'geometry' || key === 'geom' || key === 'the_geom') continue;
              
              // 确定字段类型
              let type = 'string';
              const value = properties[key];
              if (typeof value === 'number') {
                type = 'number';
              } else if (value instanceof Date) {
                type = 'date';
              } else if (typeof value === 'boolean') {
                type = 'boolean';
              }
              
              fields.push({
                name: key,
                type: type,
                sample: value
              });
            }
          }
          
          console.log('获取到图层字段:', fields);
          resolve(fields);
        } catch (error) {
          console.error('获取图层字段失败:', error);
          reject(error);
        }
      });
    },

    // 应用简单样式
    applySimpleStyle(layerId) {
      const layer = this.layers[layerId];
      if (!layer || typeof layer.setStyle !== 'function') return;
      
      // 生成随机颜色
      const getRandomColor = () => {
        const letters = '0123456789ABCDEF';
        let color = '#';
        for (let i = 0; i < 6; i++) {
          color += letters[Math.floor(Math.random() * 16)];
        }
        return color;
      };
      
      const strokeColor = getRandomColor();
      const fillColor = strokeColor + 'AA'; // 添加透明度 AA (约66%)
      
      // 保存样式配置
      this.$set(this.layerStyleConfigs, layerId, {
        type: 'simple',
        field: null,
        colorRamp: null,
        legend: [
          { label: layer.get('name') || layerId, color: fillColor, stroke: strokeColor }
        ]
      });
      
      // 应用简单样式
      layer.setStyle(new Style({
        fill: new Fill({
          color: fillColor
        }),
        stroke: new Stroke({
          color: strokeColor,
          width: 2
        }),
        image: new Circle({
          radius: 7,
          fill: new Fill({
            color: strokeColor // 点使用描边色填充，更明显
          }),
           stroke: new Stroke({
            color: '#FFFFFF', // 点要素添加白色边框，使其在深色填充上更突出
            width: 1
          })
        })
      }));
       if (layer.getSource() && typeof layer.getSource().refresh === 'function') {
        layer.getSource().refresh();
      }
      this.$forceUpdate(); // 强制更新以刷新图例
    },
    
    // 应用分类样式 - 根据属性值的不同类别使用不同颜色
    applyCategorizedStyle(layerId, fieldName, colorRamp) {
      const layer = this.layers[layerId];
      if (!layer || typeof layer.setStyle !== 'function') return;
      
      const source = layer.getSource();
      if (!source || typeof source.getFeatures !== 'function') return;
      const features = source.getFeatures();
      
      const uniqueValues = new Set();
      features.forEach(feature => {
        const value = feature.get(fieldName);
        if (value !== undefined && value !== null) {
          uniqueValues.add(value.toString());
        }
      });
      
      const categories = Array.from(uniqueValues);
      if (categories.length === 0) {
        this.$message.warning(`字段 '${fieldName}' 没有有效值用于分类渲染。`);
        this.applySimpleStyle(layerId); // 回退
        return;
      }
      
      const colorScheme = this.getColorScheme(colorRamp, categories.length);
      const colorMap = {};
      const legend = categories.map((category, index) => {
        const color = colorScheme[index % colorScheme.length];
        colorMap[category] = color;
        return {
          value: category,
          label: category.toString(),
          color: color + 'AA', // 添加透明度
          stroke: color
        };
      });
      
      this.$set(this.layerStyleConfigs, layerId, {
        type: 'categorized',
        field: fieldName,
        colorRamp,
        categories,
        colorMap,
        legend
      });
      
      layer.setStyle((feature) => {
        const value = feature.get(fieldName);
        const valueStr = value !== undefined && value !== null ? value.toString() : '';
        const baseColor = colorMap[valueStr] || '#CCCCCC'; // 默认灰色
        const fillColor = baseColor + 'AA';
        
        return new Style({
          fill: new Fill({
            color: fillColor
          }),
          stroke: new Stroke({
            color: baseColor,
            width: 2
          }),
          image: new Circle({
            radius: 7,
            fill: new Fill({
              color: baseColor
            }),
            stroke: new Stroke({
              color: '#FFFFFF',
              width: 1
            })
          })
        });
      });
       if (layer.getSource() && typeof layer.getSource().refresh === 'function') {
        layer.getSource().refresh();
      }
      this.$forceUpdate();
    },
    
    // 应用分级样式 - 根据数值字段分级
    applyGraduatedStyle(layerId, fieldName, colorRamp) {
      const layer = this.layers[layerId];
      if (!layer || typeof layer.setStyle !== 'function') return;

      const source = layer.getSource();
      if (!source || typeof source.getFeatures !== 'function') return;
      const features = source.getFeatures();
      
      const values = [];
      features.forEach(feature => {
        const value = parseFloat(feature.get(fieldName));
        if (!isNaN(value)) {
          values.push(value);
        }
      });
      
      if (values.length === 0) {
        this.$message.warning(`字段 '${fieldName}' 没有有效的数值用于分级渲染。`);
        this.applySimpleStyle(layerId); // 回退
        return;
      }
      
      const numClasses = 5; // 默认分5个等级
      const breaks = this.calculateJenksBreaks(values, Math.min(numClasses, values.length)); // 使用Jenks确保分类效果
      const minVal = Math.min(...values);
      const maxVal = Math.max(...values);
      
      const colorScheme = this.getColorScheme(colorRamp, breaks.length + 1); // 需要的颜色比断点多一个
      const legend = [];

      for (let i = 0; i <= breaks.length; i++) {
        const lowerBound = (i === 0) ? minVal : breaks[i-1];
        const upperBound = (i === breaks.length) ? maxVal : breaks[i];
        let label = '';
        if (i === 0) {
          label = `< ${upperBound.toFixed(2)}`;
        } else if (i === breaks.length) {
          label = `>= ${lowerBound.toFixed(2)}`;
        } else {
          label = `${lowerBound.toFixed(2)} - ${upperBound.toFixed(2)}`;
        }
        // 确保上限不小于下限，特别是在只有一个断点或数据分布极端的情况下
        if (upperBound < lowerBound && i === breaks.length) {
           label = `>= ${lowerBound.toFixed(2)}`;
        }

        legend.push({
          lowerBound,
          upperBound,
          label,
          color: colorScheme[i] + 'AA',
          stroke: colorScheme[i]
        });
      }
      
      this.$set(this.layerStyleConfigs, layerId, {
        type: 'graduated',
        field: fieldName,
        colorRamp,
        breaks,
        min: minVal,
        max: maxVal,
        numClasses: breaks.length + 1,
        legend
      });
      
      layer.setStyle((feature) => {
        const value = parseFloat(feature.get(fieldName));
        let styleColor = '#CCCCCC'; // 默认颜色

        if (!isNaN(value)) {
          for (let i = 0; i < legend.length; i++) {
            if (i === 0 && value < legend[i].upperBound) {
              styleColor = legend[i].stroke;
              break;
            }
            if (i === legend.length - 1 && value >= legend[i].lowerBound) {
               styleColor = legend[i].stroke;
               break;
            }
            if (value >= legend[i].lowerBound && value < legend[i].upperBound) {
              styleColor = legend[i].stroke;
              break;
            }
          }
        }
        const fillColor = styleColor + 'AA';

        return new Style({
          fill: new Fill({
            color: fillColor
          }),
          stroke: new Stroke({
            color: styleColor,
            width: 2
          }),
          image: new Circle({
            radius: 7,
            fill: new Fill({
              color: styleColor
            }),
            stroke: new Stroke({
              color: '#FFFFFF',
              width: 1
            })
          })
        });
      });
       if (layer.getSource() && typeof layer.getSource().refresh === 'function') {
        layer.getSource().refresh();
      }
      this.$forceUpdate();
    },
    
    // 计算分级断点 (Jenks Natural Breaks)
    calculateJenksBreaks(data, numClasses) {
      if (numClasses <= 0) return [];
      data = data.slice().sort((a, b) => a - b);
      if (numClasses >= data.length) {
        // 如果类别数大于或等于数据点数，则每个点自成一类 (返回中间值作为断点)
        return data.slice(0, -1).map((d, i) => (d + data[i+1])/2);
      }

      let matrix = Array(data.length + 1).fill(0).map(() => Array(numClasses + 1).fill(0));
      let backMatrix = Array(data.length + 1).fill(0).map(() => Array(numClasses + 1).fill(0));

      for (let i = 1; i <= numClasses; i++) {
        matrix[1][i] = 1;
        backMatrix[1][i] = 0;
        for (let j = 2; j <= data.length; j++) {
          matrix[j][i] = Infinity;
        }
      }

      for (let rangeEnd = 2; rangeEnd <= data.length; rangeEnd++) {
        let sum = 0;
        let sumSquares = 0;
        let w = 0;
        let dataVal;

        for (let rangeStart = rangeEnd; rangeStart >= 1; rangeStart--) {
          let i = rangeEnd - rangeStart;
          dataVal = data[i];
          sumSquares += dataVal * dataVal;
          sum += dataVal;
          w++;
          let gvf = sumSquares - (sum * sum) / w;
          let i4 = rangeStart - 1;

          if (i4 !== 0) {
            for (let classNum = 2; classNum <= numClasses; classNum++) {
              if (matrix[rangeEnd][classNum] > (matrix[i4][classNum - 1] + gvf)) {
                matrix[rangeEnd][classNum] = matrix[i4][classNum - 1] + gvf;
                backMatrix[rangeEnd][classNum] = i4;
              }
            }
          }
        }
      }

      let k = data.length;
      const breaks = [];

      for (let i = numClasses; i >= 2; i--) {
        let id = backMatrix[k][i];
        breaks.push(data[id -1]); // Jenks returns upper bounds of classes
        k = id;
      }
      // Jenks算法返回的是每个类别的上限，我们需要的是断点值，通常是两个类别之间的值
      // 为了简化，我们这里直接使用上限值，但在实际应用中可能需要调整为 (data[id-1] + data[id])/2
      return breaks.sort((a,b) => a-b);
    },
    // 获取颜色方案
    getColorScheme(colorRamp, count) {
      const colorSchemes = {
        blues: ['#f7fbff', '#deebf7', '#c6dbef', '#9ecae1', '#6baed6', '#4292c6', '#2171b5', '#08519c', '#08306b'],
        reds: ['#fff5f0', '#fee0d2', '#fcbba1', '#fc9272', '#fb6a4a', '#ef3b2c', '#cb181d', '#a50f15', '#67000d'],
        greens: ['#f7fcf5', '#e5f5e0', '#c7e9c0', '#a1d99b', '#74c476', '#41ab5d', '#238b45', '#006d2c', '#00441b'],
        spectral: ['#9e0142', '#d53e4f', '#f46d43', '#fdae61', '#fee08b', '#ffffbf', '#e6f598', '#abdda4', '#66c2a5', '#3288bd', '#5e4fa2'],
        jet: ['#00007F', '#0000FF', '#007FFF', '#00FFFF', '#7FFF7F', '#FFFF00', '#FF7F00', '#FF0000', '#7F0000']
      };

      if (colorRamp === 'random') {
        const randomColors = [];
        const getRandomHexColor = () => {
          let color = '#';
          for (let i = 0; i < 6; i++) {
            color += '0123456789ABCDEF'[Math.floor(Math.random() * 16)];
          }
          return color;
        };
        for (let i = 0; i < count; i++) {
          randomColors.push(getRandomHexColor());
        }
        return randomColors;
      }
      
      const scheme = colorSchemes[colorRamp] || colorSchemes.blues; // Default to blues if ramp not found
      
      // 如果需要的颜色数量小于方案中的颜色数量，则选择等距的子集
      if (count <= 0) return [];
      if (count === 1) return [scheme[Math.floor(scheme.length / 2)]]; // Return middle color for count 1
      
      if (count < scheme.length) {
        const result = [];
        // Ensure step is at least 1 to avoid infinite loop if scheme.length / count < 1
        const step = Math.max(1, Math.floor((scheme.length -1) / (count -1) )); 
        for (let i = 0; i < count; i++) {
          result.push(scheme[Math.min(i * step, scheme.length - 1)]);
        }
        return result;
      }
      
      // 如果需要的颜色数量大于方案中的颜色数量，则重复使用，并尽量保持颜色均匀分布
      const extendedScheme = [];
      for (let i = 0; i < count; i++) {
        extendedScheme.push(scheme[i % scheme.length]);
      }
      return extendedScheme;
    },

    // 添加removeAllLayers方法
    removeAllLayers() {
      // 弹出确认框
      this.$confirm('确定要移除所有图层吗？', '提示', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }).then(() => {
        // 获取所有非底图图层的ID
        const layerIds = [...this.layerTree.map(layer => layer.id)];
        
        // 移除每个图层
        layerIds.forEach(id => {
          if (this.layers[id]) {
            // 如果是普通图层，从地图上移除
            if (!this.layers[id].isTable) {
              this.map.removeLayer(this.layers[id]);
            }
            delete this.layers[id];
          }
        });
        
        // 清空图层树
        this.layerTree = [];
        
        // 清除选中状态
        this.selectedLayerId = null;
        
        // 提示用户
        this.$message({
          type: 'success',
          message: '已清除所有图层'
        });
        
        // 发送事件
        this.$emit('layers-cleared');
      }).catch(() => {
        // 用户取消操作
        this.$message({
          type: 'info',
          message: '已取消清除操作'
        });
      });
    },
  }
}
</script>

<style scoped>
.map-container {
  width: 100%;
  height: 100%;
  position: relative;
  transition: all 0.3s;
}

#map {
  width: 100%;
  height: 100%;
  transition: all 0.3s;
}

.map-tools {
  position: absolute;
  top: 10px;
  left: 480px;
  z-index: 1;
  /* background-color: var(--map-control-bg); */
  padding: 8px;
  border-radius: 8px;
  box-shadow: 0 2px 12px var(--shadow-color);
  transition: all 0.3s;
  backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
}

.map-tools .el-button {
  transition: all 0.2s;
  padding: 6px;
}

.map-tools .el-button:hover {
  transform: scale(1.1);
  background-color: var(--primary-bg);
}

.map-tools .el-divider {
  height: 20px;
  margin: 0 5px;
}

.basemap-selector {
  position: absolute;
  top: 11px;
  left: 350px;
  z-index: 1;
  transition: all 0.3s;
}

.basemap-selector .el-button {
  background-color: var(--map-control-bg);
  backdrop-filter: blur(8px);
  box-shadow: 0 2px 8px var(--shadow-color);
  transition: all 0.3s;
}

.basemap-selector .el-button:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.coordinate-display {
  position: absolute;
  bottom: 10px;
  right: 10px;
  background-color: var(--map-control-bg);
  padding: 5px 10px;
  border-radius: 4px;
  font-size: 12px;
  box-shadow: 0 2px 8px var(--shadow-color);
  backdrop-filter: blur(8px);
  z-index: 1;
  transition: all 0.3s;
  color: var(--primary-text);
}

.coordinate-display span {
  margin-right: 10px;
}

.layer-control {
  position: absolute;
  top: 10px;
  left: 10px;
  background-color: var(--map-control-bg);
  padding: 12px;
  border-radius: 8px;
  max-height: 600px;
  overflow-y: auto;
  width: 300px;
  z-index: 1;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.3);
  backdrop-filter: blur(10px);
  color: #fff;
}

.layer-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
  padding-bottom: 10px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.layer-header h4 {
  margin: 0;
  font-size: 16px;
  font-weight: 500;
  color: var(--primary-text);
}

.layer-header-buttons {
  display: flex;
  gap: 8px;
}

.layer-header-buttons .el-button {
  transition: all 0.3s;
}

.layer-header-buttons .el-button:hover {
  transform: scale(1.1);
  background-color: var(--primary-bg);
}

.layer-search {
  margin-bottom: 15px;
}

.layer-search :deep(.el-input__inner) {
  background-color: rgba(255, 255, 255, 0.1);
  /* border: none; */
  color: var(--primary-text);
}

/* .layer-search :deep(.el-input__prefix) {
  color: var(--primary-text);
} */

.layer-tree {
  background: transparent;
  color: #fff;
}

.layer-tree :deep(.el-tree-node__content) {
  background-color: transparent;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  height: 40px;
}

.layer-tree :deep(.el-tree-node__content:hover) {
  background-color: rgba(255, 255, 255, 0.1);
}

.layer-tree :deep(.el-checkbox__input.is-checked .el-checkbox__inner) {
  background-color: #409EFF;
  border-color: #409EFF;
}

.custom-tree-node {
  width: 100%;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 5px;
}

.layer-name {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--primary-text);
  font-size: 14px;
  width: 180px;
}

.layer-name-text {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
}

.layer-format {
  font-size: 12px;
  color: #909399;
  margin-left: 4px;
  flex-shrink: 0;
}

.layer-name i {
  color: #409EFF;
}

.layer-name i.el-icon-document-copy {
  color: #67c23a;
}

.layer-name i.el-icon-document {
  color: #409eff;
}

.layer-controls {
  display: flex;
  align-items: center;
  /* gap: 10px; */
}

.layer-visible {
  color: #409EFF;
  cursor: pointer;
  font-size: 16px;
  margin-right: 5px;
}

.layer-hidden {
  color: #909399;
  cursor: pointer;
  font-size: 16px;
  margin-right: 5px;
}

.layer-legend {
  margin-top: 15px;
  background-color: var(--map-control-bg);
  border-radius: 4px;
  padding: 10px;
  backdrop-filter: blur(5px);
}

.legend-header {
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  padding-bottom: 8px;
  margin-bottom: 10px;
}

.legend-header h4 {
  margin: 0;
  font-size: 14px;
  font-weight: normal;
  color: var(--primary-text);
}

.legend-content {
  padding: 5px 0;
}

.legend-item {
  display: flex;
  align-items: center;
  margin-bottom: 8px;
}

.legend-symbol {
  width: 20px;
  height: 20px;
  margin-right: 10px;
  border-radius: 3px;
}

.vector-symbol {
  background-color: rgba(255, 255, 255, 0.2);
  border: 2px solid #1890ff;
}

.legend-label {
  font-size: 12px;
  color: var(--primary-text);
}

.raster-legend {
  padding: 5px 0;
  width: 100%;
}

.raster-legend .legend-item {
  display: flex;
  align-items: center;
  justify-content: space-between; /* 使子元素分散对齐 */
  width: 100%;
}

.legend-value-min,
.legend-value-max {
  font-size: 12px;
  color: var(--primary-text);
  white-space: nowrap; /* 防止文本换行 */
}

.raster-gradient {
  flex-grow: 1; /* 使渐变条填充剩余空间 */
  height: 15px; /* 调整高度 */
  border-radius: 3px; /* 保持圆角 */
  margin: 0 8px; /* 在数值和渐变条之间添加间距 */
  background: linear-gradient(to right, white, black); /* 白到黑渐变 */
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2); /* 保持阴影 */
}

.legend-item {
  width: 100%;
}

.el-dropdown-link {
  cursor: pointer;
  color: var(--primary-text);
}

.el-tree-node.is-current > .el-tree-node__content {
  background-color: rgba(64, 158, 255, 0.1) !important;
  color: #409EFF !important;
}

.el-button {
  border: none;
}

.opacity-slider {
  width: 80px;
}

.opacity-slider :deep(.el-slider__runway) {
  background-color: rgba(255, 255, 255, 0.2);
}

.opacity-slider :deep(.el-slider__bar) {
  background-color: #409EFF;
}

.opacity-slider :deep(.el-slider__button) {
  border-color: #409EFF;
  background-color: #fff;
}

.layer-dropdown .el-dropdown-link {
  cursor: pointer;
  color: var(--primary-text);
  font-size: 16px;
  padding: 5px;
  padding-left: 10px;
}

.layer-dropdown .el-dropdown-link:hover {
  color: #409EFF;
}

:deep(.el-dropdown-menu) {
  background-color: rgba(30, 30, 30, 0.95);
  border: 1px solid rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(10px);
}

:deep(.el-dropdown-menu__item) {
  color: var(--primary-text);
  display: flex;
  align-items: center;
  gap: 8px;
}

:deep(.el-dropdown-menu__item:hover) {
  background-color: rgba(64, 158, 255, 0.2);
  color: #409EFF;
}

:deep(.el-dropdown-menu__item i) {
  margin-right: 5px;
}

/* 滚动条样式 */
.layer-control::-webkit-scrollbar {
  width: 6px;
}

.layer-control::-webkit-scrollbar-track {
  background: rgba(255, 255, 255, 0.1);
  border-radius: 3px;
}

.layer-control::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.2);
  border-radius: 3px;
}

.layer-control::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.3);
}

.measure-tooltip {
  position: absolute;
  bottom: 20px;
  left: 50%;
  transform: translateX(-50%);
  background-color: var(--map-control-bg);
  color: var(--primary-text);
  padding: 5px 10px;
  border-radius: 4px;
  box-shadow: 0 2px 12px 0 var(--shadow-color);
  z-index: 2;
  font-weight: bold;
  transition: all 0.3s;
  backdrop-filter: blur(8px);
}

/* 适配OpenLayers控件样式以匹配主题 */
:deep(.ol-control) {
  background-color: var(--map-control-bg);
  border-radius: 4px;
  padding: 2px;
  transition: all 0.3s;
  backdrop-filter: blur(8px);
}

:deep(.ol-control button) {
  background-color: rgba(0, 60, 136, 0.7);
  color: white;
  border-radius: 4px;
  transition: all 0.2s;
}

:deep(.ol-control button:hover) {
  background-color: rgba(0, 60, 136, 1);
  transform: scale(1.1);
}

/* 地图动画效果 */
:deep(.ol-zoom-in),
:deep(.ol-zoom-out) {
  transition: transform 0.2s;
}

:deep(.ol-zoom-in:hover),
:deep(.ol-zoom-out:hover) {
  transform: scale(1.1);
}

html[data-theme='dark'] :deep(.ol-control button) {
  background-color: rgba(64, 158, 255, 0.7);
}

html[data-theme='dark'] :deep(.ol-control button:hover) {
  background-color: rgba(64, 158, 255, 1);
}

/* 统计对话框样式 */
:deep(.statistics-dialog) {
  background-color: var(--background-color);
  border-radius: 8px;
  overflow: hidden;
}

:deep(.statistics-dialog .el-dialog__header) {
  background-color: var(--map-control-bg);
  padding: 15px 20px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

:deep(.statistics-dialog .el-dialog__body) {
  padding: 0;
  height: 70vh;
  overflow: hidden;
}

.analysis-tools .el-button:hover {
  background-color: var(--primary-color);
  color: #fff;
}

html[data-theme='dark'] .analysis-tools .el-button:hover {
  background-color: #409EFF;
}
</style>