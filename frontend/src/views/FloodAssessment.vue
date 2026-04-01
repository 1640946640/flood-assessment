<template>
    <div class="flood-assessment">
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
                        <!-- 危险性模型H（淹没深度） -->
                        <el-tab-pane label="危险性模型H" name="hazard">
                            <el-card class="assessment-card">
                                <div slot="header">
                                    <span>危险性模型H（淹没深度）</span>
                                </div>
                                <div class="assessment-content">
                                    <p>计算公式：当H水-H地＞Δh0，H=[α*1+(1-α)*（H水-H地）/max（H水-H地）]；当H水-H地≤Δh0，H=0</p>
                                    <el-form :model="hazardParams" label-width="160px" size="small">
                                        <el-form-item label="淹没水位高程">
                                            <el-input-number v-model="hazardParams.waterLevel"
                                                placeholder="请输入淹没水位高程（米）" :precision="2" :step="0.1"
                                                style="width: 100%">
                                            </el-input-number>
                                        </el-form-item>
                                        <el-form-item label="阈值Δh0">
                                            <el-input-number v-model="hazardParams.deltaH0"
                                                placeholder="请输入阈值Δh0（米）" :precision="2" :step="0.1"
                                                style="width: 100%">
                                            </el-input-number>
                                        </el-form-item>
                                        <el-form-item label="基础值α">
                                            <el-input-number v-model="hazardParams.alpha"
                                                placeholder="请输入基础值α(0-1)" :precision="2" :step="0.1"
                                                :min="0" :max="1" style="width: 100%">
                                            </el-input-number>
                                        </el-form-item>
                                        <el-form-item label="DEM高程数据">
                                            <el-input v-model="hazardParams.demDisplayName" placeholder="请选择DEM数据集"
                                                readonly class="dataset-display"
                                                @click.native="showDatasetSelector('dem')">
                                            </el-input>
                                        </el-form-item>

                                        <!-- 添加斜面模型选项 -->
                                        <el-form-item>
                                            <el-checkbox v-model="hazardParams.useSlopeModel">使用斜面模型</el-checkbox>
                                        </el-form-item>

                                        <!-- 斜面模型参数 -->
                                        <template v-if="hazardParams.useSlopeModel">
                                            <el-divider content-position="left">斜面模型参数</el-divider>
                                            <el-form-item label="P0点坐标[经度,纬度]">
                                                <el-row :gutter="10">
                                                    <el-col :span="12">
                                                        <el-input-number v-model="hazardParams.p0Coord[0]" 
                                                            :precision="8" :step="0.0001" style="width: 100%">
                                                        </el-input-number>
                                                    </el-col>
                                                    <el-col :span="12">
                                                        <el-input-number v-model="hazardParams.p0Coord[1]" 
                                                            :precision="8" :step="0.0001" style="width: 100%">
                                                        </el-input-number>
                                                    </el-col>
                                                </el-row>
                                            </el-form-item>
                                            <el-form-item label="P0点水位">
                                                <el-input-number v-model="hazardParams.p0WaterLevel" 
                                                    :precision="2" :step="0.01" style="width: 100%">
                                                </el-input-number>
                                            </el-form-item>
                                            <el-form-item label="P1点坐标[经度,纬度]">
                                                <el-row :gutter="10">
                                                    <el-col :span="12">
                                                        <el-input-number v-model="hazardParams.p1Coord[0]" 
                                                            :precision="8" :step="0.0001" style="width: 100%">
                                                        </el-input-number>
                                                    </el-col>
                                                    <el-col :span="12">
                                                        <el-input-number v-model="hazardParams.p1Coord[1]" 
                                                            :precision="8" :step="0.0001" style="width: 100%">
                                                        </el-input-number>
                                                    </el-col>
                                                </el-row>
                                            </el-form-item>
                                            <el-form-item label="P1点水位">
                                                <div class="calculated-field">
                                                   <span>根据斜面模型自动计算（验证值：449.14米）</span>
                                                </div>
                                            </el-form-item>
                                            <el-form-item label="坡度PS">
                                                <el-input-number v-model="hazardParams.slopePS" 
                                                    :precision="6" :step="0.0001" style="width: 100%">
                                                </el-input-number>
                                                <span style="margin-left: 10px;">0.0003 = 0.03%</span>
                                            </el-form-item>
                                        </template>

                                        <el-form-item label="结果名称">
                                            <el-input v-model="hazardParams.resultName"
                                                placeholder="请输入结果名称"></el-input>
                                        </el-form-item>
                                        <el-form-item>
                                            <el-button type="primary" @click="runHazardAssessment"
                                                :loading="loading.hazard">开始计算</el-button>
                                            <el-button @click="resetHazardParams">重置</el-button>
                                        </el-form-item>
                                    </el-form>
                                </div>
                            </el-card>
                        </el-tab-pane>

                        <!-- 暴露性模型E（淹没范围） -->
                        <el-tab-pane label="暴露性模型E" name="exposure">
                            <el-card class="assessment-card">
                                <div slot="header">
                                    <span>暴露性模型E（淹没范围）</span>
                                </div>
                                <div class="assessment-content">
                                    <p>输入数据：淹没水位高程（H栅格）</p>
                                    <p>空间算法：E=1，当H＞0；E=0，当H≤0</p>
                                    <p>输出形式：淹没范围栅格（淡蓝色）</p>
                                    <el-form :model="exposureParams" label-width="160px" size="small">
                                        <el-form-item label="淹没水位高程">
                                            <el-input v-model="exposureParams.hazardDisplayName"
                                                placeholder="请选择淹没水位高程数据" readonly class="dataset-display"
                                                @click.native="showDatasetSelector('hazard')">
                                            </el-input>
                                        </el-form-item>

                                        <!-- 新增：河道扣除选项 -->
                                        <el-form-item>
                                            <el-checkbox v-model="exposureParams.excludeRiver">扣除河道面积</el-checkbox>
                                        </el-form-item>

                                        <!-- 河道数据集，仅在勾选扣除河道时显示 -->
                                        <template v-if="exposureParams.excludeRiver">
                                            <el-divider content-position="left">河道扣除参数</el-divider>
                                            <el-form-item label="河道水系数据">
                                                <el-input v-model="exposureParams.riverDisplayName"
                                                    placeholder="请选择河道水系数据" readonly class="dataset-display"
                                                    @click.native="showDatasetSelector('river')">
                                                </el-input>
                                            </el-form-item>

                                        </template>

                                        <el-form-item label="结果名称">
                                            <el-input v-model="exposureParams.resultName"
                                                placeholder="请输入结果名称"></el-input>
                                        </el-form-item>
                                        <el-form-item>
                                            <el-button type="primary" @click="runExposureAssessment"
                                                :loading="loading.exposure">开始计算</el-button>
                                            <el-button @click="resetExposureParams">重置</el-button>
                                        </el-form-item>
                                    </el-form>
                                </div>
                            </el-card>
                        </el-tab-pane>

                        <!-- 价值密度模型V -->
                        <el-tab-pane label="价值密度模型V" name="value">
                            <el-card class="assessment-card">
                                <div slot="header">
                                    <span>价值密度模型V（人口/资产/其他）</span>
                                </div>
                                <div class="assessment-content">
                                    <p class="formula-title" style="font-weight: bold;">价值密度模型计算公式：</p>
                                    <p>Vi = (Vpop,i·Jp + Vbuild,i·Jb + Vother,i·Jo)</p>
                                    
                                    <el-card class="formula-card" shadow="never" style="margin-bottom: 15px;">
                                        <div slot="header">
                                            <span style="font-weight: bold;">人口价值密度计算(Vpop,i)：</span>
                                        </div>
                                        <p style="font-weight: bold;">1. 双数据计算（人口热力图RLi和建筑面积Bi）</p>
                                        <p>当RLi>0且Bi>0：</p>
                                        <p>• Bi>0: Vpop,i = (Tpop·RLi·Bi)/(∑RLi·Bi)·f/Ai</p>
                                        <p>• Bi=0: Vpop,i = (Tpop·RLi)/(∑RLi)·f/Ai</p>
                                        <p>• 系数f为淹没区权重，f=r1·ym（淹没区）或f=r1·(1-ym)（非淹没区）</p>
                                        
                                        <p style="font-weight: bold;">2. 单数据计算</p>
                                        <p>• 仅人口热力图(∑Bi=0): Vpop,i = (Tpop·RLi)/(∑RLi)·f/Ai</p>
                                        <p>• 仅建筑面积(∑RLi=0): Vpop,i = (Tpop·Bi)/(∑Bi)·f/Ai</p>
                                        
                                        <p style="font-weight: bold;">3. 无数据区域</p>
                                        <p>• 双缺失无人区(RLi=0且Bi=0): Vpop,i = 0</p>
                                    </el-card>
                                    
                                    <p style="margin-bottom: 5px;">其中：</p>
                                    <p>• Tpop: 总人口数</p>
                                    <p>• ym: 淹没区人口占比(淹没区vs.非淹没区)</p>
                                    <p>• RLi: 第i个栅格的人口热力值</p>
                                    <p>• Bi: 第i个栅格的建筑面积</p>
                                    <p>• Ai: 第i个栅格的面积</p>
                                    <p>• r1,r2,r3: 权重系数(r1+r2+r3=1或r1+r2=1)</p>
                                    <p>• Jp,Jb,Jo: 经济标准值(元/人,元/m²,元)</p>
                                    <el-form :model="valueParams" label-width="160px" size="small">
                                        <!-- 基础数据输入 -->
                                        <el-divider content-position="left">基础数据</el-divider>
                                        <el-form-item label="总人口数">
                                            <el-input-number v-model="valueParams.totalPopulation" placeholder="请输入总人口数"
                                                :min="0" style="width: 100%">
                                            </el-input-number>
                                        </el-form-item>
                                        <el-form-item label="人口热力图">
                                            <el-input v-model="valueParams.populationDisplayName"
                                                placeholder="请选择人口热力图数据" readonly class="dataset-display"
                                                @click.native="showDatasetSelector('population')">
                                            </el-input>
                                        </el-form-item>

                                        <el-form-item label="建筑分布数据">
                                            <el-input v-model="valueParams.buildingDisplayName" placeholder="请选择建筑分布数据"
                                                readonly class="dataset-display"
                                                @click.native="showDatasetSelector('building')">
                                            </el-input>
                                        </el-form-item>
                                        <el-form-item label="其他分布数据（可选）">
                                            <el-input v-model="valueParams.otherDisplayName" placeholder="请选择其他分布数据（可选）"
                                                readonly class="dataset-display"
                                                @click.native="showDatasetSelector('other')">
                                            </el-input>
                                        </el-form-item>

                                        <!-- 权重系数设置 -->
                                        <el-divider content-position="left">权重系数</el-divider>
                                        <el-form-item label="人口热力图权重r1">
                                            <el-input-number v-model="valueParams.r1" :precision="2" :step="0.01"
                                                :min="0" :max="1" style="width: 100%">
                                            </el-input-number>
                                        </el-form-item>
                                        <el-form-item label="建筑分布权重r2">
                                            <el-input-number v-model="valueParams.r2" :precision="2" :step="0.01"
                                                :min="0" :max="1" style="width: 100%">
                                            </el-input-number>
                                        </el-form-item>
                                        <el-form-item label="其他分布权重r3" v-if="valueParams.otherDataset">
                                            <el-input-number v-model="valueParams.r3" :precision="2" :step="0.01"
                                                :min="0" :max="1" style="width: 100%">
                                            </el-input-number>
                                        </el-form-item>

                                        <!-- 淹没区设置 -->
                                        <el-divider content-position="left">淹没区设置</el-divider>
                                        <el-form-item label="是否考虑淹没区人口占比ym0">
                                          <el-switch v-model="valueParams.considerYm0" active-text="考虑" inactive-text="不考虑"></el-switch>
                                        </el-form-item>
                                        
                                        <!-- 只有在考虑ym0时才显示该字段 -->
                                        <el-form-item label="淹没区人口占比(ym0)" v-if="valueParams.considerYm0">
                                            <el-input-number v-model="valueParams.ym0" :precision="4" :step="0.01"
                                                :min="0" :max="1" style="width: 100%">
                                            </el-input-number>
                                            <div class="tips" style="margin-top: 5px; font-size: 12px; color: #909399;">
                                                历史淹没区人口占比，默认值：24.5/32 = 0.7656
                                            </div>
                                        </el-form-item>

                                        <!-- 经济标准设置 -->
                                        <el-divider content-position="left">经济标准J值</el-divider>
                                        <el-form-item label="人口经济标准J人">
                                            <el-input-number v-model="valueParams.jPop" :precision="2" :min="0"
                                                style="width: 100%" placeholder="元/人">
                                            </el-input-number>
                                        </el-form-item>
                                        <el-form-item label="建筑经济标准J建筑">
                                            <el-input-number v-model="valueParams.jBuilding" :precision="2" :min="0"
                                                style="width: 100%" placeholder="元/m²">
                                            </el-input-number>
                                        </el-form-item>
                                        <el-form-item label="其他经济标准J其他" v-if="valueParams.otherDataset">
                                            <el-input-number v-model="valueParams.jOther" :precision="2" :min="0"
                                                style="width: 100%" placeholder="元">
                                            </el-input-number>
                                        </el-form-item>

                                        <el-form-item>
                                            <el-alert v-if="!isWeightValid" 
                                                :title="valueParams.otherDataset ? '权重系数r1+r2+r3之和必须等于1' : '权重系数r1+r2之和必须等于1'" 
                                                type="warning" :closable="false" style="margin-bottom: 10px">
                                            </el-alert>
                                        </el-form-item>

                                        <!-- 公式说明区域 -->
                                        <div class="formula-explanation" style="margin-bottom: 10px;">
                                          <p v-if="valueParams.considerYm0">
                                            <strong>当前公式：</strong> Vi = (Vpop,i·Jp + Vbuild,i·Jb + Vother,i·Jo)，其中Vpop,i分区加权，含ym0（淹没区人口占比）
                                          </p>
                                          <p v-else>
                                            <strong>当前公式：</strong> Vi = (Vpop,i·Jp + Vbuild,i·Jb + Vother,i·Jo)，所有区域统一加权（不考虑ym0）
                                          </p>
                                        </div>

                                        <el-form-item label="结果名称">
                                            <el-input v-model="valueParams.resultName" placeholder="请输入结果名称"></el-input>
                                        </el-form-item>
                                        <el-form-item>
                                            <el-button type="primary" @click="runValueAssessment"
                                                :loading="loading.value" :disabled="!isWeightValid">开始计算</el-button>
                                            <el-button @click="resetValueParams">重置</el-button>
                                        </el-form-item>
                                    </el-form>
                                </div>
                            </el-card>
                        </el-tab-pane>

                        <!-- 敏感性模型S -->
                        <el-tab-pane label="敏感性模型S" name="sensitivity">
                            <el-card class="assessment-card">
                                <div slot="header">
                                    <span>敏感性模型S（环境敏感性）</span>
                                </div>
                                <div class="assessment-content">
                                    <p>输入数据：OSM路网数据（线矢量）；易涝点（点矢量）；其他（点/线/面矢量，可选）；栅格模板</p>
                                    <p>空间算法：S=max(S,0)，S=g1*(易涝点密度/最大易涝点密度)+g2*(路网密度/最大密度)+g3*(其他/最大其他）</p>
                                    <p>注意：S的实际取值范围被控制在[0.9-1]，如果其他要素没有录入，即取值1</p>
                                    <el-form :model="sensitivityParams" label-width="160px" size="small">
                                        <el-form-item label="栅格模板">
                                            <el-input v-model="sensitivityParams.rasterTemplateDisplayName"
                                                placeholder="请选择栅格模板数据" readonly class="dataset-display"
                                                @click.native="showDatasetSelector('rasterTemplate')">
                                            </el-input>
                                        </el-form-item>
                                        <el-form-item label="OSM路网数据">
                                            <el-input v-model="sensitivityParams.roadDisplayName"
                                                placeholder="请选择OSM路网数据" readonly class="dataset-display"
                                                @click.native="showDatasetSelector('road')">
                                            </el-input>
                                        </el-form-item>
                                        <el-form-item label="道路缓冲区半径(米)">
                                            <el-input-number v-model="sensitivityParams.roadBufferRadius"
                                                :precision="0" :step="50" :min="0" :max="1000"
                                                style="width: 100%"
                                                placeholder="设置道路影响范围，0表示不使用缓冲区">
                                            </el-input-number>
                                            <div style="font-size: 12px; color: #909399; margin-top: 5px;">
                                                推荐值：0-500米。设置为0时仅计算道路本身，大于0时计算道路周边影响区域
                                            </div>
                                        </el-form-item>
                                        <el-form-item label="易涝点数据">
                                            <el-input v-model="sensitivityParams.floodPointDisplayName"
                                                placeholder="请选择易涝点数据" readonly class="dataset-display"
                                                @click.native="showDatasetSelector('floodPoint')">
                                            </el-input>
                                        </el-form-item>
                                        <el-form-item label="其他数据（可选）">
                                            <el-input v-model="sensitivityParams.otherDisplayName"
                                                placeholder="请选择其他数据（可选）" readonly class="dataset-display"
                                                @click.native="showDatasetSelector('other')">
                                            </el-input>
                                        </el-form-item>

                                        <el-form-item label="权重系数g1（易涝点）">
                                            <el-input-number v-model="sensitivityParams.g1"
                                                :precision="2" :step="0.1" :min="0" :max="1"
                                                style="width: 100%">
                                            </el-input-number>
                                        </el-form-item>
                                        <el-form-item label="权重系数g2（路网）">
                                            <el-input-number v-model="sensitivityParams.g2"
                                                :precision="2" :step="0.1" :min="0" :max="1"
                                                style="width: 100%">
                                            </el-input-number>
                                        </el-form-item>
                                        <el-form-item label="权重系数g3（其他）">
                                            <el-input-number v-model="sensitivityParams.g3"
                                                :precision="2" :step="0.1" :min="0" :max="1"
                                                style="width: 100%">
                                            </el-input-number>
                                        </el-form-item>

                                        <el-form-item>
                                            <el-alert v-if="!isSensitivityWeightValid" 
                                                title="权重系数之和必须等于1" 
                                                type="warning" 
                                                :closable="false" 
                                                style="margin-bottom: 10px">
                                            </el-alert>
                                        </el-form-item>

                                        <el-form-item label="结果名称">
                                            <el-input v-model="sensitivityParams.resultName"
                                                placeholder="请输入结果名称">
                                            </el-input>
                                        </el-form-item>

                                        <el-form-item>
                                            <el-button type="primary" 
                                                @click="runSensitivityAssessment"
                                                :loading="loading.sensitivity"
                                                :disabled="!isSensitivityWeightValid">
                                                开始计算
                                            </el-button>
                                            <el-button @click="resetSensitivityParams">重置</el-button>
                                        </el-form-item>
                                    </el-form>
                                </div>
                            </el-card>
                        </el-tab-pane>

                        <!-- 工程防灾性模型R -->
                        <el-tab-pane label="工程防灾性模型R" name="resistance">
                            <el-card class="assessment-card">
                                <div slot="header">
                                    <span>工程防灾性模型R（工程防灾效果评估）</span>
                                </div>
                                <div class="assessment-content">
                                    <p><strong>计算公式：</strong>R=H，当（ΔH拓河+ΔH围堰）＞（H水-H地）；R=0，当（ΔH拓河+ΔH围堰）≤（H水-H地）</p>
                                    <p><strong>输出效果：</strong>防灾效果栅格，5级色带分级显示（红-橙-黄-蓝-绿），自然断点法分类</p>
                                    <p style="color: #E6A23C; font-size: 12px;"><i class="el-icon-info"></i> 
                                    模型评估河道拓宽清淤和围堰工程对防洪的综合效果，颜色越绿表示防灾效果越好</p>
                                    <el-form :model="resistanceParams" label-width="160px" size="small">
                                        <el-form-item>
                                            <el-checkbox v-model="resistanceParams.useSlopeModel">使用Hi模型的倾斜水面</el-checkbox>
                                            <div class="tips" style="margin-top: 5px; font-size: 12px; color: #909399;">
                                                <i class="el-icon-info"></i> 选择此选项后，将使用危险性模型的倾斜水面计算，无需手动输入淹没水位，计算更精确
                                            </div>
                                        </el-form-item>
                                        
                                        <el-form-item label="淹没水位高程" v-if="!resistanceParams.useSlopeModel">
                                            <el-input-number v-model="resistanceParams.waterLevel"
                                                placeholder="请输入淹没水位高程（米）" :precision="2" :step="0.1"
                                                style="width: 100%">
                                            </el-input-number>
                                        </el-form-item>
                                        <el-form-item label="河道拓宽清淤降低水位">
                                            <el-input-number v-model="resistanceParams.deltaHRiver"
                                                placeholder="请输入ΔH拓河（米）" :precision="2" :step="0.1"
                                                style="width: 100%">
                                            </el-input-number>
                                        </el-form-item>
                                        <el-form-item label="DEM高程数据">
                                            <el-input v-model="resistanceParams.demDisplayName" placeholder="请选择DEM数据集"
                                                readonly class="dataset-display"
                                                @click.native="showDatasetSelector('demResistance')">
                                            </el-input>
                                        </el-form-item>
                                        <el-form-item label="围堰范围数据">
                                            <el-input v-model="resistanceParams.damDisplayName" placeholder="请选择围堰范围数据"
                                                readonly class="dataset-display"
                                                @click.native="showDatasetSelector('dam')">
                                            </el-input>
                                        </el-form-item>
                                        <el-form-item label="危险性模型H">
                                            <el-input v-model="resistanceParams.hazardDisplayName" placeholder="请选择危险性模型H数据"
                                                readonly class="dataset-display"
                                                @click.native="showDatasetSelector('hazardResistance')">
                                            </el-input>
                                        </el-form-item>
                                        <el-form-item label="结果名称">
                                            <el-input v-model="resistanceParams.resultName"
                                                placeholder="请输入结果名称"></el-input>
                                        </el-form-item>
                                        <el-form-item>
                                            <el-button type="primary" @click="runResistanceAssessment"
                                                :loading="loading.resistance">开始计算</el-button>
                                            <el-button @click="resetResistanceParams">重置</el-button>
                                        </el-form-item>
                                    </el-form>
                                </div>
                            </el-card>
                        </el-tab-pane>

                        <!-- 工程减灾性模型M -->
                        <el-tab-pane label="工程减灾性模型M" name="mitigation">
                            <el-card class="assessment-card">
                                <div slot="header">
                                    <span>工程减灾性模型M（避难所覆盖）</span>
                                </div>
                                <div class="assessment-content">
                                    <p>计算公式：M=min[V，V容量价值密度]*η，d距离≤D，否则为零</p>
                                    <p>V容量价值密度=(Np*Jp+Nother*Jo)/(3.14*d*d)</p>
                                    <p>输出形式：减灾效果栅格（归一化，浅绿色）</p>
                                    <el-form :model="mitigationParams" label-width="160px" size="small">
                                        <el-form-item label="避难所POI数据">
                                            <el-input v-model="mitigationParams.shelterDisplayName" placeholder="请选择避难所POI数据集"
                                                readonly class="dataset-display"
                                                @click.native="showDatasetSelector('shelter')">
                                            </el-input>
                                        </el-form-item>
                                        <el-form-item label="人口经济价值J">
                                            <el-input-number v-model="mitigationParams.economicValue"
                                                placeholder="请输入人口经济价值（元/人）" :precision="0" :step="100"
                                                :min="0" style="width: 100%">
                                            </el-input-number>
                                        </el-form-item>
                                        <el-form-item label="物资经济价值Jo">
                                            <el-input-number v-model="mitigationParams.materialValue"
                                                placeholder="请输入物资经济价值（元/单位）" :precision="0" :step="100"
                                                :min="0" style="width: 100%">
                                            </el-input-number>
                                            <div style="font-size: 12px; color: #909399; margin-top: 5px;">
                                                可以设置为0，表示不考虑物资价值
                                            </div>
                                        </el-form-item>
                                        <el-form-item label="避难所覆盖范围D">
                                            <el-input-number v-model="mitigationParams.coverageRange"
                                                placeholder="请输入避难所覆盖范围（米）" :precision="0" :step="100"
                                                :min="0" style="width: 100%">
                                            </el-input-number>
                                        </el-form-item>
                                        <el-form-item label="减灾转移效率η">
                                            <el-input-number v-model="mitigationParams.efficiency"
                                                placeholder="请输入减灾转移效率(0-1)" :precision="2" :step="0.1"
                                                :min="0" :max="1" style="width: 100%">
                                            </el-input-number>
                                        </el-form-item>
                                        <el-form-item label="价值密度模型V">
                                            <el-input v-model="mitigationParams.valueDisplayName" placeholder="请选择价值密度模型V数据集"
                                                readonly class="dataset-display"
                                                @click.native="showDatasetSelector('valueMitigation')">
                                            </el-input>
                                        </el-form-item>
                                        <el-form-item label="是否归一化">
                                            <el-switch v-model="mitigationParams.normalize" active-text="是" inactive-text="否"></el-switch>
                                        </el-form-item>
                                        <el-form-item label="结果名称">
                                            <el-input v-model="mitigationParams.resultName" placeholder="请输入结果名称">
                                            </el-input>
                                        </el-form-item>
                                        <el-form-item>
                                            <el-button type="primary" @click="runMitigationAssessment"
                                                :loading="loading.mitigation">开始计算</el-button>
                                            <el-button @click="resetMitigationParams">重置</el-button>
                                        </el-form-item>
                                    </el-form>
                                </div>
                            </el-card>
                        </el-tab-pane>

                        <!-- 综合影响图（IDF和IPI） -->
                        <el-tab-pane label="综合影响图" name="comprehensive">
                            <el-card class="assessment-card">
                                <div slot="header">
                                    <span>综合影响图（IDF和IPI）</span>
                                </div>
                                <div class="assessment-content">
                                    <p>计算公式：</p>
                                    <p>I1 = w1*H × w2*E × w3*V × w4*S（灾害影响基值）</p>
                                    <p>I2 = w5*R × w2*E × w3*V × w4*S（工程防灾减量值）</p>
                                    <p>I3 = w1*H × w2*E × w6*M × w4*S（工程减灾减量值）</p>
                                    <p>IDFi = I1-I2-I3，IPIi = (I1-I2-I3)/I1</p>
                                    <p>IDF = ΣIDFi（小于0的值设为0后求和），IPI = ΣIPIi（小于0的值设为0后求和）</p>
                                    <p>输出形式：按自然断点法分5级风险色带（红→橙→黄→绿→灰）的栅格图像</p>
                                    <el-form :model="comprehensiveParams" label-width="160px" size="small">
                                        <!-- 模型结果选择 -->
                                        <el-divider content-position="left">模型结果选择</el-divider>
                                        <el-form-item label="危险性模型H">
                                            <el-input v-model="comprehensiveParams.hazardDisplayName"
                                                placeholder="请选择危险性模型H结果" readonly class="dataset-display"
                                                @click.native="showDatasetSelector('hazardComp')">
                                            </el-input>
                                        </el-form-item>
                                        <el-form-item label="暴露性模型E">
                                            <el-input v-model="comprehensiveParams.exposureDisplayName"
                                                placeholder="请选择暴露性模型E结果" readonly class="dataset-display"
                                                @click.native="showDatasetSelector('exposureComp')">
                                            </el-input>
                                        </el-form-item>
                                        <el-form-item label="价值密度模型V">
                                            <el-input v-model="comprehensiveParams.valueDisplayName"
                                                placeholder="请选择价值密度模型V结果" readonly class="dataset-display"
                                                @click.native="showDatasetSelector('valueComp')">
                                            </el-input>
                                        </el-form-item>
                                        <el-form-item label="敏感性模型S">
                                            <el-input v-model="comprehensiveParams.sensitivityDisplayName"
                                                placeholder="请选择敏感性模型S结果" readonly class="dataset-display"
                                                @click.native="showDatasetSelector('sensitivityComp')">
                                            </el-input>
                                        </el-form-item>
                                        <el-form-item label="工程防灾性模型R">
                                            <el-input v-model="comprehensiveParams.resistanceDisplayName"
                                                placeholder="请选择工程防灾性模型R结果" readonly class="dataset-display"
                                                @click.native="showDatasetSelector('resistanceComp')">
                                            </el-input>
                                        </el-form-item>
                                        <el-form-item label="工程减灾性模型M">
                                            <el-input v-model="comprehensiveParams.mitigationDisplayName"
                                                placeholder="请选择工程减灾性模型M结果" readonly class="dataset-display"
                                                @click.native="showDatasetSelector('mitigationComp')">
                                            </el-input>
                                        </el-form-item>

                                        <!-- 权重系数设置 -->
                                        <el-divider content-position="left">权重系数设置</el-divider>
                                        <el-form-item label="危险性权重w1">
                                            <el-input-number v-model="comprehensiveParams.w1" :precision="2" :step="0.1"
                                                :min="0" style="width: 100%">
                                            </el-input-number>
                                        </el-form-item>
                                        <el-form-item label="暴露性权重w2">
                                            <el-input-number v-model="comprehensiveParams.w2" :precision="2" :step="0.1"
                                                :min="0" style="width: 100%">
                                            </el-input-number>
                                        </el-form-item>
                                        <el-form-item label="价值密度权重w3">
                                            <el-input-number v-model="comprehensiveParams.w3" :precision="2" :step="0.1"
                                                :min="0" style="width: 100%">
                                            </el-input-number>
                                        </el-form-item>
                                        <el-form-item label="敏感性权重w4">
                                            <el-input-number v-model="comprehensiveParams.w4" :precision="2" :step="0.1"
                                                :min="0" style="width: 100%">
                                            </el-input-number>
                                        </el-form-item>
                                        <el-form-item label="工程防灾性权重w5">
                                            <el-input-number v-model="comprehensiveParams.w5" :precision="2" :step="0.1"
                                                :min="0" style="width: 100%">
                                            </el-input-number>
                                        </el-form-item>
                                        <el-form-item label="工程减灾性权重w6">
                                            <el-input-number v-model="comprehensiveParams.w6" :precision="2" :step="0.1"
                                                :min="0" style="width: 100%">
                                            </el-input-number>
                                        </el-form-item>

                                        <el-form-item label="结果名称">
                                            <el-input v-model="comprehensiveParams.resultName"
                                                placeholder="请输入结果名称"></el-input>
                                        </el-form-item>
                                        <el-form-item>
                                            <el-button type="primary" @click="runComprehensiveAssessment"
                                                :loading="loading.comprehensive">开始计算</el-button>
                                            <el-button @click="resetComprehensiveParams">重置</el-button>
                                        </el-form-item>
                                    </el-form>
                                </div>
                            </el-card>
                        </el-tab-pane>
                    </el-tabs>

                    <!-- 通用数据集选择器 -->
                    <el-dialog title="选择数据集" :visible.sync="datasetSelectorVisible" width="700px"
                        :before-close="handleDatasetSelectorClose" append-to-body>
                        <dataset-selector ref="currentSelector" :showCheckbox="true"
                            :selectionMode="currentSelectorMode" :allowedTypes="currentAllowedTypes"
                            @selected-datasets-change="handleDatasetSelection" />
                        <span slot="footer" class="dialog-footer">
                            <el-button @click="handleDatasetSelectorClose">取消</el-button>
                            <el-button type="primary" @click="confirmDatasetSelection">确定</el-button>
                        </span>
                    </el-dialog>

                    <!-- 统一的评估结果列表 -->
                    <el-card class="results-card">
                        <div slot="header">
                            <span>洪涝灾害评估结果</span>
                        </div>
                        <div class="results-list">
                            <el-table :data="hazardResults.concat(exposureResults).concat(valueResults).concat(sensitivityResults).concat(resistanceResults).concat(mitigationResults).concat(comprehensiveResults)"
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
                                    </template>
                                </el-table-column>
                            </el-table>
                        </div>
                    </el-card>

                    <!-- 评估结果详情卡片 -->
                    <assessment-result-cards v-if="currentResult" :result="currentResult" :apiBaseUrl="apiBaseUrl" />
                    <!-- 图片选择器 -->
                    <img-selector path="flood_results" title="洪涝灾害评估结果" />
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
    name: 'FloodAssessment',
    components: {
        MapView,
        ChartView,
        DatasetSelector,
        AssessmentResultCards,
        ImgSelector
    },
    mixins: [ToolsPanelMixin],
    data() {
        return {
            activeTab: 'hazard',
            map: null,
            showTools: true,
            datasetSelectorVisible: false,
            currentSelectorType: null,
            currentSelectorMode: 'single',
            currentAllowedTypes: [],
            datasetSelectorConfig: {
                dem: {
                    selectorMode: 'single',
                    allowedTypes: ['raster'],
                },
                hazard: {
                    selectorMode: 'single',
                    allowedTypes: ['raster'],
                },
                population: {
                    selectorMode: 'single',
                    allowedTypes: ['raster'],
                },

                building: {
                    selectorMode: 'single',
                    allowedTypes: ['raster'],
                },
                other: {
                    selectorMode: 'single',
                    allowedTypes: ['raster'],
                },
                rasterTemplate: {
                    selectorMode: 'single',
                    allowedTypes: ['raster'],
                },
                road: {
                    selectorMode: 'single',
                    allowedTypes: ['vector'],
                },
                floodPoint: {
                    selectorMode: 'single',
                    allowedTypes: ['vector'],
                },
                dam: {
                    selectorMode: 'single',
                    allowedTypes: ['vector'],
                },
                demResistance: {
                    selectorMode: 'single',
                    allowedTypes: ['raster'],
                },
                hazardResistance: {
                    selectorMode: 'single',
                    allowedTypes: ['raster'],
                },
                shelter: {
                    selectorMode: 'single',
                    allowedTypes: ['vector'],
                },
                valueMitigation: {
                    selectorMode: 'single',
                    allowedTypes: ['raster'],
                },
                hazardComp: {
                    selectorMode: 'single',
                    allowedTypes: ['raster'],
                },
                exposureComp: {
                    selectorMode: 'single',
                    allowedTypes: ['raster'],
                },
                valueComp: {
                    selectorMode: 'single',
                    allowedTypes: ['raster'],
                },
                sensitivityComp: {
                    selectorMode: 'single',
                    allowedTypes: ['raster'],
                },
                resistanceComp: {
                    selectorMode: 'single',
                    allowedTypes: ['raster'],
                },
                mitigationComp: {
                    selectorMode: 'single',
                    allowedTypes: ['raster'],
                },
                river: {
                    selectorMode: 'single',
                    allowedTypes: ['vector', 'raster'],
                }
            },
            loading: {
                hazard: false,
                exposure: false,
                value: false,
                sensitivity: false,
                resistance: false,
                mitigation: false,
                comprehensive: false
            },
            // 危险性模型参数
            hazardParams: {
                resultName: '',
                waterLevel: null,
                deltaH0: 0,
                alpha: 0.9,
                demDataset: null,
                demDisplayName: '',
                // 新增斜面模型参数
                useSlopeModel: false,
                p0Coord: [104.45777446, 30.80215121],
                p0WaterLevel: 446.55,
                p1Coord: [104.41572145, 30.86892721],
                slopePS: 0.0003
            },
            // 暴露性模型参数
            exposureParams: {
                resultName: '',
                hazardDataset: null,
                hazardDisplayName: '',
                // 新增河道扣除参数
                excludeRiver: false,
                riverDataset: null,
                riverDisplayName: ''
            },
            // 价值密度模型参数
            valueParams: {
                resultName: '',
                totalPopulation: null,
                populationDataset: null,
                buildingDataset: null,
                otherDataset: null,
                populationDisplayName: '',
                buildingDisplayName: '',
                otherDisplayName: '',
                // 权重系数
                r1: 0.5,
                r2: 0.5,
                r3: 0.0,
                // 经济标准
                jPop: 1000,
                jBuilding: 2000,
                jOther: 500,
                // 淹没区人口占比
                ym0: 0.7656,
                // 是否考虑淹没区人口占比
                considerYm0: false
            },
            sensitivityParams: {
                resultName: '',
                rasterTemplateDataset: null,
                roadDataset: null,
                floodPointDataset: null,
                otherDataset: null,
                rasterTemplateDisplayName: '',
                roadDisplayName: '',
                floodPointDisplayName: '',
                otherDisplayName: '',
                roadBufferRadius: 100, // 道路缓冲区半径(米)，默认100米
                g1: 0.05,
                g2: 0.05,
                g3: 0.9
            },
            // 工程防灾性模型参数
            resistanceParams: {
                resultName: '',
                waterLevel: null,
                deltaHRiver: 0,
                demDataset: null,
                damDataset: null,
                hazardDataset: null,
                demDisplayName: '',
                damDisplayName: '',
                hazardDisplayName: '',
                useSlopeModel: false // 新增：是否使用Hi模型的倾斜水面
            },
            // 工程减灾性模型参数
            mitigationParams: {
                resultName: '',
                shelterDataset: null,
                economicValue: 1000,
                materialValue: 2000,
                coverageRange: 1000,
                efficiency: 1.0,
                valueDataset: null,
                shelterDisplayName: '',
                valueDisplayName: '',
                normalize: false
            },
            // 综合影响图参数
            comprehensiveParams: {
                resultName: '',
                hazardDataset: null,
                exposureDataset: null,
                valueDataset: null,
                sensitivityDataset: null,
                resistanceDataset: null,
                mitigationDataset: null,
                hazardDisplayName: '',
                exposureDisplayName: '',
                valueDisplayName: '',
                sensitivityDisplayName: '',
                resistanceDisplayName: '',
                mitigationDisplayName: '',
                w1: 1.1,  // 危险性权重，默认1.1
                w2: 1.0,  // 暴露性权重，默认1.0
                w3: 1.0,  // 价值密度权重，默认1.0
                w4: 1.1,  // 敏感性权重，默认1.1
                w5: 1.0,  // 工程防灾性权重，默认1.0
                w6: 1.0   // 工程减灾性权重，默认1.0
            },
            hazardResults: [],
            exposureResults: [],
            valueResults: [],
            sensitivityResults: [],
            resistanceResults: [],
            mitigationResults: [],
            comprehensiveResults: [],
            apiBaseUrl: process.env.VUE_APP_API_URL || 'http://localhost:5000',
            currentResult: null,
            tempSelectedDatasets: null
        }
    },
    computed: {
        ...mapState(['datasets']),
        // 检查权重系数是否有效
        isWeightValid() {
            // 如果有其他数据集，检查r1+r2+r3=1
            if (this.valueParams.otherDataset) {
                const sum = this.valueParams.r1 + this.valueParams.r2 + this.valueParams.r3;
                return Math.abs(sum - 1) < 0.001;
            } else {
                // 如果没有其他数据集，检查r1+r2=1
                const sum = this.valueParams.r1 + this.valueParams.r2;
                return Math.abs(sum - 1) < 0.001;
            }
        },
        isSensitivityWeightValid() {
            const { g1, g2, g3 } = this.sensitivityParams;
            return Math.abs(g1 + g2 + g3 - 1) < 0.001;
        }
    },
    mounted() {
        document.documentElement.style.setProperty('--collapse-width', '600px');
        this.fetchDatasets();
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
            console.error('图层添加失败:', error);
            this.$message.error('图层添加失败: ' + error.message);
        },

        // 图层已存在
        handleLayerExists(layerId) {
            console.warn('图层已存在:', layerId);
            this.$message.warning(`图层 ${layerId} 已存在`);
        },

        // 显示数据集选择器
        showDatasetSelector(type) {
            this.currentSelectorType = type;
            
            // 设置选择器模式和允许的数据类型
            const config = this.datasetSelectorConfig[type];
            if (config) {
                this.currentSelectorMode = config.selectorMode;
                this.currentAllowedTypes = config.allowedTypes;
            }
            
            // 根据不同类型设置已选数据集
            switch (type) {
                case 'dem':
                    this.tempSelectedDatasets = this.hazardParams.demDataset ? 
                        this.datasets.filter(d => this.hazardParams.demDataset.includes(d.id)) : [];
                    break;
                case 'hazard':
                    this.tempSelectedDatasets = this.exposureParams.hazardDataset ? 
                        this.datasets.filter(d => this.exposureParams.hazardDataset.includes(d.id)) : [];
                    break;
                case 'population':
                    this.tempSelectedDatasets = this.valueParams.populationDataset ? 
                        this.datasets.filter(d => this.valueParams.populationDataset.includes(d.id)) : [];
                    break;
                case 'light':
                    this.tempSelectedDatasets = this.valueParams.lightDataset ? 
                        this.datasets.filter(d => this.valueParams.lightDataset.includes(d.id)) : [];
                    break;
                case 'building':
                    this.tempSelectedDatasets = this.valueParams.buildingDataset ? 
                        this.datasets.filter(d => this.valueParams.buildingDataset.includes(d.id)) : [];
                    break;
                case 'other':
                    this.tempSelectedDatasets = this.valueParams.otherDataset ? 
                        this.datasets.filter(d => this.valueParams.otherDataset.includes(d.id)) : [];
                    break;
                case 'rasterTemplate':
                    this.tempSelectedDatasets = this.sensitivityParams.rasterTemplateDataset ? 
                        this.datasets.filter(d => this.sensitivityParams.rasterTemplateDataset.includes(d.id)) : [];
                    break;
                case 'road':
                    this.tempSelectedDatasets = this.sensitivityParams.roadDataset ? 
                        this.datasets.filter(d => this.sensitivityParams.roadDataset.includes(d.id)) : [];
                    break;
                case 'floodPoint':
                    this.tempSelectedDatasets = this.sensitivityParams.floodPointDataset ? 
                        this.datasets.filter(d => this.sensitivityParams.floodPointDataset.includes(d.id)) : [];
                    break;
                case 'demResistance':
                    this.tempSelectedDatasets = this.resistanceParams.demDataset ? 
                        this.datasets.filter(d => this.resistanceParams.demDataset.includes(d.id)) : [];
                    break;
                case 'dam':
                    this.tempSelectedDatasets = this.resistanceParams.damDataset ? 
                        this.datasets.filter(d => this.resistanceParams.damDataset.includes(d.id)) : [];
                    break;
                case 'hazardResistance':
                    this.tempSelectedDatasets = this.resistanceParams.hazardDataset ? 
                        this.datasets.filter(d => this.resistanceParams.hazardDataset.includes(d.id)) : [];
                    break;
                case 'shelter':
                    this.tempSelectedDatasets = this.mitigationParams.shelterDataset ? 
                        this.datasets.filter(d => this.mitigationParams.shelterDataset.includes(d.id)) : [];
                    break;
                case 'valueMitigation':
                    this.tempSelectedDatasets = this.mitigationParams.valueDataset ? 
                        this.datasets.filter(d => this.mitigationParams.valueDataset.includes(d.id)) : [];
                    break;
                case 'hazardComp':
                    this.tempSelectedDatasets = this.comprehensiveParams.hazardDataset ? 
                        this.datasets.filter(d => this.comprehensiveParams.hazardDataset.includes(d.id)) : [];
                    break;
                case 'exposureComp':
                    this.tempSelectedDatasets = this.comprehensiveParams.exposureDataset ? 
                        this.datasets.filter(d => this.comprehensiveParams.exposureDataset.includes(d.id)) : [];
                    break;
                case 'valueComp':
                    this.tempSelectedDatasets = this.comprehensiveParams.valueDataset ? 
                        this.datasets.filter(d => this.comprehensiveParams.valueDataset.includes(d.id)) : [];
                    break;
                case 'sensitivityComp':
                    this.tempSelectedDatasets = this.comprehensiveParams.sensitivityDataset ? 
                        this.datasets.filter(d => this.comprehensiveParams.sensitivityDataset.includes(d.id)) : [];
                    break;
                case 'resistanceComp':
                    this.tempSelectedDatasets = this.comprehensiveParams.resistanceDataset ? 
                        this.datasets.filter(d => this.comprehensiveParams.resistanceDataset.includes(d.id)) : [];
                    break;
                case 'mitigationComp':
                    this.tempSelectedDatasets = this.comprehensiveParams.mitigationDataset ? 
                        this.datasets.filter(d => this.comprehensiveParams.mitigationDataset.includes(d.id)) : [];
                    break;
                case 'river':
                    this.tempSelectedDatasets = this.exposureParams.riverDataset ? 
                        this.datasets.filter(d => this.exposureParams.riverDataset.includes(d.id)) : [];
                    break;
            }
            
            this.datasetSelectorVisible = true;
        },

        // 处理数据集选择器关闭
        handleDatasetSelectorClose() {
            this.datasetSelectorVisible = false;
            this.currentSelectorType = null;
        },

        // 处理数据集选择
        handleDatasetSelection(datasets) {
            // 这里可以处理选择的数据集
            // 临时保存选择的数据集，等确认后再应用
            this.tempSelectedDatasets = datasets;
        },

        // 确认数据集选择
        confirmDatasetSelection() {
            const selectedDatasets = this.tempSelectedDatasets;
            if (selectedDatasets.length === 0) {
                this.$message.warning('请选择数据集');
                return;
            }

            const dataset = selectedDatasets.map(d => d.id);
            const type = this.currentSelectorType;
            const datasetCount = selectedDatasets.length;
            const displayName = datasetCount > 1 ?
                `已选择 ${datasetCount} 个数据集: ${selectedDatasets[0].name}等` :
                selectedDatasets[0].name;

            switch (type) {
                case 'dem':
                    this.hazardParams.demDataset = dataset;
                    this.hazardParams.demDisplayName = displayName;
                    break;
                case 'hazard':
                    this.exposureParams.hazardDataset = dataset;
                    this.exposureParams.hazardDisplayName = displayName;
                    break;
                case 'population':
                    this.valueParams.populationDataset = dataset;
                    this.valueParams.populationDisplayName = displayName;
                    break;

                case 'building':
                    this.valueParams.buildingDataset = dataset;
                    this.valueParams.buildingDisplayName = displayName;
                    break;
                case 'other':
                    this.valueParams.otherDataset = dataset;
                    this.valueParams.otherDisplayName = displayName;
                    break;
                case 'rasterTemplate':
                    this.sensitivityParams.rasterTemplateDataset = dataset;
                    this.sensitivityParams.rasterTemplateDisplayName = displayName;
                    break;
                case 'road':
                    this.sensitivityParams.roadDataset = dataset;
                    this.sensitivityParams.roadDisplayName = displayName;
                    break;
                case 'floodPoint':
                    this.sensitivityParams.floodPointDataset = dataset;
                    this.sensitivityParams.floodPointDisplayName = displayName;
                    break;
                case 'demResistance':
                    this.resistanceParams.demDataset = dataset;
                    this.resistanceParams.demDisplayName = displayName;
                    break;
                case 'dam':
                    this.resistanceParams.damDataset = dataset;
                    this.resistanceParams.damDisplayName = displayName;
                    break;
                case 'hazardResistance':
                    this.resistanceParams.hazardDataset = dataset;
                    this.resistanceParams.hazardDisplayName = displayName;
                    break;
                case 'shelter':
                    this.mitigationParams.shelterDataset = dataset;
                    this.mitigationParams.shelterDisplayName = displayName;
                    break;
                case 'valueMitigation':
                    this.mitigationParams.valueDataset = dataset;
                    this.mitigationParams.valueDisplayName = displayName;
                    break;
                case 'hazardComp':
                    this.comprehensiveParams.hazardDataset = dataset;
                    this.comprehensiveParams.hazardDisplayName = displayName;
                    break;
                case 'exposureComp':
                    this.comprehensiveParams.exposureDataset = dataset;
                    this.comprehensiveParams.exposureDisplayName = displayName;
                    break;
                case 'valueComp':
                    this.comprehensiveParams.valueDataset = dataset;
                    this.comprehensiveParams.valueDisplayName = displayName;
                    break;
                case 'sensitivityComp':
                    this.comprehensiveParams.sensitivityDataset = dataset;
                    this.comprehensiveParams.sensitivityDisplayName = displayName;
                    break;
                case 'resistanceComp':
                    this.comprehensiveParams.resistanceDataset = dataset;
                    this.comprehensiveParams.resistanceDisplayName = displayName;
                    break;
                case 'mitigationComp':
                    this.comprehensiveParams.mitigationDataset = dataset;
                    this.comprehensiveParams.mitigationDisplayName = displayName;
                    break;
                case 'river':
                    this.exposureParams.riverDataset = dataset;
                    this.exposureParams.riverDisplayName = displayName;
                    break;
            }

            this.handleDatasetSelectorClose();
        },

        // 运行危险性评估
        async runHazardAssessment() {
            // 验证必填参数
            if (!this.hazardParams.resultName || !this.hazardParams.demDataset) {
                this.$message.error('请填写结果名称和选择DEM数据集');
                return;
            }
            
            // 如果不使用斜面模型，则需要水位参数
            if (!this.hazardParams.useSlopeModel && !this.hazardParams.waterLevel) {
                this.$message.error('请填写淹没水位或启用倾斜水面模型');
                return;
            }
            
            // 如果使用斜面模型，验证相关参数
            if (this.hazardParams.useSlopeModel) {
                if (!this.hazardParams.p0WaterLevel || !this.hazardParams.p0Coord || !this.hazardParams.p1Coord) {
                    this.$message.error('请填写完整的倾斜水面模型参数');
                    return;
                }
            }

            this.loading.hazard = true;
            try {
                const params = {
                    water_level: this.hazardParams.waterLevel,
                    delta_h0: this.hazardParams.deltaH0,
                    alpha: this.hazardParams.alpha,
                    dem_dataset_id: this.hazardParams.demDataset,
                    result_name: this.hazardParams.resultName
                };
                
                // 添加斜面模型参数（如果启用）
                if (this.hazardParams.useSlopeModel) {
                    params.use_slope_model = true;
                    params.p0_coord = this.hazardParams.p0Coord;
                    params.p0_water_level = this.hazardParams.p0WaterLevel;
                    params.p1_coord = this.hazardParams.p1Coord;
                    // P1点水位通过斜面模型自动计算，不再提交
                    params.slope_ps = this.hazardParams.slopePS;
                }

                const response = await axios.post(`${this.apiBaseUrl}/api/flood/hazard`, params);

                this.hazardResults.push(response.data);
                this.viewResult(response.data);
                this.$message.success('危险性评估完成');
                this.resetHazardParams();
            } catch (error) {
                console.error('危险性评估失败:', error);
                this.$message.error('危险性评估失败: ' + (error.response?.data?.message || error.message));
            } finally {
                this.loading.hazard = false;
            }
        },

        // 运行暴露性评估
        async runExposureAssessment() {
            if (!this.exposureParams.hazardDataset || !this.exposureParams.resultName) {
                this.$message.error('请填写完整的参数');
                return;
            }

            // 检查河道数据集是否已选择
            if (this.exposureParams.excludeRiver && !this.exposureParams.riverDataset) {
                this.$message.error('请选择河道水系数据');
                return;
            }

            this.loading.exposure = true;
            try {
                const params = {
                    hazard_dataset_id: this.exposureParams.hazardDataset,
                    result_name: this.exposureParams.resultName
                };

                // 添加河道扣除相关参数
                if (this.exposureParams.excludeRiver) {
                    params.exclude_river = true;
                    params.river_dataset_id = this.exposureParams.riverDataset;
                }

                const response = await axios.post(`${this.apiBaseUrl}/api/flood/exposure`, params);

                this.exposureResults.push(response.data);
                this.viewResult(response.data);
                this.$message.success('暴露性评估完成');
                this.resetExposureParams();
            } catch (error) {
                console.error('暴露性评估失败:', error);
                this.$message.error('暴露性评估失败: ' + (error.response?.data?.message || error.message));
            } finally {
                this.loading.exposure = false;
            }
        },

        // 运行价值密度评估
        async runValueAssessment() {
            if (!this.valueParams.totalPopulation || !this.valueParams.populationDataset ||
                !this.valueParams.buildingDataset || !this.valueParams.resultName) {
                this.$message.error('请填写完整的参数');
                return;
            }

            if (!this.isWeightValid) {
                this.$message.error('权重系数之和必须等于1');
                return;
            }

            this.loading.value = true;
            try {
                const requestData = {
                    total_population: this.valueParams.totalPopulation,
                    population_dataset_id: this.valueParams.populationDataset,
                    building_dataset_id: this.valueParams.buildingDataset,
                    r1: this.valueParams.r1,
                    r2: this.valueParams.r2,
                    j_pop: this.valueParams.jPop,
                    j_building: this.valueParams.jBuilding,
                    result_name: this.valueParams.resultName,
                    ym0: this.valueParams.ym0,
                    consider_ym0: this.valueParams.considerYm0 // 新增
                };
                
                // 如果有其他数据集，添加相关参数
                if (this.valueParams.otherDataset) {
                    requestData.other_dataset_id = this.valueParams.otherDataset;
                    requestData.r3 = this.valueParams.r3;
                    requestData.j_other = this.valueParams.jOther;
                }
                
                const response = await axios.post(`${this.apiBaseUrl}/api/flood/value`, requestData);

                this.valueResults.push(response.data);
                this.viewResult(response.data);
                this.$message.success('价值密度评估完成');
                this.resetValueParams();
            } catch (error) {
                console.error('价值密度评估失败:', error);
                this.$message.error('价值密度评估失败: ' + (error.response?.data?.message || error.message));
            } finally {
                this.loading.value = false;
            }
        },

        // 运行敏感性评估
        async runSensitivityAssessment() {
            if (!this.sensitivityParams.rasterTemplateDataset || 
                !this.sensitivityParams.roadDataset || 
                !this.sensitivityParams.floodPointDataset || 
                !this.sensitivityParams.resultName) {
                this.$message.error('请填写完整的参数');
                return;
            }

            if (!this.isSensitivityWeightValid) {
                this.$message.error('权重系数之和必须等于1');
                return;
            }

            this.loading.sensitivity = true;
            try {
                const response = await axios.post(`${this.apiBaseUrl}/api/flood/sensitivity`, {
                    rasterTemplateDataset: this.sensitivityParams.rasterTemplateDataset,
                    roadDataset: this.sensitivityParams.roadDataset,
                    floodPointDataset: this.sensitivityParams.floodPointDataset,
                    otherDataset: this.sensitivityParams.otherDataset,
                    roadBufferRadius: this.sensitivityParams.roadBufferRadius,
                    g1: this.sensitivityParams.g1,
                    g2: this.sensitivityParams.g2,
                    g3: this.sensitivityParams.g3,
                    resultName: this.sensitivityParams.resultName
                });

                this.sensitivityResults.push(response.data);
                this.viewResult(response.data);
                this.$message.success('敏感性评估完成');
                this.resetSensitivityParams();
            } catch (error) {
                console.error('敏感性评估失败:', error);
                this.$message.error('敏感性评估失败: ' + (error.response?.data?.message || error.message));
            } finally {
                this.loading.sensitivity = false;
            }
        },

        // 重置参数
        resetHazardParams() {
            this.hazardParams = {
                resultName: '',
                waterLevel: null,
                deltaH0: 0,
                alpha: 0.9,
                demDataset: null,
                demDisplayName: '',
                // 重置斜面模型参数
                useSlopeModel: false,
                p0Coord: [104.45777446, 30.80215121],
                p0WaterLevel: 446.55,
                p1Coord: [104.41572145, 30.86892721],
                slopePS: 0.0003
            };
        },

        resetExposureParams() {
            this.exposureParams = {
                resultName: '',
                hazardDataset: null,
                hazardDisplayName: '',
                excludeRiver: false,
                riverDataset: null,
                riverDisplayName: ''
            };
        },

        resetValueParams() {
            this.valueParams = {
                resultName: '',
                totalPopulation: null,
                populationDataset: null,
                buildingDataset: null,
                otherDataset: null,
                populationDisplayName: '',
                buildingDisplayName: '',
                otherDisplayName: '',
                // 权重系数
                r1: 0.5,
                r2: 0.5,
                r3: 0.0,
                // 经济标准
                jPop: 1000,
                jBuilding: 2000,
                jOther: 500,
                // 淹没区人口占比
                ym0: 0.7656
            };
        },

        resetSensitivityParams() {
            this.sensitivityParams = {
                resultName: '',
                rasterTemplateDataset: null,
                roadDataset: null,
                floodPointDataset: null,
                otherDataset: null,
                rasterTemplateDisplayName: '',
                roadDisplayName: '',
                floodPointDisplayName: '',
                otherDisplayName: '',
                roadBufferRadius: 100, // 道路缓冲区半径(米)，默认100米
                g1: 0.4,
                g2: 0.4,
                g3: 0.2
            };
        },

        resetResistanceParams() {
            this.resistanceParams = {
                resultName: '',
                waterLevel: null,
                deltaHRiver: 0,
                demDataset: null,
                damDataset: null,
                hazardDataset: null,
                demDisplayName: '',
                damDisplayName: '',
                hazardDisplayName: '',
                useSlopeModel: false
            };
        },

        resetMitigationParams() {
            this.mitigationParams = {
                shelterDataset: null,
                economicValue: 1000,
                materialValue: 2000,
                coverageRange: 1000,
                efficiency: 1.0,
                valueDataset: null,
                resultName: '工程减灾性M评估结果',
                shelterDisplayName: '',
                valueDisplayName: '',
                normalize: false
            };
        },

        resetComprehensiveParams() {
            this.comprehensiveParams = {
                resultName: '',
                hazardDataset: null,
                exposureDataset: null,
                valueDataset: null,
                sensitivityDataset: null,
                resistanceDataset: null,
                mitigationDataset: null,
                hazardDisplayName: '',
                exposureDisplayName: '',
                valueDisplayName: '',
                sensitivityDisplayName: '',
                resistanceDisplayName: '',
                mitigationDisplayName: '',
                w1: 1.1,  // 危险性权重，默认1.1
                w2: 1.0,  // 暴露性权重，默认1.0
                w3: 1.0,  // 价值密度权重，默认1.0
                w4: 1.1,  // 敏感性权重，默认1.1
                w5: 1.0,  // 工程防灾性权重，默认1.0
                w6: 1.0   // 工程减灾性权重，默认1.0
            };
        },

        // 运行工程防灾性评估
        async runResistanceAssessment() {
            // 参数验证
            if ((!this.resistanceParams.waterLevel && !this.resistanceParams.useSlopeModel) || 
                !this.resistanceParams.demDataset || 
                !this.resistanceParams.damDataset || 
                !this.resistanceParams.hazardDataset || 
                !this.resistanceParams.resultName) {
                this.$message.error('请填写完整的参数');
                return;
            }

            this.loading.resistance = true;
            try {
                const params = {
                    delta_h_river: this.resistanceParams.deltaHRiver,
                    dem_dataset_id: this.resistanceParams.demDataset,
                    dam_dataset_id: this.resistanceParams.damDataset,
                    hazard_dataset_id: this.resistanceParams.hazardDataset,
                    result_name: this.resistanceParams.resultName,
                    use_slope_model: this.resistanceParams.useSlopeModel
                };
                
                // 仅在不使用斜面模型时提供水位高程
                if (!this.resistanceParams.useSlopeModel) {
                    params.water_level = this.resistanceParams.waterLevel;
                }

                const response = await axios.post(`${this.apiBaseUrl}/api/flood/resistance`, params);

                this.resistanceResults.push(response.data);
                this.viewResult(response.data);
                this.$message.success('工程防灾性评估完成');
                this.resetResistanceParams();
            } catch (error) {
                console.error('工程防灾性评估失败:', error);
                this.$message.error('工程防灾性评估失败: ' + (error.response?.data?.message || error.message));
            } finally {
                this.loading.resistance = false;
            }
        },

        // 运行工程减灾性评估
        async runMitigationAssessment() {
            if (!this.mitigationParams.shelterDataset || 
                this.mitigationParams.economicValue === null || this.mitigationParams.economicValue === undefined ||
                this.mitigationParams.materialValue === null || this.mitigationParams.materialValue === undefined ||
                this.mitigationParams.coverageRange === null || this.mitigationParams.coverageRange === undefined ||
                this.mitigationParams.efficiency === null || this.mitigationParams.efficiency === undefined ||
                !this.mitigationParams.valueDataset || 
                !this.mitigationParams.resultName) {
                this.$message.error('请填写所有必要参数');
                return;
            }

            this.loading.mitigation = true;
            try {
                const response = await axios.post(`${this.apiBaseUrl}/api/flood/mitigation`, {
                    shelter_dataset_id: this.mitigationParams.shelterDataset,
                    economic_value: this.mitigationParams.economicValue,
                    material_value: this.mitigationParams.materialValue,
                    coverage_range: this.mitigationParams.coverageRange,
                    efficiency: this.mitigationParams.efficiency,
                    value_dataset_id: this.mitigationParams.valueDataset,
                    result_name: this.mitigationParams.resultName,
                    normalize: this.mitigationParams.normalize
                });

                this.mitigationResults.push(response.data);
                this.$message.success('工程减灾性评估完成');
                this.resetMitigationParams();
                this.activeTab = 'results';
            } catch (error) {
                this.$message.error(`工程减灾性评估失败: ${error.response?.data?.error || error.message}`);
            } finally {
                this.loading.mitigation = false;
            }
        },

        // 运行综合影响图评估
        async runComprehensiveAssessment() {
            // 检查必填参数
            if (!this.comprehensiveParams.hazardDataset || 
                !this.comprehensiveParams.exposureDataset || 
                !this.comprehensiveParams.valueDataset || 
                !this.comprehensiveParams.sensitivityDataset || 
                !this.comprehensiveParams.resistanceDataset || 
                !this.comprehensiveParams.mitigationDataset || 
                !this.comprehensiveParams.resultName) {
                this.$message.error('请选择所有模型结果数据集');
                return;
            }

            this.loading.comprehensive = true;
            try {
                const response = await axios.post(`${this.apiBaseUrl}/api/flood/comprehensive`, {
                    hazard_dataset_id: this.comprehensiveParams.hazardDataset,
                    exposure_dataset_id: this.comprehensiveParams.exposureDataset,
                    value_dataset_id: this.comprehensiveParams.valueDataset,
                    sensitivity_dataset_id: this.comprehensiveParams.sensitivityDataset,
                    resistance_dataset_id: this.comprehensiveParams.resistanceDataset,
                    mitigation_dataset_id: this.comprehensiveParams.mitigationDataset,
                    w1: this.comprehensiveParams.w1,
                    w2: this.comprehensiveParams.w2,
                    w3: this.comprehensiveParams.w3,
                    w4: this.comprehensiveParams.w4,
                    w5: this.comprehensiveParams.w5,
                    w6: this.comprehensiveParams.w6,
                    result_name: this.comprehensiveParams.resultName
                });

                this.comprehensiveResults.push(response.data);
                this.viewResult(response.data);
                this.$message.success('综合影响图评估完成');
                this.resetComprehensiveParams();
            } catch (error) {
                console.error('综合影响图评估失败:', error);
                this.$message.error('综合影响图评估失败: ' + (error.response?.data?.message || error.message));
            } finally {
                this.loading.comprehensive = false;
            }
        },

        // 查看结果
        viewResult(result) {
            this.currentResult = result;
            result.files.forEach(file => {
                if (this.$refs.mapView) {
                    this.$refs.mapView.addLayer({
                        id: file.id,
                        name: file.name,
                        url: file.url,
                        type: file.type
                    });
                }
            });
        },

        // 获取评估类型标签
        getAssessmentTypeTag(type) {
            const tagMap = {
                'hazard': 'danger',
                'exposure': 'warning',
                'value': 'success'
            };
            return tagMap[type] || 'info';
        },

        // 获取评估类型名称
        getAssessmentTypeName(type) {
            const nameMap = {
                'hazard': '危险性',
                'exposure': '暴露性',
                'value': '价值密度',
                'sensitivity': '敏感性',
                'resistance': '工程防灾性',
                'mitigation': '工程减灾性',
                'comprehensive': '综合影响图'
            };
            return nameMap[type] || type;
        },

    }
}
</script>

<style scoped>
.flood-assessment {
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

:deep(.el-tabs--border-card>.el-tabs__content) {
    padding: 0;
}

/* 计算字段样式 */
.calculated-field {
    padding: 8px 12px;
    background-color: #f0f9ff;
    border: 1px solid #b3d8ff;
    border-radius: 4px;
    color: #409eff;
    font-size: 13px;
    font-style: italic;
}

.calculated-field::before {
    content: "🧮 ";
    margin-right: 4px;
}
</style>