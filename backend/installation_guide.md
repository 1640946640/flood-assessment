# 洪涝灾害评估软件安装指南

本文档提供洪涝灾害评估软件的环境配置与依赖安装说明。

## 系统要求

- Python 3.8+
- 足够的存储空间用于GIS数据处理（建议10GB以上）

## 方法一：使用 pip 安装（简单方式）

```bash
# 克隆或下载项目后，进入项目根目录
cd 洪涝灾害评估软件

# 创建虚拟环境（推荐）
python -m venv venv

# 激活虚拟环境
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

注意：GDAL、Rasterio等GIS库可能在直接使用pip安装时遇到困难，建议使用方法二。

## 方法二：使用 Conda 安装（推荐方式）

Conda 可以更好地处理 GDAL、Rasterio 等复杂依赖。

```bash
# 创建新的conda环境
conda create -n flood-assessment python=3.8

# 激活环境
conda activate flood-assessment

# 首先安装复杂的GIS依赖
conda install -c conda-forge gdal rasterio geopandas

# 安装其他依赖
conda install -c conda-forge flask flask-cors python-dotenv numpy matplotlib shapely pandas jenkspy scikit-learn scipy tqdm
```

## 方法三：分步安装

如果你遇到安装问题，可以尝试分步安装：

### 1. 安装基本依赖

```bash
pip install Flask flask-cors python-dotenv numpy pandas scipy matplotlib scikit-learn tqdm jenkspy
```

### 2. 安装GIS依赖

#### Windows

Windows用户可以使用非官方编译的轮子：

```bash
# 安装GDAL
pip install GDAL‑<version>‑cp<python_version>‑win_amd64.whl

# 安装其他GIS依赖
pip install rasterio shapely geopandas
```

可以从 [Christoph Gohlke's Unofficial Windows Binaries](https://www.lfd.uci.edu/~gohlke/pythonlibs/) 下载预编译的轮子。

#### Linux

在Linux上，需要先安装系统级依赖：

```bash
# Ubuntu/Debian
sudo apt-get install libgdal-dev

# 设置环境变量
export CPLUS_INCLUDE_PATH=/usr/include/gdal
export C_INCLUDE_PATH=/usr/include/gdal

# 安装Python绑定
pip install GDAL==`gdal-config --version`
pip install rasterio shapely geopandas
```

## 常见问题

### GDAL安装失败

如果GDAL安装失败，请先检查系统是否已安装GDAL库。使用conda安装是避免此类问题的最简单方法。

### 找不到库

确保已激活正确的虚拟环境：

```bash
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate
```

### 版本冲突

如遇版本冲突，可以尝试创建新的独立环境：

```bash
conda create -n flood-assessment-new python=3.8
conda activate flood-assessment-new
# 重新安装依赖
```

## 验证安装

安装完成后，可以通过以下命令验证环境：

```python
python -c "import gdal; import rasterio; import geopandas; import flask; print('环境配置成功!')"
```

## 启动应用

```bash
# 启动后端服务
cd backend
flask run --host=0.0.0.0 --port=5000
``` 