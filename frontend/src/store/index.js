import Vue from 'vue'
import Vuex from 'vuex'
import axios from 'axios'

Vue.use(Vuex)

export default new Vuex.Store({
  state: {
    // 地图数据
    mapLayers: [],
    // 当前选中的图层
    activeLayer: null,
    // 空间数据集
    spatialDatasets: [],
    // 分析结果
    analysisResults: [],
    // 评估模型
    assessmentModels: [
      { id: 1, name: '加权平均法', key: 'weighted_average' },
      { id: 2, name: '层次分析法', key: 'ahp' },
      { id: 3, name: '熵权法', key: 'entropy' }
    ],
    // 评估结果
    assessmentResults: [],
    // 预测模型
    predictionModels: [
      { id: 1, name: '线性回归', key: 'linear_regression' },
      { id: 2, name: '随机森林', key: 'random_forest' },
      { id: 3, name: '神经网络', key: 'neural_network' },
      { id: 4, name: 'ARIMA时间序列分析', key: 'arima' }
    ],
    // 预测结果
    predictionResults: [],
    // 全局状态
    theme: localStorage.getItem('theme') || 'light',
    datasets: [], // 所有数据集
    loading: false
  },
  mutations: {
    // 设置地图图层
    SET_MAP_LAYERS(state, layers) {
      state.mapLayers = layers
    },
    // 设置活动图层
    SET_ACTIVE_LAYER(state, layer) {
      state.activeLayer = layer 
    },
    // 添加空间数据集
    ADD_SPATIAL_DATASET(state, dataset) {
      state.spatialDatasets.push(dataset)
    },
    // 设置空间数据集
    SET_SPATIAL_DATASETS(state, datasets) {
      state.spatialDatasets = datasets
    },
    // 添加分析结果
    ADD_ANALYSIS_RESULT(state, result) {
      state.analysisResults.push(result)
    },
    // 添加评估结果
    ADD_ASSESSMENT_RESULT(state, result) {
      state.assessmentResults.push(result)
    },
    // 添加预测结果
    ADD_PREDICTION_RESULT(state, result) {
      state.predictionResults.push(result)
    },
    SET_THEME(state, theme) {
      state.theme = theme
      localStorage.setItem('theme', theme)
    },
    SET_DATASETS(state, datasets) {
      // 确保数据集是正确的格式
      if (typeof datasets === 'string') {
        try {
          state.datasets = JSON.parse(datasets)
        } catch (error) {
          console.error('解析数据集JSON失败:', error)
          state.datasets = []
        }
      } else {
        state.datasets = datasets || []
      }
    },
    SET_LOADING(state, loading) {
      state.loading = loading
    }
  },
  actions: {
    // 从服务器获取数据集
    async fetchDatasets({ commit }) {
      commit('SET_LOADING', true)
      
      // 使用API基础URL
      
      
      try {
        const response = await axios.get(`/api/datasets`)
        console.log('response', response);
        commit('SET_SPATIAL_DATASETS', response.data)
        commit('SET_DATASETS', response.data)
        commit('SET_LOADING', false)
        return response.data
      } catch (error) {
        console.error('获取数据集失败:', error)
        commit('SET_LOADING', false)
        return Promise.reject(error)
      }
    },
    // 执行空间分析
    async runSpatialAnalysis({ commit }, params) {
      try {
        // 确保params中包含datasets参数
        if (!params.datasets && params.datasetId) {
          params.datasets = [params.datasetId]
        }
        
        const response = await Vue.prototype.$http.post('/analysis', params)
        commit('ADD_ANALYSIS_RESULT', response.data)
        return response.data
      } catch (error) {
        console.error('空间分析失败:', error)
        throw error
      }
    },
    // 执行综合评估
    async runIntegratedAssessment({ commit }, params) {
      try {
        const response = await Vue.prototype.$http.post('/assessment', params)
        commit('ADD_ASSESSMENT_RESULT', response.data)
        return response.data
      } catch (error) {
        console.error('综合评估失败:', error)
        throw error
      }
    },
    // 执行时序预测
    async runPrediction({ commit }, params) {
      try {
        const response = await Vue.prototype.$http.post('/prediction', params)
        commit('ADD_PREDICTION_RESULT', response.data)
        return response.data
      } catch (error) {
        console.error('时序预测失败:', error)
        throw error
      }
    },
    toggleTheme({ commit, state }) {
      const newTheme = state.theme === 'light' ? 'dark' : 'light'
      commit('SET_THEME', newTheme)
      
      // 应用主题到HTML元素
      document.documentElement.setAttribute('data-theme', newTheme)
    }
  },
  getters: {
    isDarkMode: state => state.theme === 'dark',
    // 获取所有矢量数据集
    vectorDatasets: state => state.datasets.filter(dataset => dataset.type === 'vector'),
    // 获取所有栅格数据集
    rasterDatasets: state => state.datasets.filter(dataset => dataset.type === 'raster')
  }
})