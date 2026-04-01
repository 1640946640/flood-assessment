import Vue from 'vue'
import VueRouter from 'vue-router'
import DataVisualization from '../views/DataVisualization.vue'

Vue.use(VueRouter)

const routes = [
  {
    path: '/',
    redirect: '/data-visualization'
  },
  {
    path: '/data-visualization',
    name: 'DataVisualization',
    component: DataVisualization
  },
  {
    path: '/auxiliary',
    name: 'Auxiliary',
    component: () => import('../views/AuxiliaryLayout.vue'),
    children: [
      {
        path: 'create-grid',
        name: 'CreateGridView',
        component: () => import('../views/CreateGridView.vue')
      },
      {
        path: 'correlation-analysis',
        name: 'CorrelationAnalysis',
        component: () => import('../views/CorrelationAnalysis.vue')
      },
      {
        path: 'raster-compare',
        name: 'RasterCompare',
        component: () => import('../views/RasterCompare.vue')
      },
      {
        path: 'export-csv',
        name: 'ExportCSV',
        component: () => import('../views/ExportCSV.vue')
      },
      {
        path: 'raster-alignment',
        name: 'RasterAlignment',
        component: () => import('../views/RasterAlignment.vue')
      },
      {
        path: 'raster-statistics',
        name: 'RasterStatistics',
        component: () => import('../views/RasterStatistics.vue')
      },
      {
        path: 'flood-points',
        name: 'FloodPointsView',
        component: () => import('../views/FloodPointsView.vue')
      }
    ]
  },
  {
    path: '/flood-assessment',
    name: 'FloodAssessment',
    component: () => import('../views/FloodAssessment.vue')
  },
  {
    path: '/about',
    name: 'About',
    component: () => import('../views/IntegratedAssessment.vue')
  }
]

const router = new VueRouter({
  mode: 'hash',
  base: process.env.BASE_URL,
  routes
})

export default router