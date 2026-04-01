<template>
    <div class="integrated-assessment">
        <el-container class="main-container" :class="{ 'tools-hidden': !showTools }">
            <el-main class="map-main">
                <MapView ref="mapView" @map-initialized="handleMapInitialized" @layer-added="handleLayerAdded"
                    @layer-error="handleLayerError" @layer-exists="handleLayerExists" />
            </el-main>

            <!-- 工具面板折叠按钮 -->
            <div class="toggle-tools-panel" @click="toggleTools">
                <i :class="showTools ? 'el-icon-arrow-right' : 'el-icon-arrow-left'"></i>
            </div>

            <el-aside class="tools-aside" v-show="showTools">
                <div class="tools-container">

                    <el-tabs v-model="activeTab" type="border-card">
                        <!-- 生态系统物理健康评估 -->
                        <el-tab-pane label="生态系统物理健康评估" name="physical">
                            <el-card class="assessment-card">
                                <div slot="header">
                                    <span>生态系统物理健康评估</span>
                                </div>
                                <div class="assessment-content">
                                    <p>请选择以下三类数据集:</p>
                                    <el-form :model="physicalParams" label-width="160px" size="small">
                                        <el-form-item label="生态系统组织（EO）">
                                            <el-input v-model="physicalParams.eoDisplayName" placeholder="请选择EO数据集"
                                                readonly class="dataset-display"
                                                @click.native="showDatasetSelector('eo')">
                                            </el-input>
                                        </el-form-item>
                                        <el-form-item label="生态系统活力（EV）">
                                            <el-input v-model="physicalParams.evDisplayName" placeholder="请选择EV数据集"
                                                readonly class="dataset-display"
                                                @click.native="showDatasetSelector('ev')">
                                            </el-input>
                                        </el-form-item>
                                        <el-form-item label="生态系统韧性（ER）">
                                            <el-input v-model="physicalParams.erDisplayName" placeholder="请选择ER数据集"
                                                readonly class="dataset-display"
                                                @click.native="showDatasetSelector('er')">
                                            </el-input>
                                        </el-form-item>

                                        <!-- 通用数据集选择器 -->
                                        <el-dialog title="选择数据集" :visible.sync="datasetSelectorVisible" width="500px"
                                            :before-close="handleDatasetSelectorClose" append-to-body>
                                            <dataset-selector ref="currentSelector" :showCheckbox="true"
                                                :selectionMode="currentSelectorMode" :allowedTypes="currentAllowedTypes"
                                                @selected-datasets-change="handleDatasetSelection" />
                                            <span slot="footer" class="dialog-footer">
                                                <el-button @click="handleDatasetSelectorClose">取消</el-button>
                                                <el-button type="primary"
                                                    @click="confirmDatasetSelection">确定</el-button>
                                            </span>
                                        </el-dialog>
                                        <el-form-item label="结果名称">
                                            <el-input v-model="physicalParams.resultName"
                                                placeholder="请输入结果名称"></el-input>
                                        </el-form-item>
                                        <el-form-item>
                                            <el-button type="primary" @click="runPhysicalAssessment"
                                                :loading="loading.physical">开始评估</el-button>
                                            <el-button @click="resetPhysicalParams">重置</el-button>
                                        </el-form-item>
                                    </el-form>
                                </div>
                            </el-card>
                        </el-tab-pane>

                        <!-- 生态系统服务评估 -->
                        <el-tab-pane label="生态系统服务评估" name="service">
                            <el-card class="assessment-card">
                                <div slot="header">
                                    <span>生态系统服务评估</span>
                                </div>
                                <div class="assessment-content">
                                    <p>请选择以下三类数据集:</p>
                                    <el-form :model="serviceParams" label-width="160px" size="small">
                                        <el-form-item label="产水服务">
                                            <el-input v-model="serviceParams.waterDisplayName" placeholder="请选择产水服务数据集"
                                                readonly class="dataset-display"
                                                @click.native="showDatasetSelector('water')">
                                            </el-input>
                                        </el-form-item>
                                        <el-form-item label="固碳服务">
                                            <el-input v-model="serviceParams.carbonDisplayName" placeholder="请选择固碳服务数据集"
                                                readonly class="dataset-display"
                                                @click.native="showDatasetSelector('carbon')">
                                            </el-input>
                                        </el-form-item>
                                        <el-form-item label="土壤保持服务">
                                            <el-input v-model="serviceParams.soilDisplayName" placeholder="请选择土壤保持服务数据集"
                                                readonly class="dataset-display"
                                                @click.native="showDatasetSelector('soil')">
                                            </el-input>
                                        </el-form-item>
                                        <el-form-item label="结果名称">
                                            <el-input v-model="serviceParams.resultName"
                                                placeholder="请输入结果名称"></el-input>
                                        </el-form-item>
                                        <el-form-item>
                                            <el-button type="primary" @click="runServiceAssessment"
                                                :loading="loading.service">开始评估</el-button>
                                            <el-button @click="resetServiceParams">重置</el-button>
                                        </el-form-item>
                                    </el-form>
                                </div>
                            </el-card>


                        </el-tab-pane>

                        <!-- 生态系统健康评估 -->
                        <el-tab-pane label="生态系统健康评估" name="health">
                            <el-card class="assessment-card">
                                <div slot="header">
                                    <span>生态系统健康评估</span>
                                </div>
                                <div class="assessment-content">
                                    <p>请选择物理健康和服务评估结果文件夹:</p>
                                    <el-form :model="healthParams" label-width="120px" size="small">
                                        <el-form-item label="物理健康结果">
                                            <el-input v-model="healthParams.physicalDisplayName"
                                                placeholder="请选择物理健康数据集" readonly class="dataset-display"
                                                @click.native="showDatasetSelector('physical')">
                                            </el-input>
                                        </el-form-item>
                                        <el-form-item label="服务评估结果">
                                            <el-input v-model="healthParams.serviceDisplayName" placeholder="请选择服务评估数据集"
                                                readonly class="dataset-display"
                                                @click.native="showDatasetSelector('service')">
                                            </el-input>
                                        </el-form-item>
                                        <el-form-item label="结果名称">
                                            <el-input v-model="healthParams.resultName"
                                                placeholder="请输入结果名称"></el-input>
                                        </el-form-item>
                                        <el-form-item>
                                            <el-button type="primary" @click="runHealthAssessment"
                                                :loading="loading.health">开始评估</el-button>
                                            <el-button @click="resetHealthParams">重置</el-button>
                                        </el-form-item>
                                    </el-form>
                                </div>
                            </el-card>


                        </el-tab-pane>

                        <!-- 生态保护修复区评估 -->
                        <el-tab-pane label="生态保护修复区评估" name="protection">
                            <el-card class="assessment-card">
                                <div slot="header">
                                    <span>生态保护修复区评估</span>
                                </div>
                                <div class="assessment-content">
                                    <p>请选择生态保护修复区数据集:</p>
                                    <el-form :model="protectionParams" label-width="120px" size="small">
                                        <el-form-item label="生态系统健康评估结果">
                                            <el-input v-model="protectionParams.healthDisplayName"
                                                placeholder="请选择生态系统健康评估数据集" readonly class="dataset-display"
                                                @click.native="showDatasetSelector('health')">
                                            </el-input>
                                        </el-form-item>
                                        <el-form-item label="生态系统活力趋势分析结果">
                                            <el-input v-model="protectionParams.trendDisplayName"
                                                placeholder="请选择生态系统活力趋势分析数据集" readonly class="dataset-display"
                                                @click.native="showDatasetSelector('trend')">
                                            </el-input>
                                        </el-form-item>
                                        <el-form-item label="结果名称">
                                            <el-input v-model="protectionParams.resultName"
                                                placeholder="请输入结果名称"></el-input>
                                        </el-form-item>
                                        <el-form-item>
                                            <el-button type="primary" @click="runProtectionAssessment"
                                                :loading="loading.protection">开始评估</el-button>
                                            <el-button @click="resetProtectionParams">重置</el-button>
                                        </el-form-item>
                                    </el-form>
                                </div>
                            </el-card>


                        </el-tab-pane>
                    </el-tabs>

                    <!-- 统一的评估结果列表 -->
                    <el-card class="results-card">
                        <div slot="header">
                            <span>评估结果列表</span>
                            <!-- <el-button style="float: right; padding: 3px 0" type="text" @click="refreshResults">刷新</el-button> -->
                        </div>
                        <div class="results-list">
                            <el-table
                                :data="physicalResults.concat(serviceResults).concat(healthResults).concat(protectionResults)"
                                style="width: 100%" border size="mini">
                                <el-table-column prop="name" label="名称"></el-table-column>
                                <el-table-column prop="type" label="类型" width="100">
                                    <template slot-scope="scope">
                                        <el-tag size="mini" :type="getAssessmentTypeTag(scope.row.type)">{{
                                            getAssessmentTypeName(scope.row.type) }}</el-tag>
                                    </template>
                                </el-table-column>
                                <el-table-column prop="createdAt" label="创建时间" width="160"></el-table-column>
                                <el-table-column label="操作" width="150">
                                    <template slot-scope="scope">
                                        <el-button type="text" size="small"
                                            @click="viewResult(scope.row)">查看</el-button>
                                        <!-- <el-button type="text" size="small"
                                            @click="downloadResult(scope.row)">下载</el-button> -->
                                    </template>
                                </el-table-column>
                            </el-table>
                        </div>
                    </el-card>

                    <!-- 评估结果详情卡片 -->
                    <assessment-result-cards v-if="currentResult" :result="currentResult" :apiBaseUrl="apiBaseUrl" />
                    <!-- 图片选择器 -->
                    <img-selector path="assessment_results" title="评估结果" />
                </div>

            </el-aside>
        </el-container>




    </div>
