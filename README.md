# 洪涝灾害影响评估平台 (Flood Assessment Platform)

![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg) ![Vue.js](https://img.shields.io/badge/Vue.js-2.6-4FC08D.svg) ![Flask](https://img.shields.io/badge/Flask-2.x-000000.svg) ![GIS](https://img.shields.io/badge/GIS-Spatial_Analysis-orange.svg) ![License](https://img.shields.io/badge/License-Commercial_Use_Restricted-red.svg)

> **Tags / Keywords**: `GIS`, `Flood Assessment`, `WebGIS`, `Vue2`, `Flask`, `Spatial Analysis`, `Hazard Model`, `Raster Processing`, `Emergency Response`, `Urban Planning`

## 项目简介 (Project Overview)
本项目是一个功能强大且专业的洪涝灾害影响评估与数据可视化分析平台，专为城市规划、应急管理及水文研究等领域设计。通过深度结合地理信息系统（GIS）数据（如 DEM 高程数据、矢量建筑、易涝点、人口热力图等），平台能够进行精准的洪涝风险评估、水文模型分析、危险性与暴露性评估。

平台分为前端和后端两部分，前后端分离架构保证了系统的高性能与可扩展性：
- **后端**：基于 Python/Flask 开发，集成了强大的地理空间计算库（如 `GDAL`, `Rasterio`, `GeoPandas` 等），提供栅格/矢量数据处理、空间分析、行列对齐、相关性分析等核心计算能力。
- **前端**：基于 Vue.js 开发，结合 `OpenLayers`, `Mapbox GL` 与 `ECharts`，提供直观的地图交互、图层管理、多维度数据可视化及评估结果展示。

## 核心功能 (Key Features)
1. **多源数据管理与可视化**：
   - 支持动态加载和渲染高分辨率的 TIFF 栅格数据及 SHP 矢量数据。
   - 内置强大的图层管理器，支持图层的透明度调节、叠加及底图切换。
2. **洪涝灾害模型计算**：
   - **淹没深度计算**：基于给定的水位线与地形 DEM 数据，精确计算洪涝淹没范围与深度。
   - **危险性评估 (Hazard Model)**：结合淹没深度、流速等参数，进行灾害危险性等级划分。
3. **暴露性与影响综合评估**：
   - 基于建筑物（如建筑面积、密度）、人口热力图及避难所 POI 等多维数据，量化评估洪涝发生时的区域暴露性与综合影响指数。
4. **栅格与矢量工具箱**：
   - 内置影像对比、多图层行列对齐、局部统计分析、以及各类环境因子间的相关性分析（Pearson/Spearman）等丰富工具。
5. **评估结果分析与导出**：
   - 自动生成数据报表与可视化图表（ECharts），并支持一键将结果数据导出为 CSV 等格式，供进一步学术研究或报告编写使用。

## 技术栈 (Tech Stack)
- **后端 (Backend)**: Python, Flask, GDAL, Rasterio, GeoPandas, Shapely, Scikit-learn, Numpy, Pandas.
- **前端 (Frontend)**: Vue.js 2.x, Element UI, OpenLayers (ol), Mapbox GL, ECharts, Turf.js.

## 效果图展示 (Screenshots)

### 效果图1：平台图层管理与底图交互
![效果图1](images/效果图1.png)

### 效果图2：洪水分析与暴露性评估结果
![效果图2](images/效果图2.png)

## 环境搭建与快速开始 (Getting Started)

### 1. 环境准备
- 安装 [Miniconda](https://docs.conda.io/en/latest/miniconda.html) 或 Anaconda (用于后端环境隔离)。
- 安装 [Node.js](https://nodejs.org/) (推荐使用 v14 或 v16 版本用于前端编译)。

### 2. 后端部署 (Conda 环境)

> ⚠️ **【排查避坑提示】**
> 在 Windows 下通过 VSCode/Trae 自带的终端运行 Conda 环境时，经常会出现 Python 环境或库（如 GDAL）版本错乱的情况。**排查时请始终先检查环境激活状态及所使用的 Python 路径**（可使用 `where python` 命令确认当前是否处于新建的 conda 虚拟环境中）。

```bash
# 进入后端目录
cd backend

# 1. 创建名为 flood_env 的 Conda 虚拟环境 (推荐 Python 3.8/3.9)
conda create -n flood_env python=3.9 -y

# 2. 激活虚拟环境
conda activate flood_env

# 3. 安装后端核心依赖
pip install -r requirements.txt
# 注意：由于 GDAL 等地理空间库在 Windows 下直接 pip 安装可能报错，
# 建议通过 conda 优先安装 gdal，或者使用对应的 .whl 文件安装。
# conda install -c conda-forge gdal

# 4. 运行后端服务
python app.py
```
后端服务默认将在 `http://127.0.0.1:5000` 启动。

### 3. 前端部署

```bash
# 打开新的终端，进入前端目录
cd frontend

# 1. 安装前端依赖
npm install

# 2. 启动前端开发服务器
npm run serve
```
前端服务启动后，通过浏览器访问控制台输出的地址（通常为 `http://localhost:8080`）即可使用平台。

### 4. 数据配置
将所需的地理数据集（如 DEM、建筑 SHP 等）放置于 `backend/data/` 目录下，前端平台即可读取并进行图层渲染与评估计算。

## 开源与商用声明 (License & Usage Terms)
本项目已开源至 GitHub，欢迎学习与交流。

**关于商业使用的特别声明**：
1. **允许原版商用**：您可以将本项目的**未修改版本**直接用于商业目的。
2. **修改商用需授权**：如果您对本项目的源代码、UI界面或核心算法进行了**任何形式的修改**，并将其用于**商业用途（包括但不限于出售衍生软件、提供商业化SaaS服务、用于企业内部盈利项目等）**，**必须向原作者支付相应的授权费用**。

如需获取修改商用授权或有其他合作意向，请联系项目原作者。