</template>

<script>
import { mapGetters, mapActions, mapState } from 'vuex';
import MapView from '@/components/MapView.vue';
import ChartView from '@/components/ChartView.vue';
import ToolsPanelMixin from '@/mixins/ToolsPanelMixin';
import axios from 'axios';
import DatasetSelector from '@/components/DatasetSelector.vue';
import AssessmentResultCards from '@/components/AssessmentResultCards.vue';
import ImgSelector from '@/components/ImgSelector.vue';

export default {
    name: 'IntegratedAssessment',
    components: {
        MapView,
        ChartView,
        DatasetSelector,
        AssessmentResultCards,
        ImgSelector
    },
    mixins: [ToolsPanelMixin], data() {
        return {
            activeTab: 'physical',
            map: null,
            showTools: true,
            datasetSelectorVisible: false, // 是否显示数据集选择器
            selectorTypeList: ['eo', 'ev', 'er', 'water', 'carbon', 'soil'], // 选择器类型列表
            currentSelectorType: null, // 当前选择器类型: 'eo', 'ev', 'er', 'service'
            currentSelectorMode: 'single', // 当前选择器模式: 'single' 或 'multiple'
            currentAllowedTypes: [], // 当前选择器允许的类型
            modelSelectorSettingsList: {
                eo: {
                    selectorMode: 'multiple',
                    allowedTypes: ['raster'],
                },
                ev: {
                    selectorMode: 'multiple',
                    allowedTypes: ['raster'],
                },
                er: {
                    selectorMode: 'multiple',
                    allowedTypes: ['raster'],
                },
                water: {
                    selectorMode: 'multiple',
                    allowedTypes: ['raster'],
                },
                carbon: {
                    selectorMode: 'multiple',
                    allowedTypes: ['raster'],
                },
                soil: {
                    selectorMode: 'multiple',
                    allowedTypes: ['raster'],
                },
                physical: {
                    selectorMode: 'multiple',
                    allowedTypes: ['raster'],
                },
                service: {
                    selectorMode: 'multiple',
                    allowedTypes: ['raster'],
                },
                health: {
                    selectorMode: 'multiple',
                    allowedTypes: ['raster'],
                },
                trend: {
                    selectorMode: 'multiple',
                    allowedTypes: ['raster'],
                },
            },
            loading: {
                physical: false,
                service: false,
                health: false,
                protection: false
            },
            physicalParams: {
                resultName: '',
                eoDataset: null,
                evDataset: null,
                erDataset: null,
                eoDisplayName: '',
                evDisplayName: '',
                erDisplayName: ''
            },
            serviceParams: {
                resultName: '',
                waterDataset: null,
                carbonDataset: null,
                soilDataset: null,
                waterDisplayName: '',
                carbonDisplayName: '',
                soilDisplayName: ''
            },
            healthParams: {
                resultName: '',
                physicalResult: null,
                serviceResult: null,
                physicalDisplayName: '',
                serviceDisplayName: ''
            },
            protectionParams: {
                resultName: '',
                healthResult: null,
                trendResult: null,
                healthDisplayName: '',
                trendDisplayName: ''
            },
            physicalResults: [],
            serviceResults: [],
            healthResults: [],
            protectionResults: [],
            apiBaseUrl: process.env.VUE_APP_API_URL || 'http://localhost:5000',
            currentResult: null // 当前查看的评估结果
        }
    },
    computed: {
        ...mapState(['datasets']),
    },
    mounted() {
        document.documentElement.style.setProperty('--collapse-width', '500px');
        this.fetchDatasets();
        // this.fetchResults();
    },
    methods: {
        ...mapActions(['fetchDatasets']),

        // 地图初始化完成
        handleMapInitialized(map) {
            this.map = map;
            console.log('地图初始化完成');
        },

        // 图层添加完成
        handleLayerAdded(layer) {
            console.log('图层添加成功:', layer);
        },

        // 图层添加错误
        handleLayerError(error) {
            this.$message.error(`图层添加失败: ${error.message}`);
        },

        // 图层已存在
        handleLayerExists(layerName) {
            this.$message.warning(`图层 ${layerName} 已存在`);
        },


        // 显示数据集选择器
        showDatasetSelector(type) {
            this.currentSelectorType = type;

            this.currentSelectorMode = this.modelSelectorSettingsList[type].selectorMode;
            this.currentAllowedTypes = this.modelSelectorSettingsList[type].allowedTypes;

            // 显示选择器
            this.datasetSelectorVisible = true;

            // 清空当前选择器的选择
            if (this.$refs.currentSelector) {
                this.$refs.currentSelector.clearSelectedDatasets();
            }
        },

        // 处理数据集选择
        handleDatasetSelection(datasets) {
            // 临时保存选择的数据集，等确认后再应用
            this.tempSelectedDatasets = datasets;
        },

        // 确认数据集选择
        confirmDatasetSelection() {
            if (!this.tempSelectedDatasets || this.tempSelectedDatasets.length === 0) {
                this.$message.warning('请至少选择一个数据集');
                return;
            }

            // 获取选择的数据集数量
            const datasetCount = this.tempSelectedDatasets.length;

            switch (this.currentSelectorType) {
                case 'eo':
                    this.physicalParams.eoDataset = this.tempSelectedDatasets.map(d => d.id);
                    this.physicalParams.eoDisplayName = datasetCount > 1 ?
                        `已选择 ${datasetCount} 个数据集: ${this.tempSelectedDatasets[0].name}等` :
                        this.tempSelectedDatasets[0].name;
                    break;
                case 'ev':
                    this.physicalParams.evDataset = this.tempSelectedDatasets.map(d => d.id);
                    this.physicalParams.evDisplayName = datasetCount > 1 ?
                        `已选择 ${datasetCount} 个数据集: ${this.tempSelectedDatasets[0].name}等` :
                        this.tempSelectedDatasets[0].name;
                    break;
                case 'er':
                    this.physicalParams.erDataset = this.tempSelectedDatasets.map(d => d.id);
                    this.physicalParams.erDisplayName = datasetCount > 1 ?
                        `已选择 ${datasetCount} 个数据集: ${this.tempSelectedDatasets[0].name}等` :
                        this.tempSelectedDatasets[0].name;
                    break;
                case 'water':
                    this.serviceParams.waterDataset = this.tempSelectedDatasets.map(d => d.id);
                    this.serviceParams.waterDisplayName = datasetCount > 1 ?
                        `已选择 ${datasetCount} 个数据集: ${this.tempSelectedDatasets[0].name}等` :
                        this.tempSelectedDatasets[0].name;
                    break;
                case 'carbon':
                    this.serviceParams.carbonDataset = this.tempSelectedDatasets.map(d => d.id);
                    this.serviceParams.carbonDisplayName = datasetCount > 1 ?
                        `已选择 ${datasetCount} 个数据集: ${this.tempSelectedDatasets[0].name}等` :
                        this.tempSelectedDatasets[0].name;
                    break;
                case 'soil':
                    this.serviceParams.soilDataset = this.tempSelectedDatasets.map(d => d.id);
                    this.serviceParams.soilDisplayName = datasetCount > 1 ?
                        `已选择 ${datasetCount} 个数据集: ${this.tempSelectedDatasets[0].name}等` :
                        this.tempSelectedDatasets[0].name;
                    break;
                case 'physical':
                    this.healthParams.physicalResult = this.tempSelectedDatasets.map(d => d.id);
                    this.healthParams.physicalDisplayName = datasetCount > 1 ?
                        `已选择 ${datasetCount} 个数据集: ${this.tempSelectedDatasets[0].name}等` :
                        this.tempSelectedDatasets[0].name;
                    break;
                case 'service':
                    this.healthParams.serviceResult = this.tempSelectedDatasets.map(d => d.id);
                    this.healthParams.serviceDisplayName = datasetCount > 1 ?
                        `已选择 ${datasetCount} 个数据集: ${this.tempSelectedDatasets[0].name}等` :
                        this.tempSelectedDatasets[0].name;
                    break;
                case 'health':
                    this.protectionParams.healthResult = this.tempSelectedDatasets.map(d => d.id);
                    this.protectionParams.healthDisplayName = datasetCount > 1 ?
                        `已选择 ${datasetCount} 个数据集: ${this.tempSelectedDatasets[0].name}等` :
                        this.tempSelectedDatasets[0].name;
                    break;
                case 'trend':
                    this.protectionParams.trendResult = this.tempSelectedDatasets.map(d => d.id);
                    this.protectionParams.trendDisplayName = datasetCount > 1 ?
                        `已选择 ${datasetCount} 个数据集: ${this.tempSelectedDatasets[0].name}等` :
                        this.tempSelectedDatasets[0].name;
                    break;
                default:
                    break;
            }


            // 关闭选择器
            this.datasetSelectorVisible = false;
            this.tempSelectedDatasets = null;
        },

        // 关闭数据集选择器
        handleDatasetSelectorClose() {
            this.datasetSelectorVisible = false;
            this.tempSelectedDatasets = null;
        },

        // 执行物理健康评估
        runPhysicalAssessment() {
            if (!this.physicalParams.eoDataset || !this.physicalParams.evDataset || !this.physicalParams.erDataset) {
                this.$message.warning('请选择全部三类数据集');
                return;
            }

            this.loading.physical = true;

            const requestData = {
                eoDataset: this.physicalParams.eoDataset,
                evDataset: this.physicalParams.evDataset,
                erDataset: this.physicalParams.erDataset,
                resultName: this.physicalParams.resultName
            };

            console.log('执行物理健康评估', this.physicalParams);
            axios.post(`/assessment/physical`, requestData)
                .then(response => {
                    this.$message.success('物理健康评估完成');
                    console.log('物理健康评估结果', response.data);
                    const result = response.data;
                    this.physicalResults.unshift(result);
                    this.viewResult(result);
                })
                .catch(error => {
                    console.error('物理健康评估失败', error);
                    this.$message.error('物理健康评估失败: ' + (error.response?.data?.message || error.message));
                })
                .finally(() => {
                    this.loading.physical = false;
                });
        },

        // 执行服务评估
        runServiceAssessment() {
            if (!this.serviceParams.waterDataset || !this.serviceParams.carbonDataset || !this.serviceParams.soilDataset) {
                this.$message.warning('请选择全部三类服务数据集');
                return;
            }

            this.loading.service = true;

            const requestData = {
                waterDataset: this.serviceParams.waterDataset,
                carbonDataset: this.serviceParams.carbonDataset,
                soilDataset: this.serviceParams.soilDataset,
                resultName: this.serviceParams.resultName
            };

            console.log('执行生态系统服务评估', this.serviceParams);
            axios.post(`${this.apiBaseUrl}/api/assessment/service`, requestData)
                .then(response => {
                    this.$message.success('生态系统服务评估完成');
                    console.log('生态系统服务评估结果', response.data);
                    const result = response.data;
                    this.physicalResults.unshift(result);

                    this.viewResult(result);

                })
                .catch(error => {
                    console.error('生态系统服务评估失败', error);
                    this.$message.error('生态系统服务评估失败: ' + (error.response?.data?.message || error.message));
                })
                .finally(() => {
                    this.loading.service = false;
                });
        },

        // 执行健康评估
        runHealthAssessment() {
            if (!this.healthParams.physicalResult || !this.healthParams.serviceResult) {
                this.$message.warning('请选择物理健康和服务评估结果');
                return;
            }

            this.loading.health = true;

            console

            axios.post(`${this.apiBaseUrl}/api/assessment/health`, this.healthParams)
                .then(response => {
                    this.$message.success('生态系统健康评估完成');
                    this.healthResults.unshift(response.data);
                    // 显示结果
                    if (response.data.previewUrl) {
                        this.viewResult(response.data);
                    }
                })
                .catch(error => {
                    console.error('生态系统健康评估失败', error);
                    this.$message.error('生态系统健康评估失败: ' + (error.response?.data?.message || error.message));
                })
                .finally(() => {
                    this.loading.health = false;
                });
        },
        // 运行生态保护修复区评估
        async runProtectionAssessment() {
            if (!this.protectionParams.healthResult || !this.protectionParams.trendResult) {
                this.$message.warning('请选择所需的数据集');
                return;
            }
            // if (!this.protectionParams.resultName) {
            //     this.$message.warning('请输入结果名称');
            //     return;
            // }

            this.loading.protection = true;
            try {
                // 这里添加生态保护修复区评估的具体实现
                await axios.post(`/assessment/protection`, {
                    healthResult: this.protectionParams.healthResult,
                    trendResult: this.protectionParams.trendResult,
                    resultName: this.protectionParams.resultName
                }).then(response => {
                    console.log('生态保护修复区评估成功:', response.data);
                    this.$message.success('评估成功');
                    const result = response.data;
                    this.protectionResults.unshift(result);

                    this.viewResult(result);

                }).catch(error => {
                    console.error('生态保护修复区评估失败:', error);
                    this.$message.error('评估过程中发生错误');
                });
            } catch (error) {
                console.error('生态保护修复区评估失败:', error);
                this.$message.error('评估过程中发生错误');
            } finally {
                this.loading.protection = false;
            }
        },

        // 重置生态保护修复区评估参数
        resetProtectionParams() {
            this.protectionParams = {
                resultName: '',
                healthResult: null,
                trendResult: null,
                healthDisplayName: '',
                trendDisplayName: ''
            };
        },
        // 重置物理健康评估参数
        resetPhysicalParams() {
            this.physicalParams = {
                resultName: '',
                eoDataset: null,
                evDataset: null,
                erDataset: null,
                eoDisplayName: '',
                evDisplayName: '',
                erDisplayName: ''
            };
        },

        // 重置服务评估参数
        resetServiceParams() {
            this.serviceParams = {
                resultName: '',
                waterDataset: null,
                carbonDataset: null,
                soilDataset: null,
                waterDisplayName: '',
                carbonDisplayName: '',
                soilDisplayName: ''
            };
        },

        // 重置健康评估参数
        resetHealthParams() {
            this.healthParams = {
                resultName: '',
                physicalResult: null,
                serviceResult: null
            };
        },

        // 获取评估结果列表
        fetchResults() {
            // 获取物理健康评估结果
            axios.get(`/assessment/results/physical`)
                .then(response => {
                    console.log('获取物理健康评估结果', response.data);
                    this.physicalResults = response.data;
                })
                .catch(error => {
                    console.error('获取物理健康评估结果失败', error);
                });

            // 获取服务评估结果
            axios.get(`/assessment/results/service`)
                .then(response => {
                    this.serviceResults = response.data;
                })
                .catch(error => {
                    console.error('获取服务评估结果失败', error);
                });

            // 获取健康评估结果
            axios.get(`${this.apiBaseUrl}/api/assessment/results/health`)
                .then(response => {
                    this.healthResults = response.data;
                })
                .catch(error => {
                    console.error('获取健康评估结果失败', error);
                });
            // 获取生态保护修复区评估结果
            axios.get(`${this.apiBaseUrl}/api/assessment/results/protection`)
                .then(response => {
                    this.protectionResults = response.data;
                })
                .catch(error => {
                    console.error('获取生态保护修复区评估结果失败', error);
                });
        },

        // // 刷新物理健康评估结果
        // refreshPhysicalResults() {
        //     axios.get(`${this.apiBaseUrl}/api/assessment/results/physical`)
        //         .then(response => {
        //             this.physicalResults = response.data;
        //             this.$message.success('刷新成功');
        //         })
        //         .catch(error => {
        //             console.error('刷新失败', error);
        //             this.$message.error('刷新失败');
        //         });
        // },

        // // 刷新服务评估结果
        // refreshServiceResults() {
        //     axios.get(`${this.apiBaseUrl}/api/assessment/results/service`)
        //         .then(response => {
        //             this.serviceResults = response.data;
        //             this.$message.success('刷新成功');
        //         })
        //         .catch(error => {
        //             console.error('刷新失败', error);
        //             this.$message.error('刷新失败');
        //         });
        // },

        // // 刷新健康评估结果
        // refreshHealthResults() {
        //     axios.get(`${this.apiBaseUrl}/api/assessment/results/health`)
        //         .then(response => {
        //             this.healthResults = response.data;
        //             this.$message.success('刷新成功');
        //         })
        //         .catch(error => {
        //             console.error('刷新失败', error);
        //             this.$message.error('刷新失败');
        //         });
        // },

        // 在地图上查看结果
        viewResult(result) {
            if (!this.map) {
                this.$message.warning('地图尚未初始化');
                return;
            }

            console.log('查看评估结果@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@');
            // 在地图上显示评估结果
            if (result.type === "physical_timeseries" || result.type === "service_timeseries" || result.type === "health_timeseries") {

                if (result.files && Array.isArray(result.files)) {
                    result.files.forEach(file => {
                        this.$refs.mapView.addRasterLayer({
                            id: file.id,
                            name: file.name,
                            url: file.url,
                            visible: true
                        });
                    });
                }
            } else if (result.files && Array.isArray(result.files)) {
                // 单个时间点的结果
                const file = result.files[0];
                if (file) {
                    console.log('添加单时间点图层:', file);
                    this.$refs.mapView.addRasterLayer({
                        id: file.id,
                        name: file.name,
                        url: file.url,
                        visible: true
                    });
                }
            }

            // 设置当前查看的结果
            this.currentResult = result;

            // 滚动到对应的结果详情区域
            this.$nextTick(() => {
                const detailCard = document.querySelector('.assessment-result-cards');
                if (detailCard) {
                    detailCard.scrollIntoView({ behavior: 'smooth' });
                }
            });
        },

        // 下载结果
        downloadResult(result) {
            window.open(`${this.apiBaseUrl}/api/assessment/results/${result.id}/download`, '_blank');
        },

        // 获取评估类型标签样式
        getAssessmentTypeTag(type) {
            const typeMap = {
                'physical_timeseries': 'success',
                'service_timeseries': 'warning',
                'health_timeseries': 'danger'
            };
            return typeMap[type] || 'info';
        },

        // 获取评估类型名称
        getAssessmentTypeName(type) {
            const typeMap = {
                'physical_timeseries': '物理健康评估',
                'service_timeseries': '服务评估',
                'health_timeseries': '健康评估',
                'protection': '生态保护修复区评估'
            };
            return typeMap[type] || type;
        },

        // // 刷新所有结果
        // refreshResults() {
        //     Promise.all([
        //         this.refreshPhysicalResults(),
        //         this.refreshServiceResults(),
        //         this.refreshHealthResults()
        //     ]).then(() => {
        //         this.$message.success('刷新成功');
        //     }).catch(error => {
        //         console.error('刷新失败', error);
        //         this.$message.error('刷新失败');
        //     });
        // }
    }
}
</script>

<style scoped>
.integrated-assessment {
    height: 100%;
    width: 100%;
}

.main-container {
    height: 100%;
    position: relative;
    transition: all 0.3s;
}

.map-main {
    padding: 0;
    height: 100%;
}

.tools-aside {
    padding: 10px;
    height: 100%;
    transition: all 0.3s;
    background-color: var(--tool-bg);
    box-shadow: -2px 0 10px var(--shadow-color);
    overflow-y: auto;
    width: var(--collapse-width, 500px) !important;
}

.tools-container {
    display: flex;
    flex-direction: column;
    gap: 15px;
}



.tools-hidden .toggle-tools-panel {
    right: 0;
}

.assessment-card,
.results-card {
    margin-bottom: 15px;
}

.assessment-content {
    padding: 10px 0;
}

/* 适配数据集选择器高度 */
.dataset-selector-container {
    max-height: 200px;
    overflow-y: auto;
}

.results-card {
    margin-bottom: 15px;
}

.results-list {
    max-height: 300px;
    overflow-y: auto;
}

/* 评估结果详情样式 */
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

.assessment-chart {
    margin: 15px 0;
    /* text-align: center; */
}

.assessment-image {
    max-width: 100%;
    border-radius: 4px;
    box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
}

.assessment-statistics h4,
.assessment-explanation h4 {
    margin-top: 0;
    margin-bottom: 10px;
    font-size: 15px;
    font-weight: 500;
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
</style>