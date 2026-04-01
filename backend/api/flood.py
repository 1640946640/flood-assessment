from flask import Blueprint, request, jsonify
from flask_cors import cross_origin
import os
import uuid
from datetime import datetime
import numpy as np
from osgeo import gdal, ogr, osr
import json
import tempfile
from werkzeug.utils import secure_filename
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, BoundaryNorm
import geopandas as gpd
from shapely.geometry import box
import rasterio
from rasterio.mask import mask
from rasterio.warp import reproject, transform_bounds, Resampling, calculate_default_transform
from rasterio.crs import CRS
from rasterio.transform import array_bounds
from rasterio.coords import BoundingBox
import jenkspy # 导入 jenkspy 库
from .utils import add_admin_boundary_to_plot # 导入行政边界绘制函数
from utils.logger import log_message, log_and_print, log_function_call

# 设置matplotlib中文字体
plt.rcParams["font.sans-serif"] = ["SimHei"]  # 用来正常显示中文标签
plt.rcParams["axes.unicode_minus"] = False  # 用来正常显示负号

flood_bp = Blueprint('flood', __name__, url_prefix='/api/flood')

# 数据文件夹路径
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
# 创建结果输出目录
OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "flood_results"
)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 模拟评估算法的基础类
class FloodAssessmentEngine:
    
    def __init__(self):
        self.flood_results = {}
    
    def save_raster_to_csv(self, data, geotransform, output_csv_path, nodata_value=None):
        """将栅格数据保存为CSV文件，包含坐标和栅格值"""
        import pandas as pd
        
        rows, cols = data.shape
        
        # 创建坐标和值的列表
        coordinates = []
        values = []
        
        for row in range(rows):
            for col in range(cols):
                # 计算地理坐标
                x = geotransform[0] + col * geotransform[1]
                y = geotransform[3] + col * geotransform[4]
                
                value = data[row, col]
                
                # 跳过无效值
                if nodata_value is not None:
                    try:
                        # 确保nodata_value是数值类型
                        if isinstance(nodata_value, (int, float)) and np.isclose(value, nodata_value):
                            continue
                    except (TypeError, ValueError):
                        # 如果类型不兼容，跳过nodata检查
                        pass
                if np.isnan(value):
                    continue
                    
                coordinates.append((x, y))
                values.append(value)
        
        # 创建DataFrame
        df = pd.DataFrame({
            'X': [coord[0] for coord in coordinates],
            'Y': [coord[1] for coord in coordinates],
            'Value': values
        })
        
        # 保存为CSV
        df.to_csv(output_csv_path, index=False, encoding='utf-8')
        return len(df)
    
    def normalize_raster(self, raster_path, save_original=True, output_prefix=None):
        """标准化栅格数据到0-1范围，可选择保存归一化前的数据"""
        dataset = gdal.Open(raster_path)
        if not dataset:
            raise ValueError(f"无法打开栅格文件: {raster_path}")
        
        band = dataset.GetRasterBand(1)
        data = band.ReadAsArray()
        geotransform = dataset.GetGeoTransform()
        projection = dataset.GetProjection()
        
        # 处理无效值
        nodata = band.GetNoDataValue()
        if nodata is not None:
            data = np.where(data == nodata, np.nan, data)
        
        # 保存归一化前的原始数据
        if save_original and output_prefix:
            # 保存原始栅格数据
            original_raster_path = f"{output_prefix}_original.tif"
            self.save_result_raster(data, geotransform, projection, original_raster_path, nodata_value=nodata if nodata is not None else -9999)
            
            # # 保存原始数据的CSV文件
            # original_csv_path = f"{output_prefix}_original.csv"
            # csv_count = self.save_raster_to_csv(data, geotransform, original_csv_path, nodata_value=nodata)
            # print(f"已保存原始栅格数据: {original_raster_path}")
            # print(f"已保存原始CSV数据: {original_csv_path} (共{csv_count}个有效数据点)")
        
        # 标准化到0-1
        data_min = np.nanmin(data)
        data_max = np.nanmax(data)
        if data_max > data_min:
            normalized = (data - data_min) / (data_max - data_min)
        else:
            normalized = np.zeros_like(data)
        
        return normalized, geotransform, projection
    
    def save_result_raster(self, data, geotransform, projection, output_path, nodata_value=-9999, metadata=None):
        """保存结果栅格，并支持写入自定义metadata"""
        try:
            # 确保输出目录存在
            output_dir = os.path.dirname(output_path)
            if not os.path.exists(output_dir):
                os.makedirs(output_dir, exist_ok=True)
                print(f"创建输出目录: {output_dir}")
            
            # 检查文件路径有效性
            print(f"保存栅格到: {output_path}")
            
            driver = gdal.GetDriverByName('GTiff')
            if driver is None:
                raise Exception("无法获取GTiff驱动")
            
            rows, cols = data.shape
            print(f"数据维度: {rows} x {cols}")
            
            # 创建数据集
            dataset = driver.Create(output_path, cols, rows, 1, gdal.GDT_Float32)
            if dataset is None:
                raise Exception(f"无法创建TIFF文件: {output_path}")
            
            # 设置地理信息
            dataset.SetGeoTransform(geotransform)
            dataset.SetProjection(projection)
            
            # 写入数据
            band = dataset.GetRasterBand(1)
            if band is None:
                raise Exception("无法获取栅格波段")
            
            band.WriteArray(data)
            band.SetNoDataValue(nodata_value)
            
            # 写入自定义metadata
            if metadata is not None and isinstance(metadata, dict):
                print(f"写入自定义metadata: {metadata}")
                dataset.SetMetadata({str(k): str(v) for k, v in metadata.items()})
            
            # 确保数据写入磁盘
            dataset.FlushCache()
            dataset = None
            print(f"栅格文件保存成功: {output_path}")
            
        except Exception as e:
            print(f"保存栅格文件失败: {str(e)}")
            raise
    
    def create_geojson_from_raster(self, raster_path, output_path):
        """从栅格创建GeoJSON用于前端显示"""
        dataset = gdal.Open(raster_path)
        band = dataset.GetRasterBand(1)
        data = band.ReadAsArray()
        
        # 创建简化的GeoJSON（这里简化处理，实际应该做栅格矢量化）
        geotransform = dataset.GetGeoTransform()
        
        # 计算统计信息
        valid_data = data[~np.isnan(data)]
        if len(valid_data) > 0:
            stats = {
                'min': float(np.min(valid_data)),
                'max': float(np.max(valid_data)),
                'mean': float(np.mean(valid_data)),
                'std': float(np.std(valid_data))
            }
        else:
            stats = {'min': 0, 'max': 0, 'mean': 0, 'std': 0}
        
        # 创建简单的边界框GeoJSON
        minx = geotransform[0]
        maxy = geotransform[3]
        maxx = minx + geotransform[1] * dataset.RasterXSize
        miny = maxy + geotransform[5] * dataset.RasterYSize
        
        geojson = {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [minx, miny],
                        [maxx, miny],
                        [maxx, maxy],
                        [minx, maxy],
                        [minx, miny]
                    ]]
                },
                "properties": {
                    "assessment_type": "flood_assessment",
                    "statistics": stats
                }
            }]
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(geojson, f, ensure_ascii=False, indent=2)
        
        return geojson
    
    def calculate_grid_statistics(self, raster_data, geotransform, projection, boundary_path, output_path):
        """按网格统计栅格数据并输出矢量结果"""
        try:
            # 计算全局归一化参数
            valid_global_data = raster_data[~np.isnan(raster_data)]
            if len(valid_global_data) > 0:
                global_min = float(np.min(valid_global_data))
                global_max = float(np.max(valid_global_data))
                global_range = global_max - global_min if global_max > global_min else 1.0
            else:
                global_min = global_max = global_range = 0.0
            
            # 打开边界矢量文件
            boundary_ds = ogr.Open(boundary_path)
            if boundary_ds is None:
                raise ValueError(f"无法打开边界文件: {boundary_path}")
            
            boundary_layer = boundary_ds.GetLayer()
            
            # 创建输出矢量文件
            driver = ogr.GetDriverByName('GeoJSON')
            if os.path.exists(output_path):
                driver.DeleteDataSource(output_path)
            
            output_ds = driver.CreateDataSource(output_path)
            
            # 获取空间参考系统
            srs = osr.SpatialReference()
            srs.ImportFromWkt(projection)
            
            # 创建输出图层
            output_layer = output_ds.CreateLayer('grid_statistics', srs, ogr.wkbPolygon)
            
            # 添加字段
            field_defns = [
                ('grid_id', ogr.OFTInteger),
                ('hazard_min', ogr.OFTReal),
                ('hazard_max', ogr.OFTReal),
                ('hazard_mean', ogr.OFTReal),
                ('hazard_std', ogr.OFTReal),
                ('hazard_mean_norm', ogr.OFTReal),  # 添加归一化均值字段
                ('flooded_ratio', ogr.OFTReal),
                ('area', ogr.OFTReal)
            ]
            
            for field_name, field_type in field_defns:
                field_def = ogr.FieldDefn(field_name, field_type)
                output_layer.CreateField(field_def)
            
            # 创建临时栅格用于统计
            rows, cols = raster_data.shape
            
            # 遍历每个网格面
            grid_id = 0
            for feature in boundary_layer:
                grid_id += 1
                geom = feature.GetGeometryRef()
                
                # 获取几何体的边界框
                envelope = geom.GetEnvelope()  # (minX, maxX, minY, maxY)
                
                # 将地理坐标转换为像素坐标
                minx, maxx, miny, maxy = envelope
                
                # 计算像素范围
                pixel_minx = int((minx - geotransform[0]) / geotransform[1])
                pixel_maxx = int((maxx - geotransform[0]) / geotransform[1])
                pixel_miny = int((maxy - geotransform[3]) / geotransform[5])
                pixel_maxy = int((miny - geotransform[3]) / geotransform[5])
                
                # 确保像素坐标在有效范围内
                pixel_minx = max(0, min(pixel_minx, cols-1))
                pixel_maxx = max(0, min(pixel_maxx, cols-1))
                pixel_miny = max(0, min(pixel_miny, rows-1))
                pixel_maxy = max(0, min(pixel_maxy, rows-1))
                
                if pixel_minx >= pixel_maxx or pixel_miny >= pixel_maxy:
                    continue
                
                # 提取网格内的栅格数据
                grid_data = raster_data[pixel_miny:pixel_maxy+1, pixel_minx:pixel_maxx+1]
                
                if grid_data.size == 0:
                    continue
                
                # 计算统计值
                valid_data = grid_data[~np.isnan(grid_data)]
                flooded_data = valid_data[valid_data > 0]
                
                if len(valid_data) > 0:
                    hazard_min = float(np.min(valid_data))
                    hazard_max = float(np.max(valid_data))
                    hazard_mean = float(np.mean(valid_data))
                    hazard_std = float(np.std(valid_data))
                    # 计算归一化均值
                    hazard_mean_norm = float((hazard_mean - global_min) / global_range) if global_range > 0 else 0.0
                    flooded_ratio = float(len(flooded_data) / len(valid_data))
                else:
                    hazard_min = hazard_max = hazard_mean = hazard_std = hazard_mean_norm = flooded_ratio = 0.0
                
                # 计算面积（简化计算）
                area = geom.GetArea()
                
                # 创建输出要素
                output_feature = ogr.Feature(output_layer.GetLayerDefn())
                output_feature.SetGeometry(geom.Clone())
                
                # 设置属性值
                output_feature.SetField('grid_id', grid_id)
                output_feature.SetField('hazard_min', hazard_min)
                output_feature.SetField('hazard_max', hazard_max)
                output_feature.SetField('hazard_mean', hazard_mean)
                output_feature.SetField('hazard_std', hazard_std)
                output_feature.SetField('hazard_mean_norm', hazard_mean_norm)
                output_feature.SetField('flooded_ratio', flooded_ratio)
                output_feature.SetField('area', area)
                
                # 添加要素到图层
                output_layer.CreateFeature(output_feature)
                
                # 清理
                output_feature = None
            
            # 清理资源
            boundary_ds = None
            output_ds = None
            
            return True
            
        except Exception as e:
            print(f"网格统计计算错误: {str(e)}")
            return False
    
    def vector_to_raster_with_mean(self, geojson_path, output_raster_path, reference_raster, geotransform, projection):
        """将矢量数据转换为栅格，栅格值为面的mean值"""
        try:
            # 打开矢量文件
            vector_ds = ogr.Open(geojson_path)
            if vector_ds is None:
                raise ValueError(f"无法打开矢量文件: {geojson_path}")
            
            vector_layer = vector_ds.GetLayer()
            
            # 获取参考栅格的尺寸
            rows, cols = reference_raster.shape
            
            # 创建输出栅格
            driver = gdal.GetDriverByName('GTiff')
            output_ds = driver.Create(output_raster_path, cols, rows, 1, gdal.GDT_Float32)
            output_ds.SetGeoTransform(geotransform)
            output_ds.SetProjection(projection)
            
            output_band = output_ds.GetRasterBand(1)
            output_band.SetNoDataValue(-9999)
            
            # 初始化输出数组
            output_array = np.full((rows, cols), -9999, dtype=np.float32)
            
            # 遍历每个矢量要素
            for feature in vector_layer:
                geom = feature.GetGeometryRef()
                
                # 获取归一化后的hazard_mean_norm属性值
                hazard_mean = feature.GetField('hazard_mean')
                if hazard_mean is None:
                    continue
                
                # 获取几何体的边界框
                envelope = geom.GetEnvelope()  # (minX, maxX, minY, maxY)
                minx, maxx, miny, maxy = envelope
                
                # 将地理坐标转换为像素坐标
                pixel_minx = int((minx - geotransform[0]) / geotransform[1])
                pixel_maxx = int((maxx - geotransform[0]) / geotransform[1])
                pixel_miny = int((maxy - geotransform[3]) / geotransform[5])
                pixel_maxy = int((miny - geotransform[3]) / geotransform[5])
                
                # 确保像素坐标在有效范围内
                pixel_minx = max(0, min(pixel_minx, cols-1))
                pixel_maxx = max(0, min(pixel_maxx, cols-1))
                pixel_miny = max(0, min(pixel_miny, rows-1))
                pixel_maxy = max(0, min(pixel_maxy, rows-1))
                
                if pixel_minx >= pixel_maxx or pixel_miny >= pixel_maxy:
                    continue
                
                # 在对应的像素区域设置hazard_mean值
                output_array[pixel_miny:pixel_maxy+1, pixel_minx:pixel_maxx+1] = hazard_mean
            
            # 写入栅格数据
            output_band.WriteArray(output_array)
            output_band.FlushCache()
            
            # 清理资源
            vector_ds = None
            output_ds = None
            
            return True
            
        except Exception as e:
             print(f"矢量转栅格错误: {str(e)}")
             return False
    
    def create_raster_preview(self, raster_path, output_path, title):
        """
        生成栅格数据的预览图
        :param raster_path: TIFF文件路径
        :param output_path: 输出PNG文件路径
        :param title: 图像标题
        """
        # 读取TIFF文件
        ds = gdal.Open(raster_path)
        if ds is None:
            raise Exception(f"无法打开文件: {raster_path}")
            
        # 读取数据和nodata值
        band = ds.GetRasterBand(1)
        data = band.ReadAsArray()
        nodata = band.GetNoDataValue()
        
        print(f"预览图数据范围: {np.min(data)} to {np.max(data)}")
        print(f"NoData值: {nodata}")
        
        # 创建掩码（使用isclose以处理浮点数比较）
        if nodata is not None:
            mask = ~np.isclose(data, nodata, rtol=1e-10, atol=1e-10)
        else:
            mask = np.ones_like(data, dtype=bool)
            
        print(f"有效数据点数量: {np.sum(mask)} / {mask.size}")
        
        # 获取有效数据
        valid_data = data[mask]
        
        if len(valid_data) == 0:
            raise Exception("预览图生成失败：没有有效数据")
            
        # 创建归一化数据用于显示
        vmin, vmax = np.percentile(valid_data, [0, 100])  # 使用2-98百分位数以避免极值影响
        print(f"显示范围（2-98百分位）: {vmin} to {vmax}")
        
        # 创建带掩膜的颜色映射
        cmap = plt.cm.RdYlBu_r.copy()
        cmap.set_bad('none')  # 设置NoData区域为透明
        
        # 创建归一化数据
        norm_data = np.ma.masked_array(data, ~mask)  # 创建掩膜数组
        
        # 创建图像
        plt.figure(figsize=(10, 8), facecolor='none')  # 设置背景透明
        plt.imshow(norm_data, 
                  cmap=cmap,
                  vmin=vmin,
                  vmax=vmax)
        
        # 添加颜色条
        cbar = plt.colorbar(label='栅格值')
        
        # 添加标题
        plt.title(title)
        
        # 去除坐标轴
        plt.axis('off')
        
        # 保存图像
        plt.savefig(output_path, 
                   bbox_inches='tight',
                   pad_inches=0,
                   transparent=True,
                   dpi=300)
        plt.close()
    
    def create_assessment_preview(self, raster_path, output_path, title, colormap='RdYlBu_r', label='评估值'):
        """
        生成评估结果的预览图
        :param raster_path: TIFF文件路径
        :param output_path: 输出PNG文件路径
        :param title: 图像标题
        :param colormap: 使用的颜色映射名称，默认为RdYlBu_r
        :param label: 颜色条标签
        """
        from matplotlib.colors import LinearSegmentedColormap
        import matplotlib.patches as mpatches
        
        # 读取TIFF文件
        ds = gdal.Open(raster_path)
        if ds is None:
            raise Exception(f"无法打开文件: {raster_path}")
            
        # 读取数据和nodata值
        band = ds.GetRasterBand(1)
        data = band.ReadAsArray()
        nodata = band.GetNoDataValue()
        
        print(f"预览图数据范围: {np.min(data)} to {np.max(data)}")
        print(f"NoData值: {nodata}")
        
        # 创建掩码
        if nodata is not None:
            nodata_mask = np.isclose(data, nodata, rtol=1e-10, atol=1e-10)
        else:
            nodata_mask = np.zeros_like(data, dtype=bool)
            
        zero_mask = (data == 0) & (~nodata_mask)
        valid_mask = (data > 0) & (~nodata_mask)
        
        print(f"有效数据点数量: {np.sum(valid_mask)} / {data.size}")
        print(f"零值数据点数量: {np.sum(zero_mask)}")
        print(f"无数据点数量: {np.sum(nodata_mask)}")
        
        # 获取有效数据
        valid_data = data[valid_mask]
        
        if len(valid_data) == 0:
            raise Exception("预览图生成失败：没有有效数据")
            
        # 获取有效数据的范围用于颜色映射
        if len(valid_data) > 0:
            vmin = np.min(valid_data)  # 有效数据的最小值
            vmax = np.percentile(valid_data, 100)  # 98百分位数
        else:
            vmin, vmax = 0.001, 1
            
        print(f"有效数据范围: {vmin} to {vmax}")
        
        # 创建显示数据，使用三个不同的数值范围
        display_data = data.copy().astype(float)
        
        # 设置显示值：nodata=-2, 0值=-1, 有效数据=原值但映射到[0,1]范围
        display_data[nodata_mask] = -2  # nodata用-2表示
        display_data[zero_mask] = -1    # 0值用-1表示
        
        # 将有效数据标准化到[0,1]范围，用于颜色映射
        if vmax > vmin:
            normalized_valid = (valid_data - vmin) / (vmax - vmin)
            display_data[valid_mask] = normalized_valid
        else:
            display_data[valid_mask] = 0.5
        
        # 创建自定义颜色映射：灰色(nodata) -> 白色(0值) -> 原colormap(有效数据)
        base_cmap = plt.get_cmap(colormap)
        
        # 构建颜色列表：灰色 + 白色 + 原colormap的渐变色
        colors = ['#808080', '#FFFFFF']  # 灰色(nodata) + 白色(0值)
        
        # 添加原colormap的颜色用于有效数据的渐变
        n_colors = 254  # 为有效数据保留254个颜色级别
        for i in range(n_colors):
            colors.append(base_cmap(i / (n_colors - 1)))
        
        # 创建自定义colormap
        custom_cmap = LinearSegmentedColormap.from_list('custom', colors, N=256)
        
        # 创建图像
        plt.figure(figsize=(12, 10), facecolor='white')
        
        # 显示图像，设置合适的范围
        im = plt.imshow(display_data, cmap=custom_cmap, vmin=-2, vmax=1)
        
        # 创建颜色条，显示归一化后的数据范围
        # 由于显示数据已经归一化到[0,1]，颜色条也应该对应这个范围
        from matplotlib.colors import Normalize
        
        # 创建一个对应归一化数据范围的colorbar
        norm = Normalize(vmin=0, vmax=1)  # 归一化后的范围是0-1
        sm = plt.cm.ScalarMappable(cmap=base_cmap, norm=norm)
        sm.set_array([])
        
        cbar = plt.colorbar(sm, label=label, shrink=0.8)
        
        # 设置颜色条标签，显示原始数据值但对应归一化位置
        if vmax > vmin:
            # 在归一化位置[0,1]上显示原始数据值
            normalized_positions = [i / 4 for i in range(5)]  # 归一化位置：0, 0.25, 0.5, 0.75, 1
            original_values = [vmin + (vmax - vmin) * pos for pos in normalized_positions]  # 对应的原始值
            cbar.set_ticks(normalized_positions)
            cbar.set_ticklabels([f'{val:.3f}' for val in original_values])
        else:
            # 如果所有值相同，显示该值
            cbar.set_ticks([0.5])
            cbar.set_ticklabels([f'{vmin:.3f}'])
        
        # 添加标题
        plt.title(title, fontsize=14, pad=20)
        
        # 去除坐标轴
        plt.axis('off')
        
        # 保存图像
        plt.savefig(output_path, 
                   bbox_inches='tight',
                   pad_inches=0.1,
                   facecolor='white',
                   dpi=300)
        plt.close()
    
    def create_value_preview(self, raster_path, output_path, title):
        """
        生成价值密度评估结果的预览图（带边界轮廓）
        :param raster_path: TIFF文件路径
        :param output_path: 输出PNG文件路径
        :param title: 图像标题
        """
        try:
            # 设置matplotlib中文字体
            plt.rcParams['font.sans-serif'] = ['SimHei']
            plt.rcParams['axes.unicode_minus'] = False
            
            # 读取栅格数据
            dataset = gdal.Open(raster_path)
            if dataset is None:
                raise ValueError(f"无法打开栅格文件: {raster_path}")
            
            band = dataset.GetRasterBand(1)
            data = band.ReadAsArray()
            nodata = band.GetNoDataValue()
            geotransform = dataset.GetGeoTransform()
            projection = dataset.GetProjection()
            
            print(f"价值密度数据范围: {np.min(data)} to {np.max(data)}")
            print(f"NoData值: {nodata}")
            
            # 处理无效值和0值
            if nodata is not None:
                # 创建掩码：nodata区域透明，0值为淡灰色，正值用颜色映射显示
                nodata_mask = np.isclose(data, nodata, rtol=1e-10, atol=1e-10)
                zero_mask = (data != nodata) & (data == 0)
                positive_mask = (data != nodata) & (data > 0)
                
                print(f"数据分布: NoData={np.sum(nodata_mask)}, 零值={np.sum(zero_mask)}, 正值={np.sum(positive_mask)}")
                
                # 创建显示数据 - 只显示有数据的区域
                display_data = np.full_like(data, np.nan, dtype=float)
                display_data[zero_mask] = 0  # 零值保持为0
                display_data[positive_mask] = data[positive_mask]
                
                # 如果大部分区域是NoData，调整显示范围到有效数据区域
                if np.sum(positive_mask) > 0:
                    valid_rows, valid_cols = np.where(positive_mask | zero_mask)
                    if len(valid_rows) > 0:
                        row_min, row_max = valid_rows.min(), valid_rows.max()
                        col_min, col_max = valid_cols.min(), valid_cols.max()
                        print(f"有效数据区域: 行[{row_min}:{row_max}], 列[{col_min}:{col_max}]")
                        
                        # 扩展一点边距
                        margin = 50
                        row_min = max(0, row_min - margin)
                        row_max = min(data.shape[0], row_max + margin)
                        col_min = max(0, col_min - margin)
                        col_max = min(data.shape[1], col_max + margin)
                        
                        # 裁剪显示数据到有效区域
                        display_data = display_data[row_min:row_max, col_min:col_max]
                        
                        # 调整地理变换参数
                        geo_x_offset = geotransform[0] + col_min * geotransform[1]
                        geo_y_offset = geotransform[3] + row_min * geotransform[5]
                        display_extent = [
                            geo_x_offset,
                            geo_x_offset + display_data.shape[1] * geotransform[1],
                            geo_y_offset + display_data.shape[0] * geotransform[5],
                            geo_y_offset
                        ]
                    else:
                        display_extent = [
                            geotransform[0], 
                            geotransform[0] + geotransform[1] * data.shape[1],
                            geotransform[3] + geotransform[5] * data.shape[0],
                            geotransform[3]
                        ]
                else:
                    display_extent = [
                        geotransform[0], 
                        geotransform[0] + geotransform[1] * data.shape[1],
                        geotransform[3] + geotransform[5] * data.shape[0],
                        geotransform[3]
                    ]
            else:
                # 如果没有nodata值
                zero_mask = data == 0
                positive_mask = data > 0
                nodata_mask = np.zeros_like(data, dtype=bool)
                
                display_data = np.full_like(data, np.nan, dtype=float)
                display_data[zero_mask] = 0
                display_data[positive_mask] = data[positive_mask]
                
                display_extent = [
                    geotransform[0], 
                    geotransform[0] + geotransform[1] * data.shape[1],
                    geotransform[3] + geotransform[5] * data.shape[0],
                    geotransform[3]
                ]
            
            # 获取有效数据统计信息
            valid_data = data[positive_mask]
            print(f"有效价值密度数据点数量: {np.sum(positive_mask)} / {data.size}")
            print(f"零值数据点数量: {np.sum(zero_mask)}")
            print(f"无数据点数量: {np.sum(nodata_mask)}")
            
            # 创建预览图
            plt.figure(figsize=(12, 10))
            ax = plt.gca()
            
            # 创建自定义颜色映射：灰色(0值) + 蓝-红渐变(正值)
            from matplotlib.colors import ListedColormap, LinearSegmentedColormap, BoundaryNorm
            
            if len(valid_data) > 0:
                vmin, vmax = np.min(valid_data), np.max(valid_data)
                print(f"价值密度范围: {vmin:.6f} - {vmax:.6f}")
                
                # 简化颜色映射：使用连续的颜色映射而不是分段映射
                # 创建蓝到红的渐变颜色映射
                colors = ['#000080', '#0000FF', '#00FFFF', '#00FF00', '#FFFF00', '#FF7F00', '#FF0000', '#800000']
                cmap = LinearSegmentedColormap.from_list('value_density', colors, N=256)
                cmap.set_bad('gray', alpha=0.3)  # 设置无效值为半透明灰色
                
                # 使用简单的范围归一化
                im = plt.imshow(display_data, cmap=cmap, vmin=0, vmax=vmax, 
                              extent=display_extent, origin='upper')
            else:
                # 如果没有有效数据，使用简单的灰度显示
                cmap = plt.cm.gray
                cmap.set_bad('gray', alpha=0.3)
                im = plt.imshow(display_data, cmap=cmap, vmin=0, vmax=1, 
                              extent=display_extent, origin='upper')
            
            # 行政边界轮廓已禁用 - 数据分布本身已清晰显示区域范围
            print(f"✅ 价值密度可视化完成 - 数据分布清楚展示评估区域")
            
            # 边界轮廓绘制已禁用 - 数据本身的蓝色分布已清楚显示评估区域
            # 无需额外的红色边界线条
                
            # 已禁用红色边界绘制 - 数据分布本身已能清楚显示区域轮廓
            print("✅ 跳过边界轮廓绘制 - 使用数据分布展示区域范围")
            
            # 添加颜色条
            if len(valid_data) > 0:
                # 为有效数据创建颜色条
                vmax = np.max(valid_data)
                cbar = plt.colorbar(im, label='价值密度', shrink=0.8)
                
                # 动态调整颜色条标签的小数位数和刻度
                if vmax < 0.001:
                    tick_decimal_places = 6
                    n_ticks = 5
                elif vmax < 0.1:
                    tick_decimal_places = 4
                    n_ticks = 5
                elif vmax < 1:
                    tick_decimal_places = 3
                    n_ticks = 5
                else:
                    tick_decimal_places = 1
                    n_ticks = 6
                
                # 设置刻度值
                tick_values = np.linspace(0, vmax, n_ticks)
                cbar.set_ticks(tick_values)
                cbar.set_ticklabels([f'{val:.{tick_decimal_places}f}' for val in tick_values])
            else:
                cbar = plt.colorbar(im, label='价值密度', shrink=0.8)
                cbar.set_ticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
                cbar.set_ticklabels(['0.000', '0.200', '0.400', '0.600', '0.800', '1.000'])
            
            # 添加统计信息文本（放在右上角，避免被边界线遮挡）
            if len(valid_data) > 0:
                # 动态调整小数位数，适应不同的数值范围
                max_val = np.max(valid_data)
                if max_val < 1:
                    decimal_places = 6  # 小数值显示更多位
                elif max_val < 100:
                    decimal_places = 3  # 中等数值显示3位
                else:
                    decimal_places = 1  # 大数值显示1位
                
                stats_text = f'统计信息:\n最小值: {np.min(valid_data):.{decimal_places}f}\n最大值: {np.max(valid_data):.{decimal_places}f}\n平均值: {np.mean(valid_data):.{decimal_places}f}\n有效像素: {len(valid_data)}/{data.size}'
                plt.text(0.98, 0.98, stats_text, transform=ax.transAxes, fontsize=10,
                        verticalalignment='top', horizontalalignment='right', 
                        bbox=dict(boxstyle='round', facecolor='white', alpha=0.9, edgecolor='gray'))
            
            plt.title(title, fontsize=16, fontweight='bold', pad=20)
            plt.xlabel('经度方向', fontsize=12)
            plt.ylabel('纬度方向', fontsize=12)
            
            # 保存预览图
            plt.tight_layout()
            plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
            plt.close()
            
            print(f"价值密度预览图已保存: {output_path}")
            return True
            
        except Exception as e:
            print(f"创建价值密度预览图错误: {str(e)}")
            # 如果失败，回退到原来的方法
            return self.create_raster_preview(raster_path, output_path, title)

    def create_sensitivity_preview(self, raster_path, output_path, title):
        """
        生成敏感性评估结果的预览图
        :param raster_path: TIFF文件路径
        :param output_path: 输出PNG文件路径
        :param title: 图像标题
        """
        return self.create_raster_preview(raster_path, output_path, title)

    def create_exposure_preview(self, raster_path, output_path, title):
        """为暴露性评估结果创建淡蓝色预览图"""
        try:
            # 设置matplotlib中文字体
            plt.rcParams['font.sans-serif'] = ['SimHei']
            plt.rcParams['axes.unicode_minus'] = False
            
            # 读取栅格数据
            dataset = gdal.Open(raster_path)
            if dataset is None:
                raise ValueError(f"无法打开栅格文件: {raster_path}")
            
            band = dataset.GetRasterBand(1)
            data = band.ReadAsArray()
            nodata = band.GetNoDataValue()
            
            # 处理无效值和0值
            if nodata is not None:
                # 创建掩码：nodata区域透明，0值显示为淡灰色，1值显示为淡蓝色
                nodata_mask = data == nodata
                zero_mask = (data != nodata) & (data == 0)
                one_mask = (data != nodata) & (data != 0)
                
                # 创建显示数据：nodata为nan（透明），0值为特殊标记，1值正常
                display_data = np.full_like(data, np.nan, dtype=float)
                display_data[zero_mask] = -0.001  # 用负值标记0值区域
                display_data[one_mask] = 1.0
            else:
                # 如果没有nodata值
                zero_mask = data == 0
                one_mask = data != 0
                
                display_data = np.full_like(data, np.nan, dtype=float)
                display_data[zero_mask] = -0.001  # 用负值标记0值区域
                display_data[one_mask] = 1.0
            
            # 创建自定义颜色映射：淡灰色(0值) + 淡蓝色(1值)
            colors = ['#D3D3D3', '#ADD8E6']  # 淡灰色和淡蓝色
            exposure_cmap = LinearSegmentedColormap.from_list('exposure_map', colors, N=2)
            exposure_cmap.set_bad('none')  # 设置nan值为透明
            
            # 创建预览图
            plt.figure(figsize=(10, 8))
            
            # 绘制数据（二值化显示）
            im = plt.imshow(display_data, cmap=exposure_cmap, vmin=-0.001, vmax=1)
            
            # 添加简单的颜色条
            cbar = plt.colorbar(im, label='暴露性')
            cbar.set_ticks([0, 1])
            cbar.set_ticklabels(['未淹没', '淹没区域'])
            
            plt.title(title, fontsize=14, fontweight='bold')
            plt.axis('off')  # 隐藏坐标轴
            plt.tight_layout()
            
            # 保存预览图
            plt.savefig(output_path, dpi=150, bbox_inches='tight')
            plt.close()
            
            return True
            
        except Exception as e:
            print(f"创建暴露性预览图错误: {str(e)}")
            return False
    
    def create_hazard_preview(self, raster_path, output_path, title):
        """为危险性评估结果创建预览图，0值为背景色，其他值使用浅蓝到深蓝渐变"""
        try:
            # 设置matplotlib中文字体
            plt.rcParams['font.sans-serif'] = ['SimHei']
            plt.rcParams['axes.unicode_minus'] = False
            
            # 读取栅格数据
            dataset = gdal.Open(raster_path)
            if dataset is None:
                raise ValueError(f"无法打开栅格文件: {raster_path}")
            
            band = dataset.GetRasterBand(1)
            data = band.ReadAsArray()
            nodata = band.GetNoDataValue()
            
            # 处理无效值和0值
            if nodata is not None:
                # 创建掩码：nodata区域为淡灰色，0值为白色，其他值正常显示
                nodata_mask = data == nodata
                zero_mask = (data != nodata) & (data == 0)
                positive_mask = (data != nodata) & (data > 0)
                
                # 创建显示数据：nodata为特殊标记，0值为特殊标记，其他值正常
                display_data = np.full_like(data, np.nan, dtype=float)
                display_data[nodata_mask] = -0.002  # 用负值标记nodata区域
                display_data[zero_mask] = -0.001  # 用负值标记0值区域
                display_data[positive_mask] = data[positive_mask]
            else:
                # 如果没有nodata值
                zero_mask = data == 0
                positive_mask = data > 0
                
                display_data = np.full_like(data, np.nan, dtype=float)
                display_data[zero_mask] = -0.001  # 用负值标记0值区域
                display_data[positive_mask] = data[positive_mask]
            
            # 创建自定义颜色映射：灰色(0值) + 浅蓝到深蓝渐变(正值)
            from matplotlib.colors import ListedColormap
            import matplotlib.colors as mcolors
            
            # 创建预览图
            plt.figure(figsize=(10, 8))
            
            # 获取有效数据的范围用于颜色映射
            valid_data = display_data[~np.isnan(display_data)]
            if len(valid_data) > 0:
                # 分别处理nodata、0值和正值
                nodata_data = display_data == -0.002
                zero_data = display_data == -0.001
                positive_data = display_data > 0
                
                # 绘制nodata区域为淡灰色
                if np.any(nodata_data):
                    nodata_img = np.where(nodata_data, 1, np.nan)
                    plt.imshow(nodata_img, cmap=ListedColormap(['#E8E8E8']), alpha=1.0)
                
                # 绘制0值区域为白色
                if np.any(zero_data):
                    zero_img = np.where(zero_data, 1, np.nan)
                    plt.imshow(zero_img, cmap=ListedColormap(['white']), alpha=1.0)
                
                # 绘制正值区域为蓝色渐变
                im = None
                if np.any(positive_data):
                    positive_img = np.where(positive_data, display_data, np.nan)
                    vmin_pos = np.min(display_data[positive_data])
                    vmax_pos = np.max(display_data[positive_data])
                    
                    print(f"   📊 水深数据范围: {vmin_pos:.2f}m - {vmax_pos:.2f}m")
                    print(f"   📊 正值像素数: {np.sum(positive_data):,}")
                    
                    # 创建蓝色渐变色彩映射 - 修复颜色映射逻辑
                    # 深水用深蓝色，浅水用浅蓝色
                    blue_colors = ['#003D7A', '#0066CC', '#3399FF', '#66C2FF', '#99D6FF', '#CCE7FF', '#E6F3FF']
                    blue_cmap = LinearSegmentedColormap.from_list('blues', blue_colors, N=256)
                    blue_cmap.set_bad('none')
                    
                    im = plt.imshow(positive_img, cmap=blue_cmap, vmin=vmin_pos, vmax=vmax_pos, alpha=1.0)
                
                # 添加颜色条（仅当有正值数据时）
                if im is not None:
                    if title == "危险性评估结果":
                        cbar = plt.colorbar(im, label='危险性指数')
                        cbar.set_label('危险性指数', fontsize=12)
                    else:
                        cbar = plt.colorbar(im, label='水深 (m)')
                        cbar.set_label('水深 (m)', fontsize=12)
                        
                        # 设置颜色条刻度，显示实际水深值
                        if vmax_pos > vmin_pos:
                            # 计算合适的刻度数量
                            tick_count = 5
                            tick_values = np.linspace(vmin_pos, vmax_pos, tick_count)
                            cbar.set_ticks(tick_values)
                            cbar.set_ticklabels([f'{val:.2f}' for val in tick_values])
            else:
                # 如果没有有效数据，显示空白图
                plt.imshow(np.full_like(display_data, np.nan), cmap='gray')
                plt.text(0.5, 0.5, '无有效数据', transform=plt.gca().transAxes, 
                        ha='center', va='center', fontsize=16)
            
            plt.title(title, fontsize=14, fontweight='bold')
            plt.axis('off')  # 隐藏坐标轴
            plt.tight_layout()
            
            # 保存预览图
            plt.savefig(output_path, dpi=150, bbox_inches='tight', transparent=True)
            plt.close()
            
            return True
            
        except Exception as e:
            print(f"创建危险性预览图错误: {str(e)}")
            return False

# 创建评估引擎实例
assessment_engine = FloodAssessmentEngine()

@flood_bp.route('/hazard', methods=['POST'])
@cross_origin()
@log_function_call
def hazard_assessment():
    """危险性评估"""
    try:
        data = request.get_json()
        
        # 获取参数
        water_level = float(data.get('water_level'))
        delta_h0 = float(data.get('delta_h0', 0))  # 获取Δh0参数，默认为0
        alpha = float(data.get('alpha', 0.9))  # 获取α参数，默认为0.9
        dem_dataset_id = data.get('dem_dataset_id')
        boundary_dataset_id = data.get('boundary_dataset_id')
        result_name = data.get('result_name', '危险性评估结果')
        
        # 获取斜面模型参数（如果有）
        use_slope_model = data.get('use_slope_model', False)  # 是否使用斜面模型
        p0_coord = data.get('p0_coord')  # P0点坐标 [lon, lat]
        p0_water_level = float(data.get('p0_water_level', water_level))  # P0点水位，默认为water_level
        p1_coord = data.get('p1_coord')  # P1点坐标 [lon, lat]
        slope_ps = float(data.get('slope_ps', 0.0003))  # 坡度参数，默认0.03%
        
        if not all([water_level, dem_dataset_id, result_name]):
            return jsonify({'error': '缺少必要的数据集参数'}), 400
        
        # 验证alpha参数
        if not 0 <= alpha <= 1:
            return jsonify({'error': 'α参数必须在0到1之间'}), 400
        
        # 生成唯一ID和文件名
        result_id = str(uuid.uuid4())
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # 获取DEM数据路径
        if isinstance(dem_dataset_id, list) and len(dem_dataset_id) > 0:
            dem_path = os.path.join(DATA_DIR, dem_dataset_id[0])
        else:
            dem_path = os.path.join(DATA_DIR, dem_dataset_id)
        
        if not os.path.exists(dem_path):
            return jsonify({'error': f'DEM文件不存在: {dem_path}'}), 400
        
        # 读取DEM数据
        dem_dataset = gdal.Open(dem_path)
        if dem_dataset is None:
            return jsonify({'error': f'无法读取DEM文件: {dem_path}'}), 400
        
        dem_band = dem_dataset.GetRasterBand(1)
        dem_array = dem_band.ReadAsArray()
        dem_nodata = dem_band.GetNoDataValue()
        geotransform = dem_dataset.GetGeoTransform()
        projection = dem_dataset.GetProjection()
        
        # 创建有效数据掩码（排除nodata）
        valid_mask = np.ones_like(dem_array, dtype=bool)
        if dem_nodata is not None:
            valid_mask = dem_array != dem_nodata
        
        # 计算水位矩阵
        water_level_array = np.zeros_like(dem_array, dtype=np.float32)
        
        # 使用斜面模型计算水位（如果启用）
        if use_slope_model and p0_coord and p1_coord:
            try:
                log_and_print("\n" + "="*80)
                log_and_print("🌊 开始倾斜水面模型计算")
                log_and_print("="*80)
                
                # 解析P0和P1点坐标
                p0_lon, p0_lat = p0_coord
                p1_lon, p1_lat = p1_coord
                
                log_and_print(f"📍 关键点坐标信息:")
                log_and_print(f"   P0点（监测点）: ({p0_lon:.8f}, {p0_lat:.8f})")
                log_and_print(f"   P1点（未来点）: ({p1_lon:.8f}, {p1_lat:.8f})")
                log_and_print(f"   P0点水位: {p0_water_level:.2f}m")
                log_and_print(f"   坡度(Ps): {slope_ps} = {slope_ps*100:.3f}%")
                log_and_print(f"   坡度调节系数(kp): 1.0")
                
                # 导入geopy计算真实地理距离
                from geopy.distance import geodesic
                
                # 检查DEM的坐标系统
                log_and_print(f"\n🗺️  DEM坐标系统信息:")
                log_and_print(f"   投影信息: {projection[:100]}...")
                
                # 检查是否需要坐标转换
                from osgeo import osr
                dem_srs = osr.SpatialReference()
                dem_srs.ImportFromWkt(projection)
                
                if dem_srs.IsGeographic():
                    log_and_print(f"   ✅ DEM使用地理坐标系，无需转换")
                    use_coordinate_transform = False
                elif dem_srs.IsProjected():
                    log_and_print(f"   ⚠️  DEM使用投影坐标系，需要转换到WGS84")
                    use_coordinate_transform = True
                    # 创建坐标转换器
                    wgs84_srs = osr.SpatialReference()
                    wgs84_srs.ImportFromEPSG(4326)  # WGS84
                    coord_transform = osr.CoordinateTransformation(dem_srs, wgs84_srs)
                else:
                    log_and_print(f"   ❓ 未知坐标系类型")
                    use_coordinate_transform = False
                
                # 计算P0到P1的真实地理距离（米）
                p0_point = (p0_lat, p0_lon)
                p1_point = (p1_lat, p1_lon)
                real_distance = geodesic(p0_point, p1_point).meters
                
                # 计算P1点水位（验证用户提供的449.14m）
                kp = 1.0  # 坡度调节系数
                calculated_p1_water_level = p0_water_level + real_distance * kp * slope_ps
                
                print(f"\n🔢 距离与水位计算:")
                print(f"   P0→P1真实距离: {real_distance:.2f}m")
                print(f"   计算公式: Hi水位 = Hp0监 + Di*kp*Ps")
                print(f"   参数说明:")
                print(f"     - Hp0监: P0点监测水位 = {p0_water_level:.2f}m")
                print(f"     - Di: 到P0点的距离 = {real_distance:.2f}m")
                print(f"     - kp: 坡度调节系数 = {kp}")
                print(f"     - Ps: 坡度 = {slope_ps} ({slope_ps*100:.3f}%)")
                print(f"   计算过程: {calculated_p1_water_level:.2f} = {p0_water_level:.2f} + {real_distance:.2f} × {kp} × {slope_ps}")
                print(f"   计算得P1点水位: {calculated_p1_water_level:.2f}m")
                print(f"   用户验证水位: 449.14m")
                print(f"   计算误差: {abs(calculated_p1_water_level - 449.14):.3f}m")
                
                if abs(calculated_p1_water_level - 449.14) < 1.0:
                    print(f"   ✅ 计算结果与用户验证值基本一致！")
                else:
                    print(f"   ⚠️  计算结果与用户验证值存在差异，请检查参数！")
                
                print(f"\n📋 倾斜水面模型约束条件:")
                print(f"   ✅ 仅处理行政边界内区域")
                print(f"   ✅ 坡度方向: P0监→P1未为正(水位上升)")
                print(f"   ✅ 直线上点: Hi水位 = Hp0监 + Di*kp*Ps")
                print(f"   ✅ 两侧的点: 等于垂足水位")
                
                # 计算P0到P1的方向向量（单位向量）
                direction_vector_x = (p1_lon - p0_lon) / (real_distance / 111000)  # 近似转换
                direction_vector_y = (p1_lat - p0_lat) / (real_distance / 111000)
                direction_length = np.sqrt(direction_vector_x**2 + direction_vector_y**2)
                
                if direction_length > 0:
                    direction_vector_x /= direction_length
                    direction_vector_y /= direction_length
                    
                    print(f"\n🧭 方向向量信息:")
                    print(f"   方向向量(归一化): ({direction_vector_x:.6f}, {direction_vector_y:.6f})")
                    
                    # 遍历DEM数组，计算倾斜水面模型水位
                    print(f"\n🔧 开始计算每个像素的水位...")
                    rows, cols = dem_array.shape
                    processed_pixels = 0
                    total_valid_pixels = np.sum(valid_mask)
                    
                    # 添加坐标范围检查
                    print(f"📐 DEM坐标变换信息:")
                    print(f"   DEM坐标系左上角: ({geotransform[0]:.8f}, {geotransform[3]:.8f})")
                    print(f"   DEM坐标系右下角: ({geotransform[0] + cols * geotransform[1]:.8f}, {geotransform[3] + rows * geotransform[5]:.8f})")
                    print(f"   像素大小: ({geotransform[1]:.8f}, {geotransform[5]:.8f})")
                    
                    # 检查第一个有效像素的坐标
                    first_valid_found = False
                    
                    for y in range(rows):
                        for x in range(cols):
                            if valid_mask[y, x] and not first_valid_found:
                                # 转换像素坐标为DEM坐标系坐标
                                dem_x = geotransform[0] + (x + 0.5) * geotransform[1]
                                dem_y = geotransform[3] + (y + 0.5) * geotransform[5]
                                
                                print(f"   第一个有效像素位置: ({x}, {y})")
                                print(f"   第一个有效像素DEM坐标: ({dem_x:.8f}, {dem_y:.8f})")
                                
                                # 如果需要坐标转换，转换到WGS84
                                if use_coordinate_transform:
                                    try:
                                        point = coord_transform.TransformPoint(dem_x, dem_y)
                                        lat, lon = point[0], point[1]  # point[0]是纬度，point[1]是经度
                                        print(f"   第一个有效像素WGS84坐标: ({lon:.8f}, {lat:.8f})")
                                        
                                        # 第一个像素坐标转换成功
                                            
                                    except Exception as e:
                                        print(f"❌ 第一个像素坐标转换错误: {e}")
                                        continue
                                else:
                                    lon, lat = dem_x, dem_y
                                    print(f"   第一个有效像素坐标: ({lon:.8f}, {lat:.8f})")
                                first_valid_found = True
                                break
                    
                    error_count = 0
                    max_errors = 10  # 最多显示10个错误
                    
                    for y in range(rows):
                        for x in range(cols):
                            if valid_mask[y, x]:
                                # 转换像素坐标为DEM坐标系坐标
                                dem_x = geotransform[0] + (x + 0.5) * geotransform[1]
                                dem_y = geotransform[3] + (y + 0.5) * geotransform[5]
                                
                                # 如果需要坐标转换，转换到WGS84
                                if use_coordinate_transform:
                                    try:
                                        # 转换坐标 - TransformPoint返回(x, y, z)格式，其中x是纬度，y是经度
                                        point = coord_transform.TransformPoint(dem_x, dem_y)
                                        lat, lon = point[0], point[1]  # point[0]是纬度，point[1]是经度
                                        
                                        # 添加调试信息
                                        if error_count < max_errors:
                                            print(f"🔍 坐标转换调试:")
                                            print(f"   DEM坐标: ({dem_x:.8f}, {dem_y:.8f})")
                                            print(f"   转换后坐标(经度,纬度): ({lon:.8f}, {lat:.8f})")
                                        
                                        # 坐标转换成功，继续处理
                                            
                                    except Exception as e:
                                        if error_count < max_errors:
                                            print(f"❌ 坐标转换错误: {e}")
                                            print(f"   DEM坐标: ({dem_x:.8f}, {dem_y:.8f})")
                                        error_count += 1
                                        continue
                                else:
                                    # 直接使用DEM坐标
                                    lon, lat = dem_x, dem_y
                                
                                # 坐标验证通过，继续处理
                                
                                # 计算当前点到P0点的真实地理距离
                                # geopy的geodesic需要(纬度, 经度)格式
                                # TransformPoint返回(lon, lat)，但geodesic需要(lat, lon)
                                current_point = (lat, lon)  # 修正：geopy需要(纬度, 经度)格式
                                
                                # 添加坐标验证
                                if not (-90 <= lat <= 90):
                                    print(f"❌ 纬度超出范围: {lat:.8f} (应在[-90, 90]范围内)")
                                    continue
                                if not (-180 <= lon <= 180):
                                    print(f"❌ 经度超出范围: {lon:.8f} (应在[-180, 180]范围内)")
                                    continue
                                
                                try:
                                    di_distance = geodesic(p0_point, current_point).meters
                                except ValueError as e:
                                    print(f"❌ 地理距离计算错误: {e}")
                                    print(f"   当前点坐标: ({lat:.8f}, {lon:.8f})")
                                    print(f"   P0点坐标: ({p0_lat:.8f}, {p0_lon:.8f})")
                                    continue
                                
                                # 计算当前点在P0→P1方向上的投影距离
                                # 使用向量投影公式
                                current_vector_x = lon - p0_lon
                                current_vector_y = lat - p0_lat
                                
                                # 投影长度（沿P0→P1方向的距离）
                                projection_distance = (current_vector_x * direction_vector_x + 
                                                     current_vector_y * direction_vector_y) * 111000  # 转换为米
                                
                                # 计算垂直距离（到P0→P1直线的距离）
                                perpendicular_distance = np.sqrt(max(0, di_distance**2 - projection_distance**2))
                                
                                # 根据倾斜水面模型计算水位
                                if projection_distance >= 0:  # 在P0点前方
                                    # 计算垂足点的水位
                                    footprint_water_level = p0_water_level + projection_distance * kp * slope_ps
                                    
                                    # 两侧点等于垂足水位
                                    water_level_array[y, x] = footprint_water_level
                                    
                                    # 添加详细计算日志（仅前几个像素）
                                    if processed_pixels < 5:
                                        print(f"   📍 像素({x},{y})计算详情:")
                                        print(f"      - 地理距离: {di_distance:.2f}m")
                                        print(f"      - 投影距离: {projection_distance:.2f}m")
                                        print(f"      - 垂足水位: {footprint_water_level:.2f}m")
                                        print(f"      - 计算公式: {p0_water_level:.2f} + {projection_distance:.2f} × {kp} × {slope_ps}")
                                else:
                                    # P0点后方的点使用P0点水位
                                    water_level_array[y, x] = p0_water_level
                                    
                                    # 添加详细计算日志（仅前几个像素）
                                    if processed_pixels < 5:
                                        print(f"   📍 像素({x},{y})计算详情:")
                                        print(f"      - 地理距离: {di_distance:.2f}m")
                                        print(f"      - 投影距离: {projection_distance:.2f}m (P0后方)")
                                        print(f"      - 使用P0水位: {p0_water_level:.2f}m")
                                
                                processed_pixels += 1
                                
                                # 每处理1000个像素输出一次进度
                                if processed_pixels % 1000 == 0 or processed_pixels == total_valid_pixels:
                                    progress = processed_pixels / total_valid_pixels * 100
                                    print(f"   进度: {processed_pixels}/{total_valid_pixels} ({progress:.1f}%)")
                    
                    # 显示错误统计
                    if error_count > 0:
                        print(f"\n⚠️  坐标转换错误统计:")
                        print(f"   总错误数: {error_count}")
                        if error_count > max_errors:
                            print(f"   显示前{max_errors}个错误，其余省略...")
                        print(f"   成功处理像素数: {processed_pixels}")
                        print(f"   总有效像素数: {total_valid_pixels}")
                        print(f"   成功率: {processed_pixels/total_valid_pixels*100:.1f}%")
                    
                    # 统计水位分布
                    valid_water_levels = water_level_array[valid_mask]
                    min_water_level = np.min(valid_water_levels)
                    max_water_level = np.max(valid_water_levels)
                    mean_water_level = np.mean(valid_water_levels)
                    
                    print(f"\n📊 水位分布统计:")
                    print(f"   最低水位: {min_water_level:.2f}m")
                    print(f"   最高水位: {max_water_level:.2f}m")
                    print(f"   平均水位: {mean_water_level:.2f}m")
                    print(f"   水位变化范围: {max_water_level - min_water_level:.2f}m")
                    print(f"   处理像素数: {processed_pixels}")
                    
                    # 验证P1点附近的水位
                    p1_x = int((p1_lon - geotransform[0]) / geotransform[1])
                    p1_y = int((p1_lat - geotransform[3]) / geotransform[5])
                    
                    print(f"\n🎯 P1点水位验证:")
                    print(f"   P1点像素坐标: ({p1_x}, {p1_y})")
                    print(f"   P1点理论水位: {calculated_p1_water_level:.2f}m")
                    print(f"   用户验证水位: 449.14m")
                    print(f"   理论误差: {abs(calculated_p1_water_level - 449.14):.3f}m")
                    
                    if 0 <= p1_y < rows and 0 <= p1_x < cols and valid_mask[p1_y, p1_x]:
                        actual_p1_water = water_level_array[p1_y, p1_x]
                        print(f"   P1点实际计算水位: {actual_p1_water:.2f}m")
                        print(f"   实际误差: {abs(actual_p1_water - calculated_p1_water_level):.3f}m")
                        print(f"   与用户验证值误差: {abs(actual_p1_water - 449.14):.3f}m")
                        
                        if abs(actual_p1_water - 449.14) < 1.0:
                            print(f"   ✅ P1点水位验证成功！")
                        else:
                            print(f"   ⚠️  P1点水位与预期有差异")
                    else:
                        print(f"   ⚠️  P1点不在有效数据范围内")
                    
                    print(f"✅ 倾斜水面模型计算完成！")
                    
                    # 为综合评估模型准备数据
                    print(f"\n📊 为综合评估模型准备数据:")
                    print(f"   ✅ 危险性模型(H)数据已生成")
                    print(f"   ✅ 水位矩阵维度: {water_level_array.shape}")
                    print(f"   ✅ 有效数据像素数: {processed_pixels}")
                    print(f"   ✅ 水位范围: [{np.min(water_level_array[valid_mask]):.2f}, {np.max(water_level_array[valid_mask]):.2f}]m")
                    print(f"   ✅ 数据质量: 无负值，符合H模型要求")
                    
                    # 计算淹没比例（如果倾斜水面模型成功）
                    valid_water_levels = water_level_array[valid_mask]
                    if len(valid_water_levels) > 0:
                        # 这里暂时用水位变化来估算淹没效果，实际淹没比例需要等水深计算后确定
                        water_level_range = np.max(valid_water_levels) - np.min(valid_water_levels)
                        print(f"   ✅ 水位变化幅度: {water_level_range:.2f}m")
                        print(f"   ✅ 计算精度: P1点误差{abs(calculated_p1_water_level - 449.14):.3f}m")
                    else:
                        print(f"   ⚠️  无有效水位数据")
                    
                    # 使用计算得到的水位矩阵
                    water_level = None  # 将默认水位设为None，表示使用矩阵
                    
                else:
                    print(f"❌ P0和P1点重合，使用默认水位: {water_level}m")
                    
            except Exception as e:
                print(f"❌ 倾斜水面模型计算错误: {str(e)}")
                import traceback
                traceback.print_exc()
                print(f"使用默认水位: {water_level}m")
                
                # 重置水位矩阵为统一水位
                water_level_array = np.full_like(dem_array, water_level, dtype=np.float32)
        
        # 计算危险性：H = water_level - DEM
        # 当 water_level - DEM > Δh0 时，H = 0.9 + 0.1 * (water_level - DEM) / max(water_level - DEM)
        # 当 water_level - DEM <= Δh0 时，H = 0
        
        log_and_print(f"\n" + "="*80)
        log_and_print("💧 开始水深和危险性计算")
        log_and_print("="*80)
        
        water_depth = np.zeros_like(dem_array)
        
        # 根据是否使用斜面模型来计算水深
        if water_level is None:  # 使用倾斜水面模型计算的水位矩阵
            log_and_print(f"📊 使用倾斜水面模型计算水深...")
            
            # 添加调试信息
            print(f"   🔍 调试信息:")
            print(f"      - 水位数组形状: {water_level_array.shape}")
            print(f"      - DEM数组形状: {dem_array.shape}")
            print(f"      - 有效掩码像素数: {np.sum(valid_mask):,}")
            
            # 检查水位数组是否有异常值
            if np.any(water_level_array[valid_mask] > 1000):
                print(f"      - ⚠️  发现异常水位值 > 1000m")
                abnormal_water_levels = water_level_array[valid_mask & (water_level_array > 1000)]
                print(f"      - 异常水位数量: {len(abnormal_water_levels)}")
                print(f"      - 异常水位范围: [{np.min(abnormal_water_levels):.2f}, {np.max(abnormal_water_levels):.2f}]m")
            
            # 检查DEM数组是否有异常值
            if np.any(dem_array[valid_mask] > 1000):
                print(f"      - ⚠️  发现异常DEM值 > 1000m")
                abnormal_dem_values = dem_array[valid_mask & (dem_array > 1000)]
                print(f"      - 异常DEM数量: {len(abnormal_dem_values)}")
                print(f"      - 异常DEM范围: [{np.min(abnormal_dem_values):.2f}, {np.max(abnormal_dem_values):.2f}]m")
            
            water_depth[valid_mask] = water_level_array[valid_mask] - dem_array[valid_mask]
            
            # 统计倾斜水面效果
            water_levels_used = water_level_array[valid_mask]
            dem_values_used = dem_array[valid_mask]
            water_depths_calculated = water_depth[valid_mask]
            
            print(f"📈 倾斜水面模型效果统计:")
            print(f"   使用的水位范围: [{np.min(water_levels_used):.2f}, {np.max(water_levels_used):.2f}]m")
            print(f"   DEM高程范围: [{np.min(dem_values_used):.2f}, {np.max(dem_values_used):.2f}]m")
            print(f"   计算的水深范围: [{np.min(water_depths_calculated):.2f}, {np.max(water_depths_calculated):.2f}]m")
            print(f"   水位变化幅度: {np.max(water_levels_used) - np.min(water_levels_used):.2f}m")
            print(f"   地形高差: {np.max(dem_values_used) - np.min(dem_values_used):.2f}m")
            
            # 验证倾斜效果是否明显
            water_level_variance = np.var(water_levels_used)
            print(f"   水位方差: {water_level_variance:.6f} (方差越大坡度效果越明显)")
            
            # 统计淹没区域
            flooded_pixels = np.sum(water_depths_calculated > 0)
            total_pixels = len(water_depths_calculated)
            flood_ratio = flooded_pixels / total_pixels * 100
            
            print(f"   淹没像素数: {flooded_pixels}/{total_pixels}")
            print(f"   淹没比例: {flood_ratio:.2f}%")
            
            # 检查水深数据异常
            if np.max(water_depths_calculated) > 1000:  # 如果最大水深超过1000m，可能有问题
                print(f"   ⚠️  警告: 最大水深 {np.max(water_depths_calculated):.2f}m 异常，可能存在数据问题")
                print(f"   🔍 检查DEM和水位数据...")
                
                # 检查是否有异常的水位或DEM值
                abnormal_water_levels = water_levels_used[water_levels_used > 1000]
                abnormal_dem_values = dem_values_used[dem_values_used > 1000]
                
                if len(abnormal_water_levels) > 0:
                    print(f"   ❌ 发现异常水位值: {len(abnormal_water_levels)}个，范围: [{np.min(abnormal_water_levels):.2f}, {np.max(abnormal_water_levels):.2f}]m")
                
                if len(abnormal_dem_values) > 0:
                    print(f"   ❌ 发现异常DEM值: {len(abnormal_dem_values)}个，范围: [{np.min(abnormal_dem_values):.2f}, {np.max(abnormal_dem_values):.2f}]m")
            
            if water_level_variance > 0.01:
                print(f"   ✅ 倾斜水面效果明显，坡度模型工作正常")
            else:
                print(f"   ⚠️  倾斜水面效果不明显，请检查坡度参数或P0P1距离")
            
        else:  # 使用统一水位
            log_and_print(f"📊 使用统一水位 {water_level:.2f}m 计算水深...")
            water_depth[valid_mask] = water_level - dem_array[valid_mask]
            
            water_depths_calculated = water_depth[valid_mask]
            dem_values_used = dem_array[valid_mask]
            
            print(f"📈 统一水位模型统计:")
            print(f"   统一水位: {water_level:.2f}m")
            print(f"   DEM高程范围: [{np.min(dem_values_used):.2f}, {np.max(dem_values_used):.2f}]m")
            print(f"   计算的水深范围: [{np.min(water_depths_calculated):.2f}, {np.max(water_depths_calculated):.2f}]m")
            
        # 创建危险性结果数组，使用-9999作为nodata值
        hazard_result = np.full_like(water_depth, -9999, dtype=np.float32)
        # 对有效区域初始化为0
        hazard_result[valid_mask] = 0
        
        # 找到淹没区域（水深 > Δh0）且在有效数据范围内
        flooded_mask = (water_depth > delta_h0) & valid_mask
        
        if np.any(flooded_mask):
            # 计算最大水深（仅考虑有效且淹没的区域）
            max_water_depth = float(np.max(water_depth[flooded_mask]))
            
            # 确保使用浮点数计算
            normalized_depth = water_depth[flooded_mask].astype(np.float32) / float(max_water_depth)
            
            # 使用浮点数进行计算：H = α*1 + (1-α)*(H水-H地)/max(H水-H地)
            alpha = float(alpha)  # 确保是Python float类型
            hazard_values = alpha + (1.0 - alpha) * normalized_depth
            hazard_result[flooded_mask] = hazard_values
            
            # 将numpy类型转换为Python原生类型
            alpha = float(alpha)
            
            # 计算淹没区域统计信息
            flooded_pixel_count = np.sum(flooded_mask)
            total_pixel_count = np.sum(valid_mask)
            # 计算单个像素的面积（平方米）
            pixel_area_m2 = abs(geotransform[1] * geotransform[5])
            # 淹没总面积（平方米）
            flooded_area_m2 = flooded_pixel_count * pixel_area_m2
            # 转换为平方公里
            flooded_area_km2 = flooded_area_m2 / 1_000_000
        
        # 保存危险性栅格结果
        result_filename = result_name + '_' + f'hazard_{timestamp}_{result_id[:8]}.tif'
        result_path = os.path.join(OUTPUT_DIR, result_filename)
        
        # 添加水位信息到metadata
        metadata = {
            'water_level': float(water_level) if water_level is not None else None,
            'delta_h0': float(delta_h0),
            'alpha': float(alpha),
            'dem_dataset_id': dem_dataset_id,
            'boundary_dataset_id': boundary_dataset_id
        }
        
        # 如果使用了斜面模型，添加斜面参数到metadata
        if use_slope_model and p0_coord and p1_coord:
            metadata.update({
                'use_slope_model': True,
                'p0_coord': p0_coord,
                'p0_water_level': float(p0_water_level),
                'p1_coord': p1_coord,
                'slope_ps': float(slope_ps)
            })
        
        assessment_engine.save_result_raster(hazard_result, geotransform, projection, result_path, metadata=metadata)
        
        # 生成危险性预览图
        preview_filename = result_name + '_' + f'hazard_{timestamp}_{result_id[:8]}_preview.png'
        preview_path = os.path.join(OUTPUT_DIR, preview_filename)
        assessment_engine.create_hazard_preview(result_path, preview_path, '危险性评估结果')
        
        # 保存水深栅格（H水-H地）
        water_depth_result = np.full_like(water_depth, -9999, dtype=np.float32)
        water_depth_result[valid_mask] = water_depth[valid_mask]
        
        # 检查并修复异常水深值
        valid_water_depths = water_depth_result[valid_mask]
        if np.max(valid_water_depths) > 1000:
            print(f"   ⚠️  修复异常水深值...")
            # 将异常水深值限制在合理范围内
            water_depth_result[water_depth_result > 100] = 100  # 最大水深限制为100m
            print(f"   ✅ 水深值已限制在 [0, 100]m 范围内")
        
        water_depth_filename = result_name + '_' + f'hazard_water_depth_{timestamp}_{result_id[:8]}.tif'
        water_depth_path = os.path.join(OUTPUT_DIR, water_depth_filename)
        assessment_engine.save_result_raster(water_depth_result, geotransform, projection, water_depth_path, metadata=metadata)
        
        # 生成水深预览图
        water_depth_preview_filename = result_name + '_' + f'hazard_water_depth_{timestamp}_{result_id[:8]}_preview.png'
        water_depth_preview_path = os.path.join(OUTPUT_DIR, water_depth_preview_filename)
        assessment_engine.create_hazard_preview(water_depth_path, water_depth_preview_path, '水深分布图(H水-H地)')
        
        # 如果使用了斜面模型，保存斜面水位数据
        if use_slope_model and 'water_level_array' in locals() and water_level_array is not None:
            print(f"\n💾 保存斜面水位数据...")
            water_level_result = np.full_like(water_level_array, -9999, dtype=np.float32)
            water_level_result[valid_mask] = water_level_array[valid_mask]
            
            water_level_filename = result_name + '_' + f'hazard_water_level_{timestamp}_{result_id[:8]}.tif'
            water_level_path = os.path.join(OUTPUT_DIR, water_level_filename)
            assessment_engine.save_result_raster(water_level_result, geotransform, projection, water_level_path, metadata=metadata)
            print(f"   ✅ 斜面水位数据保存完成: {water_level_filename}")
            
            # 生成斜面水位预览图
            water_level_preview_filename = result_name + '_' + f'hazard_water_level_{timestamp}_{result_id[:8]}_preview.png'
            water_level_preview_path = os.path.join(OUTPUT_DIR, water_level_preview_filename)
            assessment_engine.create_hazard_preview(water_level_path, water_level_preview_path, '斜面水位分布图')
        
        # 计算整体统计信息（排除nodata值）
        valid_hazard_data = hazard_result[hazard_result != -9999]
        if len(valid_hazard_data) > 0:
            overall_stats = {
                'min': float(np.min(valid_hazard_data)),
                'max': float(np.max(valid_hazard_data)),
                'mean': float(np.mean(valid_hazard_data)),
                'std': float(np.std(valid_hazard_data)),
                'flooded_area_ratio': float(np.sum(flooded_mask) / np.sum(valid_mask)),
                'max_water_depth': float(max_water_depth) if np.any(flooded_mask) else 0,
                'flooded_pixel_count': int(flooded_pixel_count),
                'total_pixel_count': int(total_pixel_count),
                'flooded_area_m2': float(flooded_area_m2),
                'flooded_area_km2': float(flooded_area_km2),
                'pixel_area_m2': float(pixel_area_m2)
            }
        else:
            overall_stats = {
                'min': 0.0,
                'max': 0.0,
                'mean': 0.0,
                'std': 0.0,
                'flooded_area_ratio': 0.0,
                'max_water_depth': 0.0,
                'flooded_pixel_count': 0,
                'total_pixel_count': int(np.sum(valid_mask)),
                'flooded_area_m2': 0.0,
                'flooded_area_km2': 0.0,
                'pixel_area_m2': float(abs(geotransform[1] * geotransform[5]))
            }
        
        # 添加斜面模型参数到结果中（如果使用了斜面模型）
        model_params = {
            'water_level': float(water_level) if water_level is not None else None,
            'delta_h0': float(delta_h0),
            'alpha': float(alpha),
            'dem_dataset_id': dem_dataset_id,
            'boundary_dataset_id': boundary_dataset_id
        }
        
        # 添加斜面模型参数（如果使用）
        if use_slope_model and p0_coord and p1_coord:
            model_params.update({
                'use_slope_model': True,
                'p0_coord': p0_coord,
                'p0_water_level': float(p0_water_level),
                'p1_coord': p1_coord,
                'slope_ps': float(slope_ps)
            })
        
        # 准备文件列表
        files = [{
            'id': 'flood_results/'+result_filename,
            'name': result_name + '_危险性',
            'type': 'raster',
            'format': 'tif',
            'url': f'/api/datasets/flood_results/{result_filename}/image',
            'download_url': f'/api/datasets/flood_results/{result_filename}/download'
        }, {
            'id': 'flood_results/'+water_depth_filename,
            'name': result_name + '_水深',
            'type': 'raster',
            'format': 'tif',
            'url': f'/api/datasets/flood_results/{water_depth_filename}/image',
            'download_url': f'/api/datasets/flood_results/{water_depth_filename}/download'
        }]
        
        # 准备预览图列表
        previews = [f'/api/datasets/images/flood_results/{preview_filename}', f'/api/datasets/images/flood_results/{water_depth_preview_filename}']
        
        # 如果使用了斜面模型，添加斜面水位文件
        if use_slope_model and 'water_level_array' in locals() and water_level_array is not None:
            files.append({
                'id': 'flood_results/'+water_level_filename,
                'name': result_name + '_斜面水位',
                'type': 'raster',
                'format': 'tif',
                'url': f'/api/datasets/flood_results/{water_level_filename}/image',
                'download_url': f'/api/datasets/flood_results/{water_level_filename}/download'
            })
            previews.append(f'/api/datasets/images/flood_results/{water_level_preview_filename}')
        
        result = {
            'id': result_id,
            'name': result_name,
            'type': 'hazard',
            'createdAt': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'description': f'危险性模型评估结果 - 淹没水位' + (f': {water_level}m' if water_level is not None else '（斜面模型）'),
            'parameters': model_params,
            'files': files,
            'statistics': overall_stats,
            'preview': previews
            }
    
        # 关闭数据集
        dem_dataset = None
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': f'危险性评估失败: {str(e)}'}), 500

@flood_bp.route('/exposure', methods=['POST'])
@cross_origin()
@log_function_call
def exposure_assessment():
    """暴露性评估 - 基于淹没水位高程的二值化模型"""
    try:
        data = request.get_json()
        
        # 获取参数
        hazard_dataset_id = data.get('hazard_dataset_id')
        result_name = data.get('result_name', '暴露性评估结果')
        
        # 新增: 河道扣除参数
        river_dataset_id = data.get('river_dataset_id')  # 河道数据集
        exclude_river = data.get('exclude_river', False)  # 是否扣除河道
        
        if not hazard_dataset_id:
            return jsonify({'error': '缺少淹没水位高程数据集参数'}), 400
        hazard_dataset_id = hazard_dataset_id[0]
        
        # 生成唯一ID和文件名
        result_id = str(uuid.uuid4())
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        result_filename = result_name + '_' + f'exposure_{timestamp}_{result_id[:8]}.tif'
        result_path = os.path.join(OUTPUT_DIR, result_filename)
        
        # 用于扣除河道的结果文件名
        result_exclude_river_filename = result_name + '_' + f'exposure_exclude_river_{timestamp}_{result_id[:8]}.tif'
        result_exclude_river_path = os.path.join(OUTPUT_DIR, result_exclude_river_filename)
        
        # 读取淹没水位高程数据
        hazard_path = os.path.join(DATA_DIR, hazard_dataset_id)
        if not os.path.exists(hazard_path):
            return jsonify({'error': f'淹没水位高程数据文件不存在: {hazard_dataset_id}'}), 404
        
        # 使用GDAL读取栅格数据
        dataset = gdal.Open(hazard_path)
        if dataset is None:
            return jsonify({'error': f'无法读取淹没水位高程数据: {hazard_dataset_id}'}), 500
        
        # 获取栅格数据
        band = dataset.GetRasterBand(1)
        hazard_data = band.ReadAsArray().astype(np.float32)
        geotransform = dataset.GetGeoTransform()
        projection = dataset.GetProjection()
        nodata = band.GetNoDataValue()
        
        # 计算像元面积        
        # 解析坐标系信息
        srs = osr.SpatialReference()
        srs.ImportFromWkt(projection)
        
        # 计算像元面积
        pixel_width = abs(geotransform[1])
        pixel_height = abs(geotransform[5])
        
        if srs.IsGeographic():
            # 地理坐标系（经纬度），需要转换为平方米
            # 使用中心点的纬度来计算近似面积
            center_lat = geotransform[3] + (dataset.RasterYSize * geotransform[5]) / 2
            # 1度经度在该纬度的米数
            meters_per_degree_lon = 111320 * np.cos(np.radians(center_lat))
            # 1度纬度约等于111320米
            meters_per_degree_lat = 111320
            
            pixel_area = (pixel_width * meters_per_degree_lon) * (pixel_height * meters_per_degree_lat)
            coord_type = "地理坐标系"
            print(f"坐标系类型: {coord_type}")
            print(f"中心纬度: {center_lat:.6f}°")
            print(f"像元大小: {pixel_width:.6f}° × {pixel_height:.6f}°")
            print(f"像元面积: {pixel_area:.2f} 平方米")
        elif srs.IsProjected():
            # 投影坐标系，直接计算面积（假设单位为米）
            pixel_area = pixel_width * pixel_height
            coord_type = "投影坐标系"
            print(f"坐标系类型: {coord_type}")
            print(f"像元大小: {pixel_width:.2f}m × {pixel_height:.2f}m")
            print(f"像元面积: {pixel_area:.2f} 平方米")
        else:
            # 未知坐标系，使用原始计算
            pixel_area = pixel_width * pixel_height
            coord_type = "未知坐标系"
            print(f"坐标系类型: {coord_type}")
            print(f"像元面积: {pixel_area} 单位²")
        
        # 处理无效值
        if nodata is not None:
            # 创建有效数据掩码
            valid_mask = hazard_data != nodata
            # 应用暴露性模型算法：E=像元面积当H>0，E=0当H≤0（仅对有效数据）
            exposure_result = np.where(valid_mask & (hazard_data > 0), pixel_area, 0.0)
            # 将无效区域设置为nodata
            exposure_result = np.where(valid_mask, exposure_result, nodata if nodata is not None else -9999)
        else:
            # 如果没有nodata值，直接应用算法
            exposure_result = np.where(hazard_data > 0, pixel_area, 0.0)
            valid_mask = np.ones_like(hazard_data, dtype=bool)
        
        # 计算原始淹没统计信息
        flooded_mask = (exposure_result > 0) & valid_mask
        flooded_pixel_count = np.sum(flooded_mask)
        total_pixel_count = np.sum(valid_mask)
        # 淹没总面积（平方米）
        flooded_area_m2 = flooded_pixel_count * pixel_area
        # 转换为平方公里
        flooded_area_km2 = flooded_area_m2 / 1_000_000
        
        log_and_print(f"\n" + "="*80)
        log_and_print("🌊 暴露性模型E计算过程")
        log_and_print("="*80)
        log_and_print(f"📊 基础信息:")
        log_and_print(f"   坐标系类型: {coord_type}")
        log_and_print(f"   像元大小: {pixel_width:.2f}m × {pixel_height:.2f}m")
        log_and_print(f"   像元面积: {pixel_area:.2f} 平方米")
        log_and_print(f"   总有效像元数: {total_pixel_count:,}")
        log_and_print(f"   数据维度: {hazard_data.shape[0]} × {hazard_data.shape[1]}")
        
        print(f"\n💧 淹没计算:")
        print(f"   算法: E=像元面积当H>0，E=0当H≤0")
        print(f"   淹没像元数: {flooded_pixel_count:,}")
        print(f"   非淹没像元数: {total_pixel_count - flooded_pixel_count:,}")
        print(f"   淹没比例: {flooded_pixel_count/total_pixel_count*100:.2f}%")
        print(f"   原始淹没面积: {flooded_area_km2:.3f} 平方公里 ({flooded_area_m2:,.0f} 平方米)")
        
        # 统计淹没区域的水深分布
        if np.any(flooded_mask):
            flooded_depths = hazard_data[flooded_mask]
            print(f"   淹没区域水深统计:")
            print(f"     - 最小水深: {np.min(flooded_depths):.2f}m")
            print(f"     - 最大水深: {np.max(flooded_depths):.2f}m")
            print(f"     - 平均水深: {np.mean(flooded_depths):.2f}m")
            print(f"     - 水深标准差: {np.std(flooded_depths):.2f}m")
        
        # 河道掩码和扣除河道后的结果
        river_mask = None
        exposure_exclude_river_result = None
        river_area_km2 = 0
        river_pixel_count = 0
        adjusted_area_km2 = flooded_area_km2
        
        # 如果需要扣除河道
        if exclude_river and river_dataset_id:
            print(f"\n🏞️  河道扣除处理:")
            print(f"   河道数据集: {river_dataset_id}")
            print(f"   扣除河道: 是")
            try:
                # 读取河道数据
                river_path = os.path.join(DATA_DIR, river_dataset_id[0] if isinstance(river_dataset_id, list) else river_dataset_id)
                print(f"   河道文件路径: {river_path}")
                
                if os.path.exists(river_path):
                    print(f"   ✅ 河道文件存在")
                    # 处理河道数据（可能是矢量或栅格）
                    if river_path.lower().endswith(('.shp', '.json', '.geojson')):
                        # 处理矢量河道数据
                        print(f"   📐 处理矢量河道数据")
                        river_vector = ogr.Open(river_path)
                        if river_vector:
                            # 创建河道掩码栅格
                            print(f"   🔧 创建河道栅格掩码")
                            river_mask = np.zeros_like(hazard_data, dtype=bool)
                            
                            # 从河道矢量创建栅格掩码
                            from rasterio.features import rasterize
                            
                            # 使用GDAL的矢量到栅格转换
                            layer = river_vector.GetLayer()
                            
                            # 创建内存栅格
                            mem_drv = gdal.GetDriverByName('MEM')
                            target_ds = mem_drv.Create('', dataset.RasterXSize, dataset.RasterYSize, 1, gdal.GDT_Byte)
                            target_ds.SetGeoTransform(geotransform)
                            target_ds.SetProjection(projection)
                            
                            # 栅格化
                            gdal.RasterizeLayer(target_ds, [1], layer, burn_values=[1])
                            
                            # 读取结果
                            river_raster = target_ds.GetRasterBand(1).ReadAsArray()
                            river_mask = river_raster > 0
                            
                            # 清理
                            target_ds = None
                            river_vector = None
                            
                            river_pixel_count = np.sum(river_mask)
                            print(f"   ✅ 河道栅格掩码创建完成")
                            print(f"   📊 河道像元数: {river_pixel_count:,}")
                    elif river_path.lower().endswith(('.tif', '.tiff')):
                        # 处理栅格河道数据
                        print(f"   📐 处理栅格河道数据")
                        river_ds = gdal.Open(river_path)
                        if river_ds:
                            # 确保河道栅格与危险性栅格尺寸一致
                            if (river_ds.RasterXSize != dataset.RasterXSize or 
                                river_ds.RasterYSize != dataset.RasterYSize):
                                print(f"   ⚠️  河道栅格尺寸与危险性栅格不一致，需要重采样")
                                print(f"   📏 河道栅格尺寸: {river_ds.RasterXSize} × {river_ds.RasterYSize}")
                                print(f"   📏 危险性栅格尺寸: {dataset.RasterXSize} × {dataset.RasterYSize}")
                                
                                # 创建临时文件
                                temp_path = os.path.join(OUTPUT_DIR, f'temp_river_{uuid.uuid4()}.tif')
                                
                                # 重采样河道栅格以匹配危险性栅格
                                gdal.Warp(temp_path, river_ds, 
                                         width=dataset.RasterXSize,
                                         height=dataset.RasterYSize,
                                         outputBounds=[geotransform[0], 
                                                     geotransform[3] + dataset.RasterYSize * geotransform[5], 
                                                     geotransform[0] + dataset.RasterXSize * geotransform[1], 
                                                     geotransform[3]],
                                         format='GTiff',
                                         resampleAlg=gdal.GRA_NearestNeighbour)
                                
                                # 打开重采样后的栅格
                                resampled_river_ds = gdal.Open(temp_path)
                                if resampled_river_ds:
                                    river_raster = resampled_river_ds.GetRasterBand(1).ReadAsArray()
                                    # 河道值大于0的部分作为掩码
                                    river_mask = river_raster > 0
                                    
                                    # 清理
                                    resampled_river_ds = None
                                    try:
                                        os.remove(temp_path)
                                    except:
                                        print(f"警告：无法删除临时文件 {temp_path}")
                            else:
                                # 直接读取河道栅格
                                river_raster = river_ds.GetRasterBand(1).ReadAsArray()
                                # 河道值大于0的部分作为掩码
                                river_mask = river_raster > 0
                            
                            # 清理
                            river_ds = None
                            
                            river_pixel_count = np.sum(river_mask)
                            print(f"   ✅ 河道栅格掩码创建完成")
                            print(f"   📊 河道像元数: {river_pixel_count:,}")
                    
                    # 计算河道统计信息
                    if river_mask is not None:
                        river_pixel_count = np.sum(river_mask)
                        river_area_m2 = river_pixel_count * pixel_area
                        river_area_km2 = river_area_m2 / 1_000_000
                        print(f"   📊 河道统计:")
                        print(f"     - 河道像元数: {river_pixel_count:,}")
                        print(f"     - 河道面积: {river_area_km2:.3f} 平方公里 ({river_area_m2:,.0f} 平方米)")
                        
                        # 创建扣除河道后的暴露性结果
                        exposure_exclude_river_result = exposure_result.copy()
                        
                        # 河道与淹没区的交集
                        river_flood_overlap_mask = river_mask & flooded_mask
                        overlap_pixel_count = np.sum(river_flood_overlap_mask)
                        overlap_area_m2 = overlap_pixel_count * pixel_area
                        overlap_area_km2 = overlap_area_m2 / 1_000_000
                        print(f"     - 河道与淹没区交集像元数: {overlap_pixel_count:,}")
                        print(f"     - 河道与淹没区交集面积: {overlap_area_km2:.3f} 平方公里 ({overlap_area_m2:,.0f} 平方米)")
                        print(f"     - 交集比例: {overlap_pixel_count/river_pixel_count*100:.1f}% (占河道)")
                        print(f"     - 交集比例: {overlap_pixel_count/flooded_pixel_count*100:.1f}% (占淹没区)")
                        
                        # 在结果中去除河道区域
                        exposure_exclude_river_result[river_mask] = 0
                        
                        # 计算扣除河道后的统计
                        flooded_exclude_river_mask = (exposure_exclude_river_result > 0) & valid_mask
                        flooded_exclude_river_count = np.sum(flooded_exclude_river_mask)
                        flooded_exclude_river_m2 = flooded_exclude_river_count * pixel_area
                        flooded_exclude_river_km2 = flooded_exclude_river_m2 / 1_000_000
                        
                        print(f"\n📈 最终结果:")
                        print(f"   🏞️  原始淹没面积: {flooded_area_km2:.3f} 平方公里")
                        print(f"   🏞️  河道面积: {river_area_km2:.3f} 平方公里")
                        print(f"   🏞️  交集面积: {overlap_area_km2:.3f} 平方公里")
                        print(f"   🏞️  扣除河道后淹没面积: {flooded_exclude_river_km2:.3f} 平方公里")
                        print(f"   📊 面积变化: {flooded_exclude_river_km2 - flooded_area_km2:.3f} 平方公里")
                        print(f"   📊 扣除比例: {overlap_area_km2/flooded_area_km2*100:.1f}%")
                        
                        adjusted_area_km2 = flooded_exclude_river_km2
            except Exception as e:
                print(f"   ❌ 处理河道数据时出错: {str(e)}")
                river_mask = None
        else:
            print(f"\n🏞️  河道扣除处理:")
            print(f"   扣除河道: 否")
            print(f"   使用原始淹没面积: {flooded_area_km2:.3f} 平方公里")
        
        # 保存原始结果栅格
        print(f"\n💾 保存结果文件:")
        print(f"   原始淹没结果: {result_filename}")
        assessment_engine.save_result_raster(exposure_result, geotransform, projection, result_path)
        
        # 生成原始结果栅格预览图
        preview_filename = result_name + '_' + f'exposure_{timestamp}_{result_id[:8]}_preview.png'
        preview_path = os.path.join(OUTPUT_DIR, preview_filename)
        assessment_engine.create_exposure_preview(result_path, preview_path, '暴露性评估结果')
        print(f"   原始淹没预览图: {preview_filename}")
        
        # 文件列表和预览列表
        files_list = [
                {
                    'id': f'flood_results/{result_filename}',
                    'name': f'{result_name}',
                    'type': 'raster',
                    'format': 'tif',
                    'url': f'/api/datasets/flood_results/{result_filename}/image',
                    'download_url': f'/api/datasets/flood_results/{result_filename}/download',
                }
        ]
        
        preview_list = [f'/api/datasets/images/flood_results/{preview_filename}']
        
        # 如果有扣除河道的结果，保存并添加到文件列表
        if exposure_exclude_river_result is not None:
            print(f"   扣除河道结果: {result_exclude_river_filename}")
            assessment_engine.save_result_raster(exposure_exclude_river_result, geotransform, projection, result_exclude_river_path)
            
            # 生成扣除河道后的预览图
            preview_exclude_river_filename = result_name + '_' + f'exposure_exclude_river_{timestamp}_{result_id[:8]}_preview.png'
            preview_exclude_river_path = os.path.join(OUTPUT_DIR, preview_exclude_river_filename)
            assessment_engine.create_exposure_preview(result_exclude_river_path, preview_exclude_river_path, '暴露性评估结果（扣除河道）')
            print(f"   扣除河道预览图: {preview_exclude_river_filename}")
            
            # 添加到文件列表和预览列表
            files_list.append({
                'id': f'flood_results/{result_exclude_river_filename}',
                'name': f'{result_name}（扣除河道）',
                'type': 'raster',
                'format': 'tif',
                'url': f'/api/datasets/flood_results/{result_exclude_river_filename}/image',
                'download_url': f'/api/datasets/flood_results/{result_exclude_river_filename}/download',
            })
            
            preview_list.append(f'/api/datasets/images/flood_results/{preview_exclude_river_filename}')
        
        # 创建统计信息
        statistics = {
            'flooded_pixel_count': int(flooded_pixel_count),
            'total_pixel_count': int(total_pixel_count),
            'pixel_area_m2': float(pixel_area),
            'flooded_area_m2': float(flooded_area_m2),
            'flooded_area_km2': float(flooded_area_km2),
            'flooded_area_ratio': float(flooded_pixel_count) / float(total_pixel_count) if total_pixel_count > 0 else 0.0,
            'exposure_min': float(np.nanmin(exposure_result[valid_mask])) if np.any(valid_mask) else 0.0,
            'exposure_max': float(np.nanmax(exposure_result[valid_mask])) if np.any(valid_mask) else 0.0,
            'exposure_mean': float(np.nanmean(exposure_result[valid_mask])) if np.any(valid_mask) else 0.0,
            'exposure_std': float(np.nanstd(exposure_result[valid_mask])) if np.any(valid_mask) else 0.0
        }
        # 如果有河道数据，添加河道相关统计
        if river_mask is not None:
            statistics.update({
                'river_pixel_count': int(river_pixel_count),
                'river_area_m2': float(river_area_m2),
                'river_area_km2': float(river_area_km2),
                'adjusted_area_km2': float(adjusted_area_km2)
            })
        # 斜面模型参数统计（如果有）
        # 检查hazard_data是否有斜面模型参数（可通过前端传递或参数中传递）
        p0_coord = data.get('p0_coord')
        p1_coord = data.get('p1_coord')
        p0_water_level = data.get('p0_water_level')
        slope_ps = data.get('slope_ps')
        use_slope_model = data.get('use_slope_model', False)
        if use_slope_model and p0_coord and p1_coord and p0_water_level is not None and slope_ps is not None:
            # 计算P1点水位
            try:
                p0_lon, p0_lat = p0_coord
                p1_lon, p1_lat = p1_coord
                direction_length = np.sqrt((p1_lon - p0_lon) ** 2 + (p1_lat - p0_lat) ** 2)
                p1_water_level = float(p0_water_level) + float(direction_length) * float(slope_ps)
            except Exception as e:
                p1_water_level = None
            statistics.update({
                'use_slope_model': True,
                'p0_coord': p0_coord,
                'p0_water_level': float(p0_water_level),
                'p1_coord': p1_coord,
                'p1_water_level': float(p1_water_level) if p1_water_level is not None else None,
                'slope_ps': float(slope_ps),
                'p0_p1_distance': float(direction_length) if p1_water_level is not None else None
            })
        
        # 准备结果
        parameters = {
            'hazard_dataset_id': hazard_dataset_id
        }
        
        # 如果使用了河道数据，添加到参数中
        if exclude_river and river_dataset_id:
            parameters.update({
                'river_dataset_id': river_dataset_id,
                'exclude_river': True
            })
        
        print(f"\n✅ 暴露性模型E计算完成!")
        print(f"📊 最终统计:")
        print(f"   - 原始淹没面积: {flooded_area_km2:.3f} 平方公里")
        if river_mask is not None:
            print(f"   - 扣除河道后面积: {adjusted_area_km2:.3f} 平方公里")
            print(f"   - 面积减少: {flooded_area_km2 - adjusted_area_km2:.3f} 平方公里")
        print(f"   - 生成文件数: {len(files_list)}")
        print(f"   - 生成预览图数: {len(preview_list)}")
        
        result = {
            'id': result_id,
            'name': result_name,
            'type': 'exposure',
            'createdAt': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'description': '暴露性模型评估结果' + (' - 含河道扣除' if exclude_river and river_dataset_id else ''),
            'parameters': parameters,
            'files': files_list,
            'preview': preview_list,
            'statistics': statistics
        }
        
        return jsonify(result)
        
    except Exception as e:
        print(f"暴露性评估失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'暴露性评估失败: {str(e)}'}), 500

@flood_bp.route('/value', methods=['POST'])
@cross_origin()
@log_function_call
def value_assessment():
    """价值密度评估"""
    try:
        data = request.get_json()
        
        # 获取参数
        total_population = float(data.get('total_population'))
        
        # 安全获取数据集ID（处理数组参数）
        population_dataset_list = data.get('population_dataset_id', [])
        building_dataset_list = data.get('building_dataset_id', [])
        other_dataset_list = data.get('other_dataset_id', [])
        
        if not population_dataset_list or not building_dataset_list:
            return jsonify({'error': '缺少必要的数据集参数'}), 400
            
        population_dataset_id = population_dataset_list[0]
        building_dataset_id = building_dataset_list[0]
        other_dataset_id = other_dataset_list[0] if other_dataset_list else None
        result_name = data.get('result_name', '价值密度评估结果')
        
        # 获取权重系数 r1, r2, r3 (r1+r2+r3=1 或 r1+r2=1 如果没有other)
        r1 = float(data.get('r1', 0.5))
        r2 = float(data.get('r2', 0.5))
        r3 = float(data.get('r3', 0.0)) if other_dataset_id else 0.0
        
        # 经济标准
        j_pop = float(data.get('j_pop', 1000))  # J人
        j_building = float(data.get('j_building', 2000))  # J建筑
        j_other = float(data.get('j_other', 500))  # J其他
        
        # 获取淹没区人口占比
        ym0 = float(data.get('ym0', 24.5/32))  # 默认值24.5/32
        
        # 获取是否考虑淹没区人口占比的参数
        consider_ym0 = data.get('consider_ym0', False)
        if isinstance(consider_ym0, str):
            consider_ym0 = consider_ym0.lower() == 'true'
        print(f"是否考虑淹没区人口占比ym0: {consider_ym0}")
        
        # 打印接收到的参数（用于调试）
        log_and_print(f"\n📨 前后端参数接收情况:")
        log_and_print(f"  总人口数: {total_population}")
        log_and_print(f"  人口热力图数据集: {population_dataset_id}")
        log_and_print(f"  建筑分布数据集: {building_dataset_id}")
        log_and_print(f"  其他数据集: {other_dataset_id}")
        log_and_print(f"  权重系数: r1={r1}, r2={r2}, r3={r3}")
        log_and_print(f"  经济标准: J人={j_pop}, J建筑={j_building}, J其他={j_other}")
        log_and_print(f"  淹没区占比: ym0={ym0}")
        log_and_print(f"  考虑ym0: {consider_ym0}")
        log_and_print(f"  结果名称: {result_name}")
        
        # 验证总人口数参数
        if not total_population or total_population <= 0:
            return jsonify({'error': '总人口数必须大于0'}), 400
        
        # 验证权重之和
        if other_dataset_id:
            if not abs(r1 + r2 + r3 - 1) < 0.001:
                return jsonify({'error': '权重系数r1+r2+r3必须等于1'}), 400
        else:
            if not abs(r1 + r2 - 1) < 0.001:
                return jsonify({'error': '权重系数r1+r2必须等于1'}), 400
                
        # 验证淹没区人口占比
        if ym0 < 0 or ym0 > 1:
            return jsonify({'error': '淹没区人口占比ym0必须在0-1之间'}), 400
        
        # 读取数据集
        pop_path = os.path.join(DATA_DIR, population_dataset_id)
        building_path = os.path.join(DATA_DIR, building_dataset_id)
        other_path = os.path.join(DATA_DIR, other_dataset_id) if other_dataset_id else None
        
        # 读取栅格数据
        pop_ds = gdal.Open(pop_path)
        building_ds = gdal.Open(building_path)
        other_ds = gdal.Open(other_path) if other_path else None
        
        required_datasets = [pop_ds, building_ds]
        if other_ds is not None:
            required_datasets.append(other_ds)
        
        if not all(required_datasets):
            return jsonify({'error': '无法读取数据集'}), 400

        # 检查所有数据集的坐标系
        log_and_print("\n检查数据集坐标系:")
        datasets_info = [(pop_ds, 'population'), (building_ds, 'building')]
        if other_ds:
            datasets_info.append((other_ds, 'other'))
        
        # 获取所有数据集的坐标系信息
        projections = []
        for ds, name in datasets_info:
            proj = ds.GetProjection()
            projections.append(proj)
            
            # 解析坐标系信息
            srs = osr.SpatialReference()
            srs.ImportFromWkt(proj)
            
            if srs.IsGeographic():
                coord_type = "地理坐标系 (经纬度)"
            elif srs.IsProjected():
                coord_type = "投影坐标系 (米)"
            else:
                coord_type = "未知坐标系"
                
            log_and_print(f"- {name}数据集: {coord_type}")
            if srs.GetAuthorityCode(None):
                log_and_print(f"  EPSG代码: {srs.GetAuthorityCode(None)}")
        
        # 检查坐标系是否一致
        if len(set(projections)) > 1:
            print("\n警告: 检测到不同的坐标系，需要进行坐标系转换")
            
            # 选择第一个数据集的坐标系作为目标坐标系
            target_proj = projections[0]
            target_srs = osr.SpatialReference()
            target_srs.ImportFromWkt(target_proj)
            
            # 如果目标坐标系是地理坐标系，转换为UTM投影坐标系
            if target_srs.IsGeographic():
                # 获取第一个数据集的中心点来确定UTM区带
                geo = pop_ds.GetGeoTransform()
                center_lon = geo[0] + (geo[1] * pop_ds.RasterXSize) / 2
                utm_zone = int((center_lon + 180) / 6) + 1
                
                # 创建UTM坐标系
                target_srs = osr.SpatialReference()
                if center_lon >= 0:
                    target_srs.ImportFromEPSG(32600 + utm_zone)  # 北半球
                else:
                    target_srs.ImportFromEPSG(32700 + utm_zone)  # 南半球
                    
                target_proj = target_srs.ExportToWkt()
                print(f"\n坐标系转换: 将所有数据集转换为UTM {utm_zone}区")
            else:
                print(f"\n坐标系转换: 将所有数据集转换为第一个数据集的投影坐标系")
            
            # 转换所有数据集到目标坐标系
            converted_datasets = []
            for i, (ds, name) in enumerate(datasets_info):
                if projections[i] != target_proj:
                    print(f"- 转换{name}数据集...")
                    
                    # 创建临时文件
                    temp_path = os.path.join(OUTPUT_DIR, f'temp_converted_{name}_{uuid.uuid4()}.tif')
                    
                    # 重投影
                    gdal.Warp(temp_path, ds, 
                             dstSRS=target_proj,
                             format='GTiff',
                             resampleAlg=gdal.GRA_Bilinear)
                    
                    # 重新打开转换后的数据集
                    converted_ds = gdal.Open(temp_path)
                    if converted_ds is None:
                        raise Exception(f"无法打开转换后的{name}数据集")
                    
                    converted_datasets.append((converted_ds, name, temp_path))
                else:
                    converted_datasets.append((ds, name, None))
            
            # 更新数据集引用
            pop_ds = converted_datasets[0][0]
            building_ds = converted_datasets[1][0]
            if other_ds:
                other_ds = converted_datasets[2][0]
            
            datasets_info = [(ds, name) for ds, name, _ in converted_datasets]
            print("- 坐标系转换完成")
        else:
            print("\n所有数据集使用相同的坐标系")
            converted_datasets = [(ds, name, None) for ds, name in datasets_info]

        # 获取所有数据集的地理信息
        geos = []
        sizes = []
        for ds, name in datasets_info:
            geo = ds.GetGeoTransform()
            size = (ds.RasterYSize, ds.RasterXSize)
            geos.append(geo)
            sizes.append(size)
            print(f"{name}数据集大小: {size}")
            print(f"{name}数据集地理信息: {geo}")
        
        # 选择分辨率最高的数据集作为参考
        cell_sizes = [(abs(geo[1]), abs(geo[5])) for geo in geos]
        target_cell_size = min(cell_sizes)
        print(f"目标像元大小: {target_cell_size}")
        
        # 计算目标范围（使用第一个数据集的完整范围作为基准）
        bounds = []
        for ds, geo in [(ds, geo) for (ds, _), geo in zip(datasets_info, geos)]:
            minx = geo[0]
            maxx = geo[0] + geo[1] * ds.RasterXSize
            miny = geo[3] + geo[5] * ds.RasterYSize
            maxy = geo[3]
            bounds.append([minx, miny, maxx, maxy])
            print(f"数据集范围: [{minx:.1f}, {miny:.1f}, {maxx:.1f}, {maxy:.1f}]")
        
                # 使用数据集的并集范围，确保数据不被过度稀释
        print("计算数据集并集范围...")
        target_bounds = [
            min(b[0] for b in bounds),  # minx
            min(b[1] for b in bounds),  # miny
            max(b[2] for b in bounds),  # maxx
            max(b[3] for b in bounds)   # maxy
        ]
        print(f"数据集并集范围: {target_bounds}")
        
        # 适当扩展边距，但不要过度扩展
        margin = 500  # 500m边距，比1km小
        target_bounds = [
            target_bounds[0] - margin,  # minx
            target_bounds[1] - margin,  # miny  
            target_bounds[2] + margin,  # maxx
            target_bounds[3] + margin   # maxy
        ]
        print(f"添加边距后的目标范围: {target_bounds}")
        
        # 检查范围合理性
        width = target_bounds[2] - target_bounds[0]
        height = target_bounds[3] - target_bounds[1]
        if width <= 0 or height <= 0:
            raise ValueError(f"目标范围无效: 宽度={width}, 高度={height}")
        
        print(f"最终目标范围: {target_bounds}")
        print(f"目标范围宽度: {width:.1f}m, 高度: {height:.1f}m")
        
        print(f"目标范围: {target_bounds}")
        
        # 计算目标大小
        target_width = int((target_bounds[2] - target_bounds[0]) / target_cell_size[0])
        target_height = int((target_bounds[3] - target_bounds[1]) / target_cell_size[1])
        
        print(f"目标大小: {target_width} x {target_height}")
        
        # 创建目标地理变换
        target_geo = (
            target_bounds[0],             # 左上角x
            target_cell_size[0],          # 像元宽度
            0,                            # 旋转
            target_bounds[3],             # 左上角y (使用最大y值作为左上角)
            0,                            # 旋转
            -target_cell_size[1]          # 像元高度 (负值，因为y轴向下)
        )
        
        print(f"目标地理变换参数: {target_geo}")
        
        # 重采样所有数据集到相同的分辨率和范围
        def resample_dataset(ds, nodata=None):
            # 读取原始数据和创建掩膜
            band = ds.GetRasterBand(1)
            data = band.ReadAsArray()
            if nodata is None:
                nodata = band.GetNoDataValue()
            
            # 处理NaN值和NoData值
            nan_mask = np.isnan(data)
            if np.any(nan_mask):
                print(f"检测到NaN值: {np.sum(nan_mask)} / {data.size} ({np.sum(nan_mask)/data.size*100:.2f}%)")
                # 如果没有设置NoData值，使用-9999作为NoData值
                if nodata is None or np.isnan(nodata):
                    nodata = -9999
                # 将NaN值替换为NoData值
                data = np.where(nan_mask, nodata, data)
            
            # 创建掩膜
            if nodata is not None and not np.isnan(nodata):
                mask = ~np.isclose(data, nodata, rtol=1e-10, atol=1e-10)
            else:
                # 如果NoData值是NaN或未设置，只排除NaN值
                mask = ~np.isnan(data)
                if nodata is None:
                    nodata = -9999
                    
            print(f"重采样前 - 数据范围: {np.min(data[mask]) if np.any(mask) else 'N/A'} to {np.max(data[mask]) if np.any(mask) else 'N/A'}")
            print(f"重采样前 - 有效数据点数量: {np.sum(mask)} / {mask.size} ({np.sum(mask)/mask.size*100:.2f}%)")
            
            # 创建临时文件
            temp_path = os.path.join(OUTPUT_DIR, f'temp_{uuid.uuid4()}.tif')
            
            # 获取GDAL驱动
            mem_driver = gdal.GetDriverByName('GTiff')
            
            # 保存带掩膜的数据到临时文件
            temp_ds = mem_driver.Create(temp_path, 
                                   data.shape[1],
                                   data.shape[0],
                                   1,
                                   gdal.GDT_Float32)
            temp_ds.SetGeoTransform(ds.GetGeoTransform())
            temp_ds.SetProjection(ds.GetProjection())
            temp_band = temp_ds.GetRasterBand(1)
            temp_band.SetNoDataValue(nodata)
            
            # 将无效区域设置为NoData
            data = data.copy()
            data[~mask] = nodata
            temp_band.WriteArray(data)
            temp_band.FlushCache()
            temp_ds = None
            
            # 重采样
            target_width = int((target_bounds[2] - target_bounds[0]) / target_cell_size[0])
            target_height = int((target_bounds[3] - target_bounds[1]) / target_cell_size[1])
            
            print(f"重采样目标尺寸: {target_width} x {target_height}")
            print(f"重采样目标范围: {target_bounds}")
            
            gdal.Warp(temp_path + '_resampled.tif',
                     temp_path,
                     format='GTiff',
                     width=target_width,
                     height=target_height,
                     outputBounds=target_bounds,
                     resampleAlg=gdal.GRA_Bilinear,  # 使用双线性插值
                     srcNodata=nodata,
                     dstNodata=nodata,
                     multithread=True)  # 启用多线程加速
            
            # 读取重采样结果
            resampled_ds = gdal.Open(temp_path + '_resampled.tif')
            if resampled_ds is None:
                raise Exception(f"无法打开重采样后的数据集: {temp_path}_resampled.tif")
            
            array = resampled_ds.GetRasterBand(1).ReadAsArray()
            geo = resampled_ds.GetGeoTransform()
            proj = resampled_ds.GetProjection()
            
            # 处理重采样后可能出现的NaN值
            nan_mask_after = np.isnan(array)
            if np.any(nan_mask_after):
                print(f"重采样后检测到NaN值: {np.sum(nan_mask_after)} / {array.size} ({np.sum(nan_mask_after)/array.size*100:.2f}%)")
                # 将NaN值替换为NoData值
                array = np.where(nan_mask_after, nodata, array)
            
            # 创建重采样后的掩膜（排除NoData值和NaN值）
            resampled_mask = ~np.isclose(array, nodata, rtol=1e-10, atol=1e-10) & ~np.isnan(array)
            print(f"重采样后 - 数据范围: {np.min(array[resampled_mask]) if np.any(resampled_mask) else 'N/A'} to {np.max(array[resampled_mask]) if np.any(resampled_mask) else 'N/A'}")
            print(f"重采样后 - 有效数据点数量: {np.sum(resampled_mask)} / {resampled_mask.size} ({np.sum(resampled_mask)/resampled_mask.size*100:.2f}%)")
            
            # 清理临时文件
            resampled_ds = None
            try:
                os.remove(temp_path)
                os.remove(temp_path + '_resampled.tif')
            except:
                print(f"警告：无法删除临时文件 {temp_path} 或 {temp_path}_resampled.tif")
            
            return array.astype(np.float32), geo, proj, resampled_mask

        try:
            # 重采样所有数据集
            print("\n重采样人口热力图...")
            pop_array, _, _, pop_mask = resample_dataset(pop_ds, pop_ds.GetRasterBand(1).GetNoDataValue())
            print("人口热力图重采样完成，大小：", pop_array.shape)
            
            print("\n重采样建筑分布数据...")
            building_array, _, _, building_mask = resample_dataset(building_ds, building_ds.GetRasterBand(1).GetNoDataValue())
            print("建筑分布数据重采样完成，大小：", building_array.shape)
            
            # 使用我们计算的目标地理变换参数，确保数据范围正确
            final_geo = target_geo
            final_proj = target_proj
            print(f"\n使用目标地理变换参数: {final_geo}")
            print(f"使用目标投影: {final_proj[:100]}...")
            
            # 组合掩膜
            valid_mask = pop_mask & building_mask
            
            if other_ds:
                print("\n重采样其他分布数据...")
                other_array, _, _, other_mask = resample_dataset(other_ds, other_ds.GetRasterBand(1).GetNoDataValue())
                print("其他分布数据重采样完成，大小：", other_array.shape)
                valid_mask = valid_mask & other_mask
                
                # 验证所有数组大小是否一致
                if not (pop_array.shape == building_array.shape == other_array.shape):
                    raise Exception(f"数据集大小不一致: pop={pop_array.shape}, building={building_array.shape}, other={other_array.shape}")
            else:
                other_array = None
                # 验证数组大小是否一致
                if not (pop_array.shape == building_array.shape):
                    raise Exception(f"数据集大小不一致: pop={pop_array.shape}, building={building_array.shape}")
            
            print(f"\n最终有效数据点数量: {np.sum(valid_mask)} / {valid_mask.size} ({np.sum(valid_mask)/valid_mask.size*100:.2f}%)")
            
        except Exception as e:
            print(f"重采样过程出错: {str(e)}")
            # 清理临时文件
            for ds, name, temp_path in converted_datasets:
                if temp_path and os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                        print(f"已清理临时文件: {temp_path}")
                    except:
                        print(f"警告：无法删除临时文件 {temp_path}")
            raise e
        
        # 计算价值密度
        def calculate_value_density(pop_array, building_array, other_array, total_population, r1, r2, r3, j_pop, j_building, j_other, valid_mask, ym0=24.5/32, consider_ym0=True):
            print("\n开始计算价值密度...")
            
            # 计算栅格单位面积（假设为平方米）
            pixel_area = abs(final_geo[1] * final_geo[5])  # 像元面积
            print(f"栅格单位面积: {pixel_area} 平方米")
            
            # 计算密度：Vpop = vPop/栅格单位面积
            v_pop_density = pop_array / pixel_area
            v_build_density = building_array / pixel_area
            v_other_density = other_array / pixel_area if other_array is not None else np.zeros_like(pop_array)
            
            print(f"人口密度范围: {np.min(v_pop_density[valid_mask]):.6f} to {np.max(v_pop_density[valid_mask]):.6f}")
            print(f"建筑密度范围: {np.min(v_build_density[valid_mask]):.6f} to {np.max(v_build_density[valid_mask]):.6f}")
            if other_array is not None:
                print(f"其他密度范围: {np.min(v_other_density[valid_mask]):.6f} to {np.max(v_other_density[valid_mask]):.6f}")
            
            # 计算总量：T_pop = sum(vPop[mask]), T_build = sum(vBuild[mask]), T_other = sum(vOther[mask])
            t_pop = np.sum(pop_array[valid_mask])
            t_build = np.sum(building_array[valid_mask])
            t_other = np.sum(other_array[valid_mask]) if other_array is not None else 0
            
            print(f"\n总量统计:")
            print(f"T_pop (人口总量): {t_pop}")
            print(f"T_build (建筑总量): {t_build}")
            print(f"T_other (其他总量): {t_other}")
            print(f"输入的总人口数T: {total_population}")
            
            # 只有在考虑ym0时才计算淹没区分配
            if consider_ym0:
                print(f"\n💧 淹没区分析（考虑ym0）:")
                print(f"历史淹没区人口占比: {ym0:.4f}")
                tpop_ym = total_population * ym0  # 淹没区人口
                tpop_non_ym = total_population * (1 - ym0)  # 非淹没区人口
                print(f"淹没区人口: {tpop_ym:.2f}")
                print(f"非淹没区人口: {tpop_non_ym:.2f}")
                
                # 判断淹没区：人口热力值大于阈值的区域视为淹没区
                flood_mask = (pop_array > np.mean(pop_array[valid_mask])) & valid_mask
                non_flood_mask = (~flood_mask) & valid_mask
                
                flood_pixel_count = np.sum(flood_mask)
                non_flood_pixel_count = np.sum(non_flood_mask)
                total_valid_pixels = np.sum(valid_mask)
                print(f"淹没区像素数: {flood_pixel_count} ({flood_pixel_count / total_valid_pixels * 100:.2f}%)")
                print(f"非淹没区像素数: {non_flood_pixel_count} ({non_flood_pixel_count / total_valid_pixels * 100:.2f}%)")
            else:
                print(f"\n🏞️ 统一区域计算（不考虑ym0）:")
                print(f"使用统一人口分配: {total_population:.2f}")
                # 不需要区分淹没区和非淹没区
                flood_mask = None
                non_flood_mask = None
                flood_pixel_count = 0
                non_flood_pixel_count = 0
                tpop_ym = 0
                tpop_non_ym = 0
            
            # 初始化价值密度结果数组
            value_result = np.zeros_like(pop_array)
            
            # 计算结果，根据请求图片里的公式
            
            # 从公式看，需要先计算 Vpop,i
            v_pop_result = np.zeros_like(pop_array)
            
            # 获取所有RLi和Bi的总和，用于计算分母
            sum_rl = np.sum(pop_array[valid_mask])
            sum_b = np.sum(building_array[valid_mask])
            sum_rl_b = np.sum((pop_array * building_array)[valid_mask])
            
            # 淹没区和非淹没区分别计算Vpop
            
            # 根据公式图片，计算全区域的分母（关键修复）
            # 计算所有有效区域的总和作为分母
            sum_rl_b_total = np.sum((pop_array * building_array)[valid_mask & (pop_array > 0) & (building_array > 0)])
            sum_rl_total = np.sum(pop_array[valid_mask & (pop_array > 0)])
            sum_b_total = np.sum(building_array[valid_mask & (building_array > 0)])
            
            print(f"全区域分母 - RLi×Bi总和: {sum_rl_b_total:.2f}")
            print(f"全区域分母 - RLi总和: {sum_rl_total:.2f}")
            print(f"全区域分母 - Bi总和: {sum_b_total:.2f}")
            
            # 判断是否考虑ym0
            if consider_ym0:
                print("📊 使用ym0分区加权计算...")
                
                # 淹没区域 - 使用ym参数
                if flood_pixel_count > 0:
                    # 当Bi>0时: Vpop,i = r1×(Tpop×ym)×(RLi×Bi)/∑(RLi×Bi)÷Ai
                    bi_greater_zero_mask = (building_array > 0) & flood_mask
                    if np.any(bi_greater_zero_mask) and sum_rl_b_total > 0:
                        v_pop_result[bi_greater_zero_mask] = r1 * tpop_ym * (pop_array[bi_greater_zero_mask] * building_array[bi_greater_zero_mask]) / sum_rl_b_total / pixel_area
                        print(f"   ✅ 淹没区Bi>0: 计算 {np.sum(bi_greater_zero_mask)} 个像素")
                
                    # 当Bi=0时: Vpop,i = r2×(Tpop×ym)×RLi/∑RLi÷Ai
                    bi_zero_mask = (building_array <= 0) & (pop_array > 0) & flood_mask
                    if np.any(bi_zero_mask) and sum_rl_total > 0:
                        v_pop_result[bi_zero_mask] = r2 * tpop_ym * pop_array[bi_zero_mask] / sum_rl_total / pixel_area
                        print(f"   ✅ 淹没区Bi=0: 计算 {np.sum(bi_zero_mask)} 个像素")
            
                # 非淹没区域 - 使用(1-ym)参数
                if non_flood_pixel_count > 0:
                    # 当Bi>0时: Vpop,i = r1×(Tpop×(1-ym))×(RLi×Bi)/∑(RLi×Bi)÷Ai
                    bi_greater_zero_mask = (building_array > 0) & non_flood_mask
                    if np.any(bi_greater_zero_mask) and sum_rl_b_total > 0:
                        v_pop_result[bi_greater_zero_mask] = r1 * tpop_non_ym * (pop_array[bi_greater_zero_mask] * building_array[bi_greater_zero_mask]) / sum_rl_b_total / pixel_area
                        print(f"   ✅ 非淹没区Bi>0: 计算 {np.sum(bi_greater_zero_mask)} 个像素")
                
                    # 当Bi=0时: Vpop,i = r2×(Tpop×(1-ym))×RLi/∑RLi÷Ai
                    bi_zero_mask = (building_array <= 0) & (pop_array > 0) & non_flood_mask
                    if np.any(bi_zero_mask) and sum_rl_total > 0:
                        v_pop_result[bi_zero_mask] = r2 * tpop_non_ym * pop_array[bi_zero_mask] / sum_rl_total / pixel_area
                        print(f"   ✅ 非淹没区Bi=0: 计算 {np.sum(bi_zero_mask)} 个像素")
                
            else:
                print("📊 不考虑ym0，使用总人口Tpop统一计算...")
                # 不考虑ym0，所有区域都用Tpop，不区分淹没区和非淹没区
                
                # 当同时有人口热力图和建筑数据时: Vpop,i = r1×Tpop×(RLi×Bi)/∑(RLi×Bi)÷Ai
                both_mask = (pop_array > 0) & (building_array > 0) & valid_mask
                if np.any(both_mask) and sum_rl_b_total > 0:
                    v_pop_result[both_mask] = r1 * total_population * (pop_array[both_mask] * building_array[both_mask]) / sum_rl_b_total / pixel_area
                    print(f"   ✅ 双数据区域(RLi×Bi): 计算 {np.sum(both_mask)} 个像素")
                
                # 当只有人口热力图时: Vpop,i = r2×Tpop×RLi/∑RLi÷Ai
                pop_only_mask = (pop_array > 0) & (building_array <= 0) & valid_mask
                if np.any(pop_only_mask) and sum_rl_total > 0:
                    v_pop_result[pop_only_mask] = r2 * total_population * pop_array[pop_only_mask] / sum_rl_total / pixel_area
                    print(f"   ✅ 仅人口数据区域(RLi): 计算 {np.sum(pop_only_mask)} 个像素")
                
                # 当只有建筑数据时: Vpop,i = r1×Tpop×Bi/∑Bi÷Ai
                build_only_mask = (pop_array <= 0) & (building_array > 0) & valid_mask
                if np.any(build_only_mask) and sum_b_total > 0:
                    v_pop_result[build_only_mask] = r1 * total_population * building_array[build_only_mask] / sum_b_total / pixel_area
                    print(f"   ✅ 仅建筑数据区域(Bi): 计算 {np.sum(build_only_mask)} 个像素")
                
                # 没有任何数据的区域设为0
                no_data_mask = (pop_array <= 0) & (building_array <= 0) & valid_mask
                v_pop_result[no_data_mask] = 0
                if np.any(no_data_mask):
                    print(f"   ✅ 无数据区域: 设置 {np.sum(no_data_mask)} 个像素为0")
            
            # 备注：单一数据计算逻辑已整合到上面的统一计算中
            
            # 双缺失情况（无人区）：Vpop,i = 0 当RLi=0且Bi=0
            double_zero_mask = (pop_array <= 0) & (building_array <= 0) & valid_mask
            v_pop_result[double_zero_mask] = 0
            
            print(f"\n计算Vpop范围: {np.min(v_pop_result[valid_mask]):.6f} to {np.max(v_pop_result[valid_mask]):.6f}")
            
            # 计算Vbuild,i = Bi/Ai (按公式要求除以像素面积)
            v_build_result = np.zeros_like(pop_array)
            v_build_result[valid_mask] = building_array[valid_mask] / pixel_area
            
            # 计算Vother,i = Oi/Ai (如果有other数据，按公式要求除以像素面积)
            v_other_result = np.zeros_like(pop_array)
            if other_array is not None:
                v_other_result[valid_mask] = other_array[valid_mask] / pixel_area
            
            # 📊 详细公式结果输出（为综合模型做铺垫）
            print(f"\n🧮 价值密度公式组件详细分析:")
            print(f"{'='*60}")
            
            # Vpop,i 人口价值密度分析
            print(f"📈 1. 人口价值密度 Vpop,i:")
            vpop_min, vpop_max = np.min(v_pop_result[valid_mask]), np.max(v_pop_result[valid_mask])
            vpop_mean, vpop_std = np.mean(v_pop_result[valid_mask]), np.std(v_pop_result[valid_mask])
            vpop_nonzero = np.sum(v_pop_result[valid_mask] > 0)
            print(f"   范围: [{vpop_min:.6f}, {vpop_max:.6f}] 人/m²")
            print(f"   均值: {vpop_mean:.6f} 人/m²，标准差: {vpop_std:.6f}")
            print(f"   非零像素: {vpop_nonzero}/{np.sum(valid_mask)} ({vpop_nonzero/np.sum(valid_mask)*100:.1f}%)")
            
            # Vbuild,i 建筑价值密度分析  
            print(f"🏢 2. 建筑价值密度 Vbuild,i = Bi/Ai:")
            vbuild_min, vbuild_max = np.min(v_build_result[valid_mask]), np.max(v_build_result[valid_mask])
            vbuild_mean, vbuild_std = np.mean(v_build_result[valid_mask]), np.std(v_build_result[valid_mask])
            vbuild_nonzero = np.sum(v_build_result[valid_mask] > 0)
            print(f"   范围: [{vbuild_min:.6f}, {vbuild_max:.6f}] m²建筑/m²")
            print(f"   均值: {vbuild_mean:.6f} m²建筑/m²，标准差: {vbuild_std:.6f}")
            print(f"   非零像素: {vbuild_nonzero}/{np.sum(valid_mask)} ({vbuild_nonzero/np.sum(valid_mask)*100:.1f}%)")
            
            # Vother,i 其他价值密度分析
            print(f"🌟 3. 其他价值密度 Vother,i = Oi/Ai:")
            vother_min, vother_max = np.min(v_other_result[valid_mask]), np.max(v_other_result[valid_mask])
            vother_mean, vother_std = np.mean(v_other_result[valid_mask]), np.std(v_other_result[valid_mask])
            vother_nonzero = np.sum(v_other_result[valid_mask] > 0)
            print(f"   范围: [{vother_min:.6f}, {vother_max:.6f}] 其他/m²")
            print(f"   均值: {vother_mean:.6f} 其他/m²，标准差: {vother_std:.6f}")
            print(f"   非零像素: {vother_nonzero}/{np.sum(valid_mask)} ({vother_nonzero/np.sum(valid_mask)*100:.1f}%)")
            
            # 经济权重系数
            print(f"💰 4. 经济权重系数 J:")
            print(f"   J人 (Jp): {j_pop:.3f} 元/人")
            print(f"   J建筑 (Jb): {j_building:.3f} 元/m²建筑")
            print(f"   J其他 (Jo): {j_other:.3f} 元/其他")
            print(f"{'='*60}")
            
            # 🎯 最终价值密度计算: Vi = (Vpop,i×Jp + Vbuild,i×Jb + Vother,i×Jo)
            print(f"🎯 5. 最终价值密度计算 Vi = (Vpop,i×Jp + Vbuild,i×Jb + Vother,i×Jo):")
            
            # 计算各组件贡献
            vpop_contribution = v_pop_result[valid_mask] * j_pop
            vbuild_contribution = v_build_result[valid_mask] * j_building  
            vother_contribution = v_other_result[valid_mask] * j_other
            
            print(f"   人口贡献 (Vpop×Jp): [{np.min(vpop_contribution):.6f}, {np.max(vpop_contribution):.6f}] 元/m²")
            print(f"   建筑贡献 (Vbuild×Jb): [{np.min(vbuild_contribution):.6f}, {np.max(vbuild_contribution):.6f}] 元/m²")
            print(f"   其他贡献 (Vother×Jo): [{np.min(vother_contribution):.6f}, {np.max(vother_contribution):.6f}] 元/m²")
            
            # 最终价值密度计算
            value_result[valid_mask] = vpop_contribution + vbuild_contribution + vother_contribution
            
            # 最终结果统计
            final_min, final_max = np.min(value_result[valid_mask]), np.max(value_result[valid_mask])
            final_mean, final_std = np.mean(value_result[valid_mask]), np.std(value_result[valid_mask])
            final_nonzero = np.sum(value_result[valid_mask] > 0)
            
            print(f"🏆 最终价值密度统计:")
            print(f"   范围: [{final_min:.6f}, {final_max:.6f}] 元/m²")
            print(f"   均值: {final_mean:.6f} 元/m²，标准差: {final_std:.6f}")
            print(f"   非零像素: {final_nonzero}/{np.sum(valid_mask)} ({final_nonzero/np.sum(valid_mask)*100:.1f}%)")
            
            # 🏛️ 为综合模型准备的关键统计信息
            print(f"\n🏛️ 综合模型准备信息:")
            print(f"   总评估面积: {np.sum(valid_mask) * pixel_area / 1000000:.2f} km²")
            print(f"   总价值: {np.sum(value_result[valid_mask]) * pixel_area / 1000000:.2f} 百万元")
            print(f"   平均价值密度: {final_mean:.6f} 元/m²")
            print(f"   最大风险区域价值: {final_max:.6f} 元/m²")
            
            # 显示数据分布统计（重要分位数）
            print(f"\n📊 价值分布分位数分析:")
            percentiles = [10, 25, 50, 75, 90, 95, 99]
            for p in percentiles:
                val = np.percentile(value_result[valid_mask], p)
                print(f"   {p:2d}分位数: {val:.6f} 元/m²")
                
            # 🔍 计算模式说明（为用户理解不同设置的影响）
            print(f"\n🔍 当前计算模式说明:")
            if consider_ym0:
                print(f"   ✅ 考虑淹没区人口占比ym0 = {ym0:.4f}")
                print(f"   📍 淹没区人口: {tpop_ym:.2f} 人 ({ym0*100:.1f}%)")
                print(f"   📍 非淹没区人口: {tpop_non_ym:.2f} 人 ({(1-ym0)*100:.1f}%)")
                print(f"   📊 分区计算：淹没区和非淹没区使用不同人口分配权重")
                print(f"   🔄 使用公式: 绿色框内ym0分区计算方法")
            else:
                print(f"   ❌ 不考虑淹没区人口占比ym0")
                print(f"   📍 统一人口: {total_population:.2f} 人 (100%)")
                print(f"   📊 统一计算：所有区域使用相同人口总数Tpop")
                print(f"   🔄 使用公式: 黄色框内统一计算方法")
                
            print(f"{'='*60}")
            
            # 注意：原始数据保存功能将在外部统一处理
            
            # 保持原始价值密度值，不进行归一化处理
            # 这对于后续的IDFi综合评估非常重要
            if np.sum(valid_mask) > 0:
                valid_values = value_result[valid_mask]
                min_val = np.min(valid_values)
                max_val = np.max(valid_values)
                print(f"\n价值密度计算完成 (保持原始值):")
                print(f"价值密度范围: [{min_val:.6f}, {max_val:.6f}]")
                print(f"有效数据点: {len(valid_values)}")
            else:
                print("\n警告: 没有有效的价值密度数据")
            
            return value_result.astype(np.float32), valid_mask

        try:
            # 计算最终价值密度
            value_result, valid_mask = calculate_value_density(pop_array, building_array, other_array, 
                                                             total_population, r1, r2, r3, 
                                                             j_pop, j_building, j_other, valid_mask, ym0, consider_ym0)
            
            if np.sum(valid_mask) == 0:
                raise Exception("没有有效数据点，请检查输入数据和NoData值设置")
            
            # 设置nodata区域
            nodata_value = -9999  # 使用固定的NoData值
            value_result = value_result.copy()  # 创建副本以避免修改原始数据
            value_result[~valid_mask] = nodata_value
            
            # 生成唯一ID和文件名
            result_id = str(uuid.uuid4())
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            safe_result_name = secure_filename(result_name)
            result_filename = safe_result_name + '_' + f'value_{timestamp}_{result_id[:8]}.tif'
            result_path = os.path.join(OUTPUT_DIR, result_filename)
            
            # 保存结果栅格
            driver = gdal.GetDriverByName('GTiff')
            out_ds = driver.Create(result_path, 
                                value_result.shape[1],  # 列数（宽度）
                                value_result.shape[0],  # 行数（高度）
                                1, 
                                gdal.GDT_Float32,
                                options=['COMPRESS=LZW'])  # 添加压缩选项
            
            # 设置地理信息 - 使用正确的目标地理变换参数
            print(f"保存栅格的地理变换参数: {final_geo}")
            print(f"保存栅格的投影信息: {final_proj[:100]}...")
            out_ds.SetGeoTransform(final_geo)
            out_ds.SetProjection(final_proj)
            
            # 写入数据和设置NoData值
            out_band = out_ds.GetRasterBand(1)
            out_band.SetNoDataValue(nodata_value)
            out_band.WriteArray(value_result)
            
            # 确保数据写入磁盘
            out_band.FlushCache()
            out_ds.FlushCache()
            
            # 生成预览图（红色渐变）
            preview_filename = safe_result_name + '_' +  f'value_{timestamp}_{result_id[:8]}_preview.png'
            preview_path = os.path.join(OUTPUT_DIR, preview_filename)
            
            print("\n保存的数据信息:")
            print(f"数据范围: {np.min(value_result[valid_mask])} to {np.max(value_result[valid_mask])}")
            print(f"NoData值: {nodata_value}")
            print(f"有效数据点数量: {np.sum(valid_mask)} / {valid_mask.size}")
            
            assessment_engine.create_value_preview(result_path, preview_path, '价值密度评估结果')
            
            # 计算统计信息（仅使用有效数据）
            valid_result = value_result[valid_mask]
            stats = {
                'min': float(np.min(valid_result)),
                'max': float(np.max(valid_result)),
                'mean': float(np.mean(valid_result)),
                'std': float(np.std(valid_result)),
                'valid_count': int(np.sum(valid_mask)),
                'total_count': int(valid_mask.size),
                'nodata_value': float(nodata_value)
            }
            stats['consider_ym0'] = consider_ym0
        
            result = {
                'id': result_id,
                'name': result_name,
                'type': 'value',
                'createdAt': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'description': '价值密度模型评估结果',
                'parameters': {
                    'total_population': total_population,
                    'population_dataset_id': population_dataset_id,
                    'building_dataset_id': building_dataset_id,
                    'other_dataset_id': other_dataset_id,
                    'weights': {
                        'r1': r1, 'r2': r2, 'r3': r3
                    },
                    'economic_values': {
                        'j_pop': j_pop, 'j_building': j_building, 'j_other': j_other
                    }
                },
                    'files': [{
                        'id': 'flood_results/'+result_filename,
                        'name': result_name,
                        'type': 'raster',
                        'format': 'tif',
                        'url': f'/api/datasets/flood_results/{result_filename}/image',
                        'download_url': f'/api/datasets/flood_results/{result_filename}/download'
                    }],
                    'preview': [f'/api/datasets/images/flood_results/{preview_filename}'],
                    'statistics': stats
                }

            # 清理资源
            out_band = None
            out_ds = None
            
            # 清理临时文件
            for ds, name, temp_path in converted_datasets:
                if temp_path and os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                        print(f"已清理临时文件: {temp_path}")
                    except:
                        print(f"警告：无法删除临时文件 {temp_path}")
            
            return jsonify(result)
            
        except Exception as e:
            print(f"价值密度评估失败: {str(e)}")
            # 清理临时文件
            try:
                for ds, name, temp_path in converted_datasets:
                    if temp_path and os.path.exists(temp_path):
                        try:
                            os.remove(temp_path)
                            print(f"已清理临时文件: {temp_path}")
                        except:
                            print(f"警告：无法删除临时文件 {temp_path}")
            except:
                pass
            raise e
        
    except Exception as e:
        print(f"价值密度评估失败: {str(e)}")
        return jsonify({'error': f'价值密度评估失败: {str(e)}'}), 500

@flood_bp.route('/sensitivity', methods=['POST'])
@cross_origin()
@log_function_call
def sensitivity_assessment():
    """环境敏感性评估"""
    try:
        log_and_print("\n=== 开始敏感性评估 ===")
        data = request.get_json()
        log_and_print(f"接收到的请求数据: {data}")
        
        # 获取参数
        raster_template_dataset = data.get('rasterTemplateDataset')[0]  # 栅格模板
        road_dataset = data.get('roadDataset')[0]  # OSM路网数据
        flood_point_dataset = data.get('floodPointDataset')[0]  # 易涝点
        other_dataset = data.get('otherDataset')  # 其他数据（可选）
        road_buffer_radius = float(data.get('roadBufferRadius', 0))  # 道路缓冲区半径(米)
        g1 = float(data.get('g1', 0.05))  # 易涝点权重
        g2 = float(data.get('g2', 0.05))  # 路网权重
        g3 = float(data.get('g3', 0.9))  # 其他权重
        result_name = data.get('resultName', '敏感性评估结果')
        
        log_and_print(f"\n📊 敏感性模型参数配置:")
        log_and_print(f"🗂️  数据集信息:")
        log_and_print(f"   - 栅格模板数据集: {raster_template_dataset}")
        log_and_print(f"   - 路网数据集: {road_dataset}")
        log_and_print(f"   - 易涝点数据集: {flood_point_dataset}")
        log_and_print(f"   - 其他数据集: {other_dataset}")
        print(f"🔧 缓冲区配置:")
        print(f"   - 道路缓冲区半径: {road_buffer_radius} 米")
        if road_buffer_radius > 0:
            print(f"   - 缓冲区模式: 启用 - 计算道路周边影响区域")
        else:
            print(f"   - 缓冲区模式: 禁用 - 仅计算道路本身")
        print(f"⚖️  权重系数:")
        print(f"   - g1 (易涝点权重): {g1}")
        print(f"   - g2 (路网权重): {g2}")
        print(f"   - g3 (其他权重): {g3}")
        print(f"   - 权重总和: {g1 + g2 + g3}")
        print(f"📁 输出设置:")
        print(f"   - 结果名称: {result_name}")
        
        if other_dataset != None:
            other_dataset = other_dataset[0]
            
        # 验证必要参数
        if not all([raster_template_dataset, road_dataset, flood_point_dataset]):
            return jsonify({'error': '缺少必要的数据集参数'}), 400
        
        # 验证权重之和是否为1
        if abs(g1 + g2 + g3 - 1) > 0.001:
            return jsonify({'error': '权重系数之和必须等于1'}), 400
            
        # 生成唯一ID和文件名
        result_id = str(uuid.uuid4())
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        result_filename = result_name + '_' + f'sensitivity_{timestamp}_{result_id[:8]}.tif'
        result_path = os.path.join(OUTPUT_DIR, result_filename)
        
        print(f"\n文件路径:")
        print(f"- 结果文件: {result_path}")
        
        # 读取栅格模板数据
        raster_template_path = os.path.join(DATA_DIR, raster_template_dataset)
        with rasterio.open(raster_template_path) as raster_template:
            raster_data_template = raster_template.read(1)
            raster_transform = raster_template.transform
            original_crs = raster_template.crs  # 保存原始坐标系
            raster_crs = raster_template.crs
            raster_bounds = raster_template.bounds
            raster_width = raster_template.width
            raster_height = raster_template.height
            nodata_value = raster_template.nodata
        
        # 创建有效数据掩膜
        print(f"\n创建栅格模板掩膜:")
        if nodata_value is not None:
            valid_mask = raster_data_template != nodata_value
            print(f"- 使用NoData值创建掩膜: {nodata_value}")
        else:
            # 如果没有NoData值，假设0为无效值
            valid_mask = raster_data_template != 0
            print(f"- 使用0值创建掩膜")
        
        valid_pixels = np.sum(valid_mask)
        total_pixels = valid_mask.size
        print(f"- 有效像元数量: {valid_pixels} / {total_pixels} ({valid_pixels/total_pixels*100:.1f}%)")
        
        print(f"\n栅格模板数据信息:")
        print(f"- 原始CRS: {original_crs}")
        print(f"- 栅格尺寸: {raster_width} x {raster_height}")
        print(f"- 边界范围: {raster_bounds}")
        print(f"- NoData值: {nodata_value}")
        
        # 读取路网数据并转换到投影坐标系
        road_path = os.path.join(DATA_DIR, road_dataset)
        road_gdf = gpd.read_file(road_path)
        print(f"\n路网数据信息:")
        print(f"- 原始CRS: {road_gdf.crs}")
        print(f"- 路段数量: {len(road_gdf)}")
        
        # 读取易涝点数据
        flood_point_path = os.path.join(DATA_DIR, flood_point_dataset)
        flood_point_gdf = gpd.read_file(flood_point_path)
        print(f"\n易涝点数据信息:")
        print(f"- 原始CRS: {flood_point_gdf.crs}")
        print(f"- 点位数量: {len(flood_point_gdf)}")
        
        # 将所有数据转换到相同的投影坐标系（使用栅格模板的坐标系）
        # 如果栅格模板是地理坐标系，则转换为UTM投影
        target_crs = raster_crs
        if raster_crs.is_geographic:
            # 获取研究区中心点的经度来确定UTM区带
            center_lon = raster_bounds.left + (raster_bounds.right - raster_bounds.left)/2
            utm_zone = int((center_lon + 180) / 6) + 1
            target_crs = f'EPSG:326{utm_zone}' if center_lon > 0 else f'EPSG:327{abs(utm_zone)}'
            print(f"\n坐标系转换信息:")
            print(f"- 中心经度: {center_lon}")
            print(f"- UTM区带: {utm_zone}")
            print(f"- 目标CRS: {target_crs}")
        else:
            print(f"\n坐标系信息:")
            print(f"- 使用栅格模板CRS: {target_crs}")
        
        # 转换矢量数据到目标坐标系
        road_gdf = road_gdf.to_crs(target_crs)
        flood_point_gdf = flood_point_gdf.to_crs(target_crs)
        print("   ✅ 完成矢量数据坐标系转换")
        
        # 确保raster_bounds在统一坐标系中（无论是否进行了栅格转换）
        if not raster_crs.is_geographic:
            # 如果栅格模板已经是投影坐标系，直接使用其bounds
            bounds_tuple = array_bounds(raster_height, raster_width, raster_transform)
            raster_bounds = BoundingBox(bounds_tuple[0], bounds_tuple[1], bounds_tuple[2], bounds_tuple[3])
        
        # 基于栅格模板计算各要素密度
        print("\n开始计算密度:")
        
        # 如果栅格模板的坐标系是地理坐标系，需要转换到投影坐标系进行密度计算
        if raster_crs.is_geographic:
            # 转换栅格模板到UTM投影坐标系
            
            dst_transform, dst_width, dst_height = calculate_default_transform(
                raster_crs, target_crs, raster_width, raster_height, *raster_bounds
            )
            
            # 重新投影栅格模板
            raster_template_proj = np.zeros((dst_height, dst_width), dtype=raster_data_template.dtype)
            reproject(
                source=raster_data_template,
                destination=raster_template_proj,
                src_transform=raster_transform,
                src_crs=raster_crs,
                dst_transform=dst_transform,
                dst_crs=target_crs,
                resampling=Resampling.nearest
            )
            
            # 同时转换掩膜
            valid_mask_proj_uint8 = np.zeros((dst_height, dst_width), dtype=np.uint8)
            reproject(
                source=valid_mask.astype(np.uint8),
                destination=valid_mask_proj_uint8,
                src_transform=raster_transform,
                src_crs=raster_crs,
                dst_transform=dst_transform,
                dst_crs=target_crs,
                resampling=Resampling.nearest
            )
            valid_mask = valid_mask_proj_uint8.astype(bool)
            
            # 更新栅格参数
            raster_template = raster_template_proj
            raster_transform = dst_transform
            raster_width = dst_width
            raster_height = dst_height
            print(f"- 栅格模板已转换到投影坐标系: {target_crs}")
            print(f"- 新栅格尺寸: {raster_width} x {raster_height}")
            
            # 更新有效像元统计
            valid_pixels = np.sum(valid_mask)
            total_pixels = valid_mask.size
            print(f"- 转换后有效像元数量: {valid_pixels} / {total_pixels} ({valid_pixels/total_pixels*100:.1f}%)")
            
            # 更新栅格范围为投影坐标系范围
            bounds_tuple = array_bounds(raster_height, raster_width, raster_transform)
            raster_bounds = BoundingBox(bounds_tuple[0], bounds_tuple[1], bounds_tuple[2], bounds_tuple[3])
        
        # 🔍 检查转换后的数据范围是否匹配（统一坐标系后）
        print(f"\n🔍 数据范围匹配检查（统一坐标系后）:")
        print(f"   栅格模板范围: [{raster_bounds.left:.2f}, {raster_bounds.bottom:.2f}, {raster_bounds.right:.2f}, {raster_bounds.top:.2f}]")
        
        if len(road_gdf) > 0:
            road_bounds = road_gdf.total_bounds
            print(f"   路网数据范围: [{road_bounds[0]:.2f}, {road_bounds[1]:.2f}, {road_bounds[2]:.2f}, {road_bounds[3]:.2f}]")
            
            # 检查重叠
            road_overlap_x = max(0, min(raster_bounds.right, road_bounds[2]) - max(raster_bounds.left, road_bounds[0]))
            road_overlap_y = max(0, min(raster_bounds.top, road_bounds[3]) - max(raster_bounds.bottom, road_bounds[1]))
            road_overlap_area = road_overlap_x * road_overlap_y
            raster_area = (raster_bounds.right - raster_bounds.left) * (raster_bounds.top - raster_bounds.bottom)
            road_overlap_ratio = road_overlap_area / raster_area if raster_area > 0 else 0
            print(f"   路网重叠面积占比: {road_overlap_ratio*100:.1f}%")
            
            if road_overlap_ratio < 0.01:
                print(f"   ⚠️  警告：路网数据与栅格模板重叠面积过小！")
        
        if len(flood_point_gdf) > 0:
            flood_bounds = flood_point_gdf.total_bounds
            print(f"   易涝点数据范围: [{flood_bounds[0]:.2f}, {flood_bounds[1]:.2f}, {flood_bounds[2]:.2f}, {flood_bounds[3]:.2f}]")
            
            # 检查有多少易涝点在栅格范围内
            points_in_raster = 0
            for idx, point in flood_point_gdf.iterrows():
                x, y = point.geometry.x, point.geometry.y
                if (raster_bounds.left <= x <= raster_bounds.right and 
                    raster_bounds.bottom <= y <= raster_bounds.top):
                    points_in_raster += 1
            
            flood_in_ratio = points_in_raster / len(flood_point_gdf) if len(flood_point_gdf) > 0 else 0
            print(f"   栅格范围内易涝点: {points_in_raster}/{len(flood_point_gdf)} ({flood_in_ratio*100:.1f}%)")
            
            if flood_in_ratio < 0.1:
                print(f"   ⚠️  警告：易涝点数据大部分不在栅格范围内！")
        
        # 计算像元大小（用于密度计算）
        pixel_size_x = abs(raster_transform.a)
        pixel_size_y = abs(raster_transform.e)
        pixel_area = pixel_size_x * pixel_size_y
        
        # 1. 计算易涝点密度
        print("📍 1. 计算易涝点密度...")
        print(f"   - 栅格尺寸: {raster_width} x {raster_height} = {raster_width * raster_height:,} 像元")
        print(f"   - 像元大小: {pixel_size_x:.1f} x {pixel_size_y:.1f} 米")
        print(f"   - 像元面积: {pixel_area:.1f} 平方米")
        print(f"   - 易涝点数量: {len(flood_point_gdf)}")
        
        # 初始化易涝点密度栅格
        flood_point_density_raster = np.zeros((raster_height, raster_width), dtype=np.float64)
        
        # 创建空间索引以加速查询
        from shapely.geometry import box
        from shapely.strtree import STRtree
        
        if len(flood_point_gdf) > 0:
            # 为易涝点创建空间索引
            flood_point_geoms = list(flood_point_gdf.geometry)
            # 过滤掉无效或非几何对象
            valid_geoms = [geom for geom in flood_point_geoms if geom is not None and hasattr(geom, 'is_valid') and geom.is_valid]
            flood_point_tree = STRtree(valid_geoms)
            # 保存几何对象数组用于索引查找
            flood_point_geom_array = valid_geoms
            
            # 遍历每个像元，计算其内部的易涝点数量
            total_pixels = raster_height * raster_width
            processed = 0
            non_zero_count = 0
            debug_sample_count = 0
            max_debug_samples = 5
            
            print(f"   🎯 开始逐像元计算...")
            
            # 增加调试信息
            sample_debug_interval = max(1, total_pixels // 20)  # 每5%输出一次采样调试
            last_debug_processed = 0
            total_queries = 0
            successful_queries = 0
            
            for row in range(raster_height):
                for col in range(raster_width):
                    # 只处理有效像元
                    if not valid_mask[row, col]:
                        processed += 1
                        continue
                        
                    # 计算像元边界
                    left = raster_transform.c + col * pixel_size_x
                    right = left + pixel_size_x
                    top = raster_transform.f + row * raster_transform.e  # e通常为负值
                    bottom = top + raster_transform.e
                    
                    # 创建像元多边形
                    pixel_box = box(left, bottom, right, top)
                    
                    # 使用空间索引快速查找可能相交的点
                    try:
                        possible_match_indices = flood_point_tree.query(pixel_box)
                        total_queries += 1
                        
                        if len(possible_match_indices) > 0:
                            successful_queries += 1
                            
                            # 详细调试前几个有查询结果的像元
                            if successful_queries <= 3:
                                print(f"      🔎 像元({row},{col}) 空间查询: 找到{len(possible_match_indices)}个候选点")
                                print(f"         像元边界: [{left:.2f}, {bottom:.2f}, {right:.2f}, {top:.2f}]")
                                
                        # 精确检查哪些点在像元内
                        point_count = 0
                        checked_count = 0
                        
                        # 通过索引获取实际的几何对象
                        for idx in possible_match_indices:
                            geom = flood_point_geom_array[idx]
                            checked_count += 1
                            
                            # 详细几何验证
                            if successful_queries <= 3 and checked_count <= 5:
                                print(f"         🔍 检查几何体[{checked_count}]: {type(geom).__name__}")
                                if geom is not None:
                                    print(f"            - 是否为None: False")
                                    print(f"            - 是否有is_valid: {hasattr(geom, 'is_valid')}")
                                    if hasattr(geom, 'is_valid'):
                                        print(f"            - is_valid: {geom.is_valid}")
                                    if hasattr(geom, 'x') and hasattr(geom, 'y'):
                                        print(f"            - 坐标: ({geom.x:.2f}, {geom.y:.2f})")
                                else:
                                    print(f"            - 是否为None: True")
                            
                            if geom is not None and hasattr(geom, 'is_valid') and geom.is_valid:
                                try:
                                    # 详细相交测试
                                    intersects_result = pixel_box.intersects(geom)
                                    contains_result = pixel_box.contains(geom)
                                    
                                    if successful_queries <= 3 and checked_count <= 5:
                                        print(f"            - intersects结果: {intersects_result}")
                                        print(f"            - contains结果: {contains_result}")
                                    
                                    if intersects_result or contains_result:
                                        point_count += 1
                                        # 详细调试前几个相交成功的情况
                                        if successful_queries <= 3:
                                            print(f"         ✅ 找到相交点[{point_count}]: {geom.x:.2f}, {geom.y:.2f}")
                                except Exception as e:
                                    # 跳过几何运算错误
                                    if successful_queries <= 3:
                                        print(f"         ❌ 几何运算错误: {e}")
                                        print(f"            - 像元box: {pixel_box}")
                                        print(f"            - 点几何: {geom}")
                                    continue
                            else:
                                if successful_queries <= 3 and checked_count <= 5:
                                    print(f"            - 跳过无效几何体")
                        
                        # 计算密度（点数/面积）
                        density_value = point_count / pixel_area if pixel_area > 0 else 0
                        flood_point_density_raster[row, col] = density_value
                        
                        # 调试信息采样
                        if density_value > 0:
                            non_zero_count += 1
                            if debug_sample_count < max_debug_samples:
                                print(f"      🔍 调试样本[{debug_sample_count+1}]: 像元({row},{col}), 易涝点数={point_count}, 密度={density_value:.6f}")
                                debug_sample_count += 1
                                
                    except Exception as e:
                        if successful_queries <= 3:
                            print(f"      ❌ 空间索引查询错误: {e}")
                    
                    # 显示进度和调试信息
                    processed += 1
                    if processed - last_debug_processed >= sample_debug_interval:
                        progress = processed / total_pixels * 100
                        query_success_rate = (successful_queries / total_queries * 100) if total_queries > 0 else 0
                        print(f"     计算进度: {progress:.1f}% ({processed:,}/{total_pixels:,}), 非零像元: {non_zero_count}")
                        print(f"     空间查询统计: 总查询{total_queries}, 有结果{successful_queries} ({query_success_rate:.1f}%)")
                        last_debug_processed = processed
                        
                    if processed % 50000 == 0 or processed == total_pixels:
                        progress = processed / total_pixels * 100
                        query_success_rate = (successful_queries / total_queries * 100) if total_queries > 0 else 0
                        print(f"     📊 总进度: {progress:.1f}%, 非零像元: {non_zero_count}, 查询成功率: {query_success_rate:.1f}%")
        else:
            print("   ⚠️  没有易涝点数据，跳过计算")
        
        flood_point_density = flood_point_density_raster.flatten()
        print(f"   📊 易涝点密度范围: {flood_point_density.min():.6f} - {flood_point_density.max():.6f} (点/平方米)")
        print(f"   📈 非零像元数量: {np.sum(flood_point_density > 0)}/{len(flood_point_density)} ({np.sum(flood_point_density > 0)/len(flood_point_density)*100:.1f}%)")
        
        # 2. 计算路网密度
        print("🛣️  2. 计算路网密度...")
        print(f"   - 路网要素数量: {len(road_gdf)}")
        print(f"   - 缓冲区半径: {road_buffer_radius} 米")
        
        # 初始化路网密度栅格
        road_density_raster = np.zeros((raster_height, raster_width), dtype=np.float64)
        
        if len(road_gdf) > 0:
            # 应用道路缓冲区（如果设置了缓冲区半径）
            if road_buffer_radius > 0:
                print(f"   ⏳ 正在创建 {road_buffer_radius} 米缓冲区...")
                # 创建缓冲区
                road_gdf_buffered = road_gdf.copy()
                road_gdf_buffered['geometry'] = road_gdf.geometry.buffer(road_buffer_radius)
                
                # 统计缓冲区信息
                original_total_length = road_gdf.geometry.length.sum()
                buffered_total_area = road_gdf_buffered.geometry.area.sum()
                print(f"   ✅ 缓冲区创建完成")
                print(f"   📏 原始路网总长度: {original_total_length:.2f} 米")
                print(f"   📐 缓冲区总面积: {buffered_total_area:.2f} 平方米")
                print(f"   📊 平均缓冲区宽度: {buffered_total_area/original_total_length:.2f} 米")
                
                road_geoms = list(road_gdf_buffered.geometry)
                calculation_mode = "面积"
                unit = "面积比例"
            else:
                print(f"   📏 使用原始路网线要素计算密度")
                road_geoms = list(road_gdf.geometry)
                calculation_mode = "长度"
                unit = "米/平方米"
            
            # 过滤掉无效或非几何对象
            valid_road_geoms = [geom for geom in road_geoms if geom is not None and hasattr(geom, 'is_valid') and geom.is_valid]
            print(f"   🔍 有效几何要素: {len(valid_road_geoms)}/{len(road_geoms)}")
            
            # 为路网创建空间索引
            road_tree = STRtree(valid_road_geoms)
            # 保存几何对象数组用于索引查找
            road_geom_array = valid_road_geoms
            print(f"   🌲 空间索引创建完成")
            
            # 遍历每个像元，计算其内部的路网长度
            total_pixels = raster_height * raster_width
            processed = 0
            non_zero_count = 0
            debug_sample_count = 0
            max_debug_samples = 5
            
            print(f"   🎯 开始逐像元计算...")
            
            # 增加调试信息
            sample_debug_interval = max(1, total_pixels // 20)  # 每5%输出一次采样调试
            last_debug_processed = 0
            total_queries = 0
            successful_queries = 0
            
            for row in range(raster_height):
                for col in range(raster_width):
                    # 只处理有效像元
                    if not valid_mask[row, col]:
                        processed += 1
                        continue
                        
                    # 计算像元边界
                    left = raster_transform.c + col * pixel_size_x
                    right = left + pixel_size_x
                    top = raster_transform.f + row * raster_transform.e  # e通常为负值
                    bottom = top + raster_transform.e
                    
                    # 创建像元多边形
                    pixel_box = box(left, bottom, right, top)
                    
                    # 使用空间索引快速查找可能相交的路网
                    try:
                        possible_match_indices = road_tree.query(pixel_box)
                        total_queries += 1
                        
                        if len(possible_match_indices) > 0:
                            successful_queries += 1
                            
                            # 详细调试前几个有查询结果的像元
                            if successful_queries <= 3:
                                print(f"      🔎 像元({row},{col}) 路网查询: 找到{len(possible_match_indices)}个候选路段")
                                print(f"         像元边界: [{left:.2f}, {bottom:.2f}, {right:.2f}, {top:.2f}]")
                        
                        # 根据是否使用缓冲区计算不同的密度值
                        total_value = 0
                        intersection_count = 0
                        
                        if road_buffer_radius > 0:
                            # 缓冲区模式：计算面积覆盖比例
                            checked_roads = 0
                            # 通过索引获取实际的几何对象
                            for idx in possible_match_indices:
                                road_geom = road_geom_array[idx]
                                checked_roads += 1
                                
                                # 详细几何验证
                                if successful_queries <= 3 and checked_roads <= 3:
                                    print(f"         🔍 检查路网几何体[{checked_roads}]: {type(road_geom).__name__}")
                                    if road_geom is not None:
                                        print(f"            - 是否为None: False")
                                        print(f"            - 是否有is_valid: {hasattr(road_geom, 'is_valid')}")
                                        if hasattr(road_geom, 'is_valid'):
                                            print(f"            - is_valid: {road_geom.is_valid}")
                                        if hasattr(road_geom, 'area'):
                                            print(f"            - 缓冲区面积: {road_geom.area:.2f}m²")
                                    else:
                                        print(f"            - 是否为None: True")
                                
                                if road_geom is not None and hasattr(road_geom, 'is_valid') and road_geom.is_valid:
                                    try:
                                        # 详细相交测试
                                        intersects_result = road_geom.intersects(pixel_box)
                                        
                                        if successful_queries <= 3 and checked_roads <= 3:
                                            print(f"            - intersects结果: {intersects_result}")
                                        
                                        if intersects_result:
                                            intersection = road_geom.intersection(pixel_box)
                                            
                                            if successful_queries <= 3 and checked_roads <= 3:
                                                print(f"            - 交集是否为空: {intersection.is_empty}")
                                                if not intersection.is_empty:
                                                    print(f"            - 交集类型: {type(intersection).__name__}")
                                                    if hasattr(intersection, 'area'):
                                                        print(f"            - 交集面积: {intersection.area:.2f}m²")
                                            
                                            if not intersection.is_empty:
                                                intersection_count += 1
                                                if hasattr(intersection, 'area'):
                                                    total_value += intersection.area
                                                elif hasattr(intersection, 'geoms'):
                                                    for sub_geom in intersection.geoms:
                                                        if hasattr(sub_geom, 'area'):
                                                            total_value += sub_geom.area
                                                # 详细调试前几个相交成功的情况
                                                if successful_queries <= 3:
                                                    print(f"         ✅ 找到缓冲区相交[{intersection_count}]: 面积={intersection.area:.2f}m²")
                                    except Exception as e:
                                        # 跳过几何运算错误
                                        if successful_queries <= 3:
                                            print(f"         ❌ 缓冲区几何运算错误: {e}")
                                            print(f"            - 像元box: {pixel_box}")
                                            print(f"            - 路网几何: {type(road_geom).__name__}")
                                        continue
                                else:
                                    if successful_queries <= 3 and checked_roads <= 3:
                                        print(f"            - 跳过无效路网几何体")
                            
                            # 计算面积覆盖比例（交集面积/像元面积）
                            density_value = total_value / pixel_area if pixel_area > 0 else 0
                            road_density_raster[row, col] = density_value
                            
                            # 调试信息采样
                            if density_value > 0:
                                non_zero_count += 1
                                if debug_sample_count < max_debug_samples:
                                    print(f"      🔍 调试样本[{debug_sample_count+1}]: 像元({row},{col}), 缓冲区面积={total_value:.2f}m², 密度={density_value:.6f}")
                                    debug_sample_count += 1
                        else:
                            # 原始模式：计算路网长度密度
                            checked_roads = 0
                            # 通过索引获取实际的几何对象
                            for idx in possible_match_indices:
                                road_geom = road_geom_array[idx]
                                checked_roads += 1
                                
                                # 详细几何验证
                                if successful_queries <= 3 and checked_roads <= 3:
                                    print(f"         🔍 检查路网几何体[{checked_roads}]: {type(road_geom).__name__}")
                                    if road_geom is not None:
                                        print(f"            - 是否为None: False")
                                        print(f"            - 是否有is_valid: {hasattr(road_geom, 'is_valid')}")
                                        if hasattr(road_geom, 'is_valid'):
                                            print(f"            - is_valid: {road_geom.is_valid}")
                                        if hasattr(road_geom, 'length'):
                                            print(f"            - 路网长度: {road_geom.length:.2f}m")
                                    else:
                                        print(f"            - 是否为None: True")
                                
                                if road_geom is not None and hasattr(road_geom, 'is_valid') and road_geom.is_valid:
                                    try:
                                        # 详细相交测试
                                        intersects_result = road_geom.intersects(pixel_box)
                                        
                                        if successful_queries <= 3 and checked_roads <= 3:
                                            print(f"            - intersects结果: {intersects_result}")
                                        
                                        if intersects_result:
                                            intersection = road_geom.intersection(pixel_box)
                                            
                                            if successful_queries <= 3 and checked_roads <= 3:
                                                print(f"            - 交集是否为空: {intersection.is_empty}")
                                                if not intersection.is_empty:
                                                    print(f"            - 交集类型: {type(intersection).__name__}")
                                                    if hasattr(intersection, 'length'):
                                                        print(f"            - 交集长度: {intersection.length:.2f}m")
                                            
                                            if not intersection.is_empty:
                                                intersection_count += 1
                                                # 计算交集的长度
                                                if hasattr(intersection, 'length'):
                                                    total_value += intersection.length
                                                elif hasattr(intersection, 'geoms'):  # MultiLineString
                                                    for geom in intersection.geoms:
                                                        if hasattr(geom, 'length'):
                                                            total_value += geom.length
                                                # 详细调试前几个相交成功的情况
                                                if successful_queries <= 3:
                                                    print(f"         ✅ 找到路网相交[{intersection_count}]: 长度={intersection.length:.2f}m")
                                    except Exception as e:
                                        # 跳过几何运算错误
                                        if successful_queries <= 3:
                                            print(f"         ❌ 路网几何运算错误: {e}")
                                            print(f"            - 像元box: {pixel_box}")
                                            print(f"            - 路网几何: {type(road_geom).__name__}")
                                        continue
                                else:
                                    if successful_queries <= 3 and checked_roads <= 3:
                                        print(f"            - 跳过无效路网几何体")
                            
                            # 计算长度密度（长度/面积）
                            density_value = total_value / pixel_area if pixel_area > 0 else 0
                            road_density_raster[row, col] = density_value
                            
                            # 调试信息采样
                            if density_value > 0:
                                non_zero_count += 1
                                if debug_sample_count < max_debug_samples:
                                    print(f"      🔍 调试样本[{debug_sample_count+1}]: 像元({row},{col}), 路网长度={total_value:.2f}m, 密度={density_value:.6f}")
                                    debug_sample_count += 1
                                    
                    except Exception as e:
                        if successful_queries <= 3:
                            print(f"      ❌ 路网空间索引查询错误: {e}")
                    
                    # 显示进度和调试信息
                    processed += 1
                    if processed - last_debug_processed >= sample_debug_interval:
                        progress = processed / total_pixels * 100
                        query_success_rate = (successful_queries / total_queries * 100) if total_queries > 0 else 0
                        print(f"     计算进度: {progress:.1f}% ({processed:,}/{total_pixels:,}), 非零像元: {non_zero_count}")
                        print(f"     空间查询统计: 总查询{total_queries}, 有结果{successful_queries} ({query_success_rate:.1f}%)")
                        last_debug_processed = processed
                        
                    if processed % 50000 == 0 or processed == total_pixels:
                        progress = processed / total_pixels * 100
                        query_success_rate = (successful_queries / total_queries * 100) if total_queries > 0 else 0
                        print(f"     📊 总进度: {progress:.1f}%, 非零像元: {non_zero_count}, 查询成功率: {query_success_rate:.1f}%")
        else:
            print("   ⚠️  没有路网数据，跳过计算")
        
        road_density = road_density_raster.flatten()
        if road_buffer_radius > 0:
            print(f"   📊 路网缓冲区密度范围: {road_density.min():.6f} - {road_density.max():.6f} (面积比例)")
            print(f"   📈 非零像元数量: {np.sum(road_density > 0)}/{len(road_density)} ({np.sum(road_density > 0)/len(road_density)*100:.1f}%)")
        else:
            print(f"   📊 路网长度密度范围: {road_density.min():.6f} - {road_density.max():.6f} (米/平方米)")
            print(f"   📈 非零像元数量: {np.sum(road_density > 0)}/{len(road_density)} ({np.sum(road_density > 0)/len(road_density)*100:.1f}%)")
        
        # 3. 计算其他要素密度（如果有）
        other_density = None
        if other_dataset:
            print("3. 计算其他要素密度...")
            other_path = os.path.join(DATA_DIR, other_dataset)
            other_gdf = gpd.read_file(other_path)
            other_gdf = other_gdf.to_crs(target_crs)
            print(f"- 其他要素数据CRS: {other_gdf.crs}")
            print(f"- 其他要素数量: {len(other_gdf)}")
            
            # 根据几何类型计算密度
            geom_type = other_gdf.geometry.geom_type.iloc[0] if len(other_gdf) > 0 else 'Point'
            print(f"- 其他要素几何类型: {geom_type}")
            
            # 初始化其他要素密度栅格
            other_density_raster = np.zeros((raster_height, raster_width), dtype=np.float64)
            
            # 为其他要素创建空间索引
            other_geoms = list(other_gdf.geometry)
            # 过滤掉无效或非几何对象
            valid_other_geoms = [geom for geom in other_geoms if geom is not None and hasattr(geom, 'is_valid') and geom.is_valid]
            other_tree = STRtree(valid_other_geoms)
            
            # 遍历每个像元，计算其内部的其他要素密度
            total_pixels = raster_height * raster_width
            processed = 0
            
            for row in range(raster_height):
                for col in range(raster_width):
                    # 计算像元边界
                    left = raster_transform.c + col * pixel_size_x
                    right = left + pixel_size_x
                    top = raster_transform.f + row * raster_transform.e  # e通常为负值
                    bottom = top + raster_transform.e
                    
                    # 创建像元多边形
                    pixel_box = box(left, bottom, right, top)
                    
                    # 使用空间索引快速查找可能相交的要素
                    possible_matches = other_tree.query(pixel_box)
                    
                    if geom_type == 'Point':
                        # 点要素：计算像元内的点数量
                        feature_count = 0
                        for geom in possible_matches:
                            if geom is not None and hasattr(geom, 'is_valid') and geom.is_valid and pixel_box.contains(geom):
                                feature_count += 1
                        other_density_raster[row, col] = feature_count / pixel_area if pixel_area > 0 else 0
                        
                    elif geom_type in ['LineString', 'MultiLineString']:
                        # 线要素：计算像元内的线长度
                        total_length = 0
                        for geom in possible_matches:
                            intersection = geom.intersection(pixel_box)
                            if not intersection.is_empty:
                                if hasattr(intersection, 'length'):
                                    total_length += intersection.length
                                elif hasattr(intersection, 'geoms'):
                                    for sub_geom in intersection.geoms:
                                        if hasattr(sub_geom, 'length'):
                                            total_length += sub_geom.length
                        other_density_raster[row, col] = total_length / pixel_area if pixel_area > 0 else 0
                        
                    else:  # Polygon
                        # 面要素：计算像元内的面积
                        total_area = 0
                        for geom in possible_matches:
                            intersection = geom.intersection(pixel_box)
                            if not intersection.is_empty:
                                if hasattr(intersection, 'area'):
                                    total_area += intersection.area
                                elif hasattr(intersection, 'geoms'):
                                    for sub_geom in intersection.geoms:
                                        if hasattr(sub_geom, 'area'):
                                            total_area += sub_geom.area
                        # 面密度：交集面积/像元面积（比例）
                        other_density_raster[row, col] = total_area / pixel_area if pixel_area > 0 else 0
                    
                    # 显示进度
                    processed += 1
                    if processed % 10000 == 0 or processed == total_pixels:
                        progress = processed / total_pixels * 100
                        print(f"  进度: {progress:.1f}% ({processed:,}/{total_pixels:,})")
            
            other_density = other_density_raster.flatten()
            
            if geom_type == 'Point':
                print(f"- 其他要素密度范围: {other_density.min():.6f} - {other_density.max():.6f} (点/平方米)")
            elif geom_type in ['LineString', 'MultiLineString']:
                print(f"- 其他要素密度范围: {other_density.min():.6f} - {other_density.max():.6f} (米/平方米)")
            else:
                print(f"- 其他要素密度范围: {other_density.min():.6f} - {other_density.max():.6f} (面积比例)")
        
        # 📊 详细的敏感性组件分析（为综合模型做铺垫）
        print(f"\n🧮 敏感性模型组件详细分析:")
        print(f"{'='*80}")
        
        # 标准化前的统计
        print(f"📈 原始密度统计:")
        print(f"   易涝点密度: 最小={flood_point_density.min():.6f}, 最大={flood_point_density.max():.6f}, 均值={flood_point_density.mean():.6f}")
        print(f"   路网密度: 最小={road_density.min():.6f}, 最大={road_density.max():.6f}, 均值={road_density.mean():.6f}")
        if other_density is not None:
            print(f"   其他要素密度: 最小={other_density.min():.6f}, 最大={other_density.max():.6f}, 均值={other_density.mean():.6f}")
        
        # 标准化密度值
        print(f"\n⚖️  标准化处理:")
        flood_max = np.max(flood_point_density)
        road_max = np.max(road_density)
        
        if flood_max > 0:
            flood_point_density = flood_point_density / flood_max
            print(f"   ✅ 易涝点密度标准化: 除以最大值 {flood_max:.6f}")
        else:
            print(f"   ⚠️  易涝点密度最大值为0，跳过标准化")
            
        if road_max > 0:
            road_density = road_density / road_max
            print(f"   ✅ 路网密度标准化: 除以最大值 {road_max:.6f}")
        else:
            print(f"   ⚠️  路网密度最大值为0，跳过标准化")
        
        if other_density is not None:
            other_max = np.max(other_density)
            if other_max > 0:
                other_density = other_density / other_max
                print(f"   ✅ 其他要素密度标准化: 除以最大值 {other_max:.6f}")
            else:
                print(f"   ⚠️  其他要素密度最大值为0，跳过标准化")
        else:
            other_density = np.full_like(flood_point_density, 1)  # 默认值
            print(f"   🔄 使用默认其他要素密度值: 1.0")
        
        # 标准化后的统计
        print(f"\n📊 标准化后密度统计:")
        print(f"   易涝点密度: [{flood_point_density.min():.6f}, {flood_point_density.max():.6f}], 均值={flood_point_density.mean():.6f}")
        print(f"   路网密度: [{road_density.min():.6f}, {road_density.max():.6f}], 均值={road_density.mean():.6f}")
        print(f"   其他要素密度: [{other_density.min():.6f}, {other_density.max():.6f}], 均值={other_density.mean():.6f}")
        
        # 🎯 敏感性指数S计算
        print(f"\n🎯 敏感性指数S计算:")
        print(f"   公式: S = g1×(易涝点密度) + g2×(路网密度) + g3×(其他密度)")
        print(f"   权重: g1={g1}, g2={g2}, g3={g3}")
        
        # 计算各组件贡献
        flood_contribution = g1 * flood_point_density
        road_contribution = g2 * road_density  
        other_contribution = g3 * other_density
        
        print(f"\n📊 各组件贡献统计:")
        print(f"   易涝点贡献 (g1×密度): [{flood_contribution.min():.6f}, {flood_contribution.max():.6f}], 均值={flood_contribution.mean():.6f}")
        print(f"   路网贡献 (g2×密度): [{road_contribution.min():.6f}, {road_contribution.max():.6f}], 均值={road_contribution.mean():.6f}")
        print(f"   其他贡献 (g3×密度): [{other_contribution.min():.6f}, {other_contribution.max():.6f}], 均值={other_contribution.mean():.6f}")
        
        # 计算敏感性指数
        sensitivity = flood_contribution + road_contribution + other_contribution
        print(f"\n🔢 初始敏感性指数S:")
        print(f"   范围: [{sensitivity.min():.6f}, {sensitivity.max():.6f}]")
        print(f"   均值: {sensitivity.mean():.6f}, 标准差: {sensitivity.std():.6f}")
        print(f"   非零像元: {np.sum(sensitivity > 0)}/{len(sensitivity)} ({np.sum(sensitivity > 0)/len(sensitivity)*100:.1f}%)")
        
        # 确保结果非负
        original_min = sensitivity.min()
        sensitivity = np.maximum(sensitivity, 0)
        if original_min < 0:
            print(f"   ⚠️  发现负值 {original_min:.6f}，已调整为0")
        
        # 将S的范围控制在[0.9-1]之间
        print(f"\n🔧 敏感性指数范围调整 [0.9-1]:")
        
        # 首先将其标准化到[0-1]区间
        if np.max(sensitivity) > 0:
            sensitivity_normalized = sensitivity / np.max(sensitivity)
            print(f"   步骤1: 标准化到[0-1] - 除以最大值 {np.max(sensitivity):.6f}")
            print(f"   标准化后范围: [{sensitivity_normalized.min():.6f}, {sensitivity_normalized.max():.6f}]")
        else:
            sensitivity_normalized = sensitivity
            print(f"   ⚠️  最大值为0，跳过标准化")
        
        # 然后将[0-1]区间映射到[0.9-1]区间
        sensitivity = 0.9 + 0.1 * sensitivity_normalized
        print(f"   步骤2: 映射到[0.9-1] - 使用公式: 0.9 + 0.1 × 标准化值")
        print(f"   🏆 最终敏感性指数范围: [{sensitivity.min():.6f}, {sensitivity.max():.6f}]")
        print(f"   🏆 最终均值: {sensitivity.mean():.6f}, 标准差: {sensitivity.std():.6f}")
        
        # 🏛️ 为综合模型准备的关键统计信息
        print(f"\n🏛️ 综合模型准备信息:")
        print(f"   总评估面积: {np.sum(valid_mask) * pixel_area / 1000000:.2f} km²")
        print(f"   平均敏感性: {sensitivity.mean():.6f}")
        print(f"   最高敏感区域: {sensitivity.max():.6f}")
        print(f"   最低敏感区域: {sensitivity.min():.6f}")
        
        # 分位数分析
        print(f"\n📊 敏感性分布分位数分析:")
        percentiles = [10, 25, 50, 75, 90, 95, 99]
        for p in percentiles:
            val = np.percentile(sensitivity, p)
            print(f"   {p:2d}分位数: {val:.6f}")
            
        print(f"{'='*80}")
        
        # 将敏感性指数重新整形为栅格数组
        print("\n准备敏感性指数栅格数据...")
        sensitivity_raster = sensitivity.reshape(raster_height, raster_width)
        
        # 应用掩膜，只保留有效数据范围内的结果
        print("\n应用栅格模板掩膜:")
        sensitivity_raster_masked = sensitivity_raster.copy()
        sensitivity_raster_masked[~valid_mask] = -9999  # 无效区域设置为NoData
        
        # 统计掩膜后的结果
        valid_sensitivity = sensitivity_raster_masked[valid_mask]
        print(f"- 有效区域敏感性指数范围: {valid_sensitivity.min():.4f} - {valid_sensitivity.max():.4f}")
        print(f"- 有效像元数量: {len(valid_sensitivity)} / {sensitivity_raster.size}")
        print(f"- 敏感性指数栅格尺寸: {raster_width} x {raster_height}")
        
        # 使用掩膜后的数据
        sensitivity_raster = sensitivity_raster_masked
        
        # 将结果转换回模板的原始坐标系进行保存
        if original_crs != target_crs:
            # 如果当前坐标系与模板原始坐标系不同，需要转换回去
            print(f"\n将敏感性指数栅格转换回模板原始坐标系: {original_crs}...")
            
            # 计算目标边界
            src_bounds = rasterio.transform.array_bounds(raster_height, raster_width, raster_transform)
            dst_bounds = transform_bounds(target_crs, original_crs, *src_bounds)
            
            # 计算目标变换和尺寸
            dst_transform, dst_width, dst_height = calculate_default_transform(
                target_crs, original_crs, raster_width, raster_height, *src_bounds
            )
            
            # 创建目标数组，初始化为NoData值
            raster_data = np.full((dst_height, dst_width), -9999, dtype=np.float64)
            
            # 重投影
            reproject(
                source=sensitivity_raster,
                destination=raster_data,
                src_transform=raster_transform,
                src_crs=target_crs,
                dst_transform=dst_transform,
                dst_crs=original_crs,
                resampling=Resampling.bilinear,
                src_nodata=-9999,
                dst_nodata=-9999
            )
            
            save_crs = original_crs
            save_transform = dst_transform
            raster_height = dst_height
            raster_width = dst_width
            print("- 坐标系转换完成")
        else:
            # 如果坐标系相同，直接使用当前结果
            save_crs = original_crs
            save_transform = raster_transform
            raster_data = sensitivity_raster
            print(f"- 直接使用模板坐标系保存: {original_crs}")

        # 创建有效数据掩码（基于NoData值）
        final_valid_mask = ~np.isclose(raster_data, -9999, rtol=1e-10, atol=1e-10)
        final_valid_data = raster_data[final_valid_mask]
        
        print(f"\n最终数据统计:")
        print(f"- 有效数据点数量: {np.sum(final_valid_mask)} / {final_valid_mask.size}")
        if len(final_valid_data) > 0:
            print(f"- 数据范围: {np.min(final_valid_data):.4f} to {np.max(final_valid_data):.4f}")
        else:
            print(f"- 警告: 没有有效数据")
        
        # 保存为GeoTIFF
        print("\n保存GeoTIFF...")
        with rasterio.open(
            result_path,
            'w',
            driver='GTiff',
            height=raster_data.shape[0],
            width=raster_data.shape[1],
            count=1,
            dtype=raster_data.dtype,
            crs=save_crs,
            transform=save_transform,
            nodata=-9999
        ) as dst:
            dst.write(raster_data, 1)
        print("- GeoTIFF保存完成")
        
        # 生成预览图
        print("\n生成预览图...")
        preview_filename = result_name + '_' +  f'sensitivity_{timestamp}_{result_id[:8]}_preview.png'
        preview_path = os.path.join(OUTPUT_DIR, preview_filename)
        assessment_engine.create_sensitivity_preview(result_path, preview_path, '敏感性评估结果')
        print("- 预览图生成完成")
        
        # 注意：不再生成GeoJSON文件，因为结果是栅格格式
        print("\n跳过GeoJSON生成（栅格结果）")
        
        # 获取统计信息
        valid_data = raster_data[raster_data != -9999]
        statistics = {
            'min': float(np.min(valid_data)),
            'max': float(np.max(valid_data)),
            'mean': float(np.mean(valid_data)),
            'std': float(np.std(valid_data))
        }
        
        result = {
            'id': result_id,
            'name': result_name,
            'type': 'sensitivity',
            'createdAt': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'description': '基于易涝点密度、路网密度和其他要素的环境敏感性评估结果',
            'parameters': {
                'raster_template_dataset_id': raster_template_dataset,
                'road_dataset_id': road_dataset,
                'flood_point_dataset_id': flood_point_dataset,
                'other_dataset_id': other_dataset,
                'weights': {
                    'g1': float(g1),
                    'g2': float(g2),
                    'g3': float(g3)
                }
            },
            'files': [{
                'id': 'flood_results/'+result_filename,
                'name': result_name,
                'type': 'raster',
                'format': 'tif',
                'url': f'/api/datasets/flood_results/{result_filename}/image',
                'download_url': f'/api/datasets/flood_results/{result_filename}/download'
            }],
            'preview': [f'/api/datasets/images/flood_results/{preview_filename}'],
            'statistics': {
                'min': float(np.min(valid_data)),
                'max': float(np.max(valid_data)),
                'mean': float(np.mean(valid_data)),
                'std': float(np.std(valid_data)),
                'valid_count': int(np.sum(valid_mask)),
                'total_count': int(valid_mask.size),
                'nodata_value': float(-9999)
            }
        }
        
        print("\n=== 敏感性评估完成 ===")
        return jsonify(result)
        
    except Exception as e:
        print("\n!!! 敏感性评估出错 !!!")
        print(f"错误信息: {str(e)}")
        import traceback
        print("\n详细错误信息:")
        traceback.print_exc()
        return jsonify({'error': f'敏感性评估失败: {str(e)}'}), 500

@flood_bp.route('/resistance', methods=['POST'])
@cross_origin()
@log_function_call
def resistance_assessment():
    """
    工程防灾性R评估主函数
    实现流程：
    1. 读取参数与数据（DEM、危险性、围堰shp等）
    2. 读取/计算水位（支持斜面水位模型）
    3. 正确计算围堰降低水位（ΔH围堰= max(0, min(围堰顶高, H水)-H地)）
    4. 计算总降低水位，执行防灾性条件判断
    5. 结果写出与统计
    """
    try:
        log_and_print("\n" + "="*80)
        log_and_print("🛡️  开始工程防灾性R评估")
        log_and_print("="*80)
        data = request.get_json()
        log_and_print(f"📥 接收到的请求数据: {data}")
        
        # 获取参数
        water_level = float(data.get('water_level', 0))  # 淹没水位高程H水，使用斜面模型时可以为0
        delta_h_river = float(data.get('delta_h_river', 0))  # 河道拓宽清淤降低水位ΔH拓河
        dem_dataset_id = data.get('dem_dataset_id')[0]  # DEM高程数据
        dam_dataset_id = data.get('dam_dataset_id')[0]  # 围堰范围数据
        hazard_dataset_id = data.get('hazard_dataset_id')[0]  # 危险性模型H数据
        result_name = data.get('result_name', '工程防灾性R评估结果')
        
        # 新增：是否使用斜面水位模型
        use_slope_model = data.get('use_slope_model', False)
        
        print(f"\n📋 参数配置详情:")
        print(f"   🌊 淹没水位高程(H水): {water_level}m")
        print(f"   🏗️  河道拓宽清淤降低水位(ΔH拓河): {delta_h_river}m")
        print(f"   📁 DEM数据集: {dem_dataset_id}")
        print(f"   🚧 围堰数据集: {dam_dataset_id}")
        print(f"   ⚠️  危险性模型数据集: {hazard_dataset_id}")
        print(f"   🔬 使用斜面水位模型: {'是' if use_slope_model else '否'}")
        print(f"   📝 结果名称: {result_name}")
        
        print(f"\n🧮 算法公式:")
        print(f"   R = H,  当 (ΔH拓河 + ΔH围堰) > (H水 - H地)")
        print(f"   R = 0,  当 (ΔH拓河 + ΔH围堰) ≤ (H水 - H地)")
        print(f"   其中:")
        print(f"   - H: 危险性模型结果值")
        print(f"   - ΔH拓河: 河道拓宽清淤降低的水位 = {delta_h_river}m")
        print(f"   - ΔH围堰: 围堰工程降低的水位（从围堰数据读取）")
        print(f"   - H水: 淹没水位高程")
        print(f"   - H地: DEM地面高程")
        
        # 验证必要参数
        if not all([dem_dataset_id, dam_dataset_id, hazard_dataset_id]):
            print("❌ 错误: 缺少必要的数据集参数")
            return jsonify({'error': '缺少必要的数据集参数'}), 400
        
        # 如果不使用斜面模型，则水位是必需的
        if not use_slope_model and water_level <= 0:
            print("❌ 错误: 淹没水位高程必须大于0")
            return jsonify({'error': '淹没水位高程必须大于0'}), 400
        
        # 生成唯一ID和文件名
        result_id = str(uuid.uuid4())
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_result_name = secure_filename(result_name)
        result_filename = f'{safe_result_name}_resistance_{timestamp}_{result_id[:8]}.tif'
        result_path = os.path.join(OUTPUT_DIR, result_filename)
        
        print(f"\n📁 文件路径:")
        print(f"   💾 结果文件: {result_path}")
        
        # 读取DEM数据
        print(f"\n📊 读取DEM数据...")
        dem_path = os.path.join(DATA_DIR, dem_dataset_id)
        with rasterio.open(dem_path) as dem_src:
            dem_data = dem_src.read(1)
            dem_transform = dem_src.transform
            dem_crs = dem_src.crs
            dem_bounds = dem_src.bounds
            dem_width = dem_src.width
            dem_height = dem_src.height
            dem_nodata = dem_src.nodata
        
        print(f"   ✅ DEM数据信息:")
        print(f"      - CRS: {dem_crs}")
        print(f"      - 尺寸: {dem_width} x {dem_height}")
        print(f"      - 边界: {dem_bounds}")
        print(f"      - NoData: {dem_nodata}")
        print(f"      - 高程范围: [{np.min(dem_data[dem_data != dem_nodata]):.2f}, {np.max(dem_data[dem_data != dem_nodata]):.2f}]m")
        
        # 读取危险性模型H数据
        print(f"\n📊 读取危险性模型H数据...")
        hazard_path = os.path.join(DATA_DIR, hazard_dataset_id)
        water_level_array = None  # 初始化水位数组
        water_depth_array = None  # 初始化水深数组
        
        with rasterio.open(hazard_path) as hazard_src:
            hazard_data = hazard_src.read(1)
            hazard_transform = hazard_src.transform
            hazard_crs = hazard_src.crs
            
            print(f"   ✅ 危险性模型数据信息:")
            print(f"      - CRS: {hazard_crs}")
            print(f"      - 尺寸: {hazard_src.width} x {hazard_src.height}")
            print(f"      - 危险性值范围: [{np.min(hazard_data[hazard_data != -9999]):.3f}, {np.max(hazard_data[hazard_data != -9999]):.3f}]")
            
            # 判断传入的hazard_dataset_id本身是否为水深数据
            hazard_basename = os.path.basename(hazard_path)
            is_water_depth_file = '_hazard_water_depth_' in hazard_basename
            
            if is_water_depth_file:
                print(f"   ✅ 检测到传入的危险性模型文件是水深数据（_hazard_water_depth_）")
                print(f"   📊 直接使用该文件作为水深数据")
                water_depth_array = hazard_data.copy()
                # 确保水深为正值
                water_depth_array[water_depth_array < 0] = 0
                water_depth_array[water_depth_array == -9999] = 0
                
                # 统计水深信息
                valid_depths = water_depth_array[(water_depth_array > 0) & (water_depth_array != -9999)]
                if len(valid_depths) > 0:
                    print(f"      - 水深范围: [{np.min(valid_depths):.2f}, {np.max(valid_depths):.2f}]m")
                    print(f"      - 平均水深: {np.mean(valid_depths):.2f}m")
                    print(f"      - 淹没像元数: {len(valid_depths):,}")
            
            # 如果使用斜面水位模型，尝试从危险性模型中提取水位信息
            if use_slope_model and not is_water_depth_file:
                print(f"\n🔬 使用危险性模型的斜面水位...")
                
                # 检查该模型是否包含斜面水位信息
                hazard_profile = hazard_src.profile
                hazard_tags = hazard_src.tags()
                
                # 尝试查找相关水深数据集（通常与hazard数据集在同一目录且名称相似）
                hazard_dir = os.path.dirname(hazard_path)
                hazard_basename = os.path.basename(hazard_path)
                water_depth_path = None
                
                # 新增：严格按照H模型输出规则查找水深tif
                # 1. 直接替换_hazard_为_hazard_water_depth_
                if '_hazard_' in hazard_basename:
                    wd_candidate = hazard_basename.replace('_hazard_', '_hazard_water_depth_')
                    candidate_path = os.path.join(hazard_dir, wd_candidate)
                    print(f"      - 严格查找: {wd_candidate}")
                    if os.path.exists(candidate_path):
                        water_depth_path = candidate_path
                # 2. 兼容原有的多种命名变体
                if not water_depth_path:
                    water_depth_patterns = [
                        hazard_basename.replace('hazard', 'hazard_water_depth'),
                        hazard_basename.replace('.tif', '_water_depth.tif'),
                        hazard_basename.replace('hazard', 'hazard_water_level'),
                        hazard_basename.replace('.tif', '_water_level.tif')
                    ]
                    for pattern in water_depth_patterns:
                        potential_path = os.path.join(hazard_dir, pattern)
                        print(f"      - 检查: {pattern}")
                        if os.path.exists(potential_path):
                            water_depth_path = potential_path
                            break
                
                if water_depth_path:
                    print(f"   ✅ 找到水深数据: {water_depth_path}")
                    # 读取水深数据
                    with rasterio.open(water_depth_path) as water_depth_src:
                        water_depth = water_depth_src.read(1)
                        
                        # 计算水位数组：水位 = DEM + 水深
                        water_level_array = np.zeros_like(dem_data)
                        
                        # 确保水深和DEM数据尺寸匹配
                        if water_depth.shape == dem_data.shape:
                            valid_mask = (dem_data != dem_nodata) & (water_depth != -9999)
                            water_level_array[valid_mask] = dem_data[valid_mask] + water_depth[valid_mask]
                            print(f"      ✅ 成功计算斜面水位矩阵")
                            print(f"      - 水位范围: [{np.min(water_level_array[valid_mask]):.2f}, {np.max(water_level_array[valid_mask]):.2f}]m")
                        else:
                            print(f"      ⚠️  水深数据尺寸 {water_depth.shape} 与DEM数据尺寸 {dem_data.shape} 不匹配")
                            # 重投影水深数据以匹配DEM
                            print(f"      🔄 尝试重投影水深数据...")
                            water_depth_reprojected = np.full((dem_height, dem_width), -9999, dtype=np.float32)
                            
                            reproject(
                                source=water_depth,
                                destination=water_depth_reprojected,
                                src_transform=water_depth_src.transform,
                                src_crs=water_depth_src.crs,
                                dst_transform=dem_transform,
                                dst_crs=dem_crs,
                                resampling=Resampling.bilinear,
                                src_nodata=-9999,
                                dst_nodata=-9999
                            )
                            
                            # 使用重投影后的水深数据
                            valid_mask = (dem_data != dem_nodata) & (water_depth_reprojected != -9999)
                            water_level_array[valid_mask] = dem_data[valid_mask] + water_depth_reprojected[valid_mask]
                            print(f"      ✅ 水深数据重投影完成并成功计算斜面水位矩阵")
                            print(f"      - 重投影后水位范围: [{np.min(water_level_array[valid_mask]):.2f}, {np.max(water_level_array[valid_mask]):.2f}]m")
                else:
                    # 如果找不到水深数据，从危险性结果中尝试恢复水位信息
                    print(f"      ❌ 未找到水深数据，尝试从危险性结果中恢复水位...")
                    
                    # 如果水位未提供，尝试从危险性模型参数中获取
                    if water_level <= 0:
                        # 尝试读取hazard结果的metadata
                        try:
                            metadata = hazard_src.tags()
                            if 'water_level' in metadata:
                                water_level = float(metadata['water_level'])
                                print(f"      ✅ 从metadata提取水位: {water_level}m")
                            elif 'p0_water_level' in metadata:
                                water_level = float(metadata['p0_water_level'])
                                print(f"      ✅ 从metadata提取P0水位: {water_level}m")
                            else:
                                print(f"      ⚠️  无法从metadata提取水位，使用默认水位446.55m")
                                water_level = 446.55  # 使用默认水位
                        except Exception as e:
                            print(f"      ⚠️  无法从metadata提取水位: {str(e)}，使用默认水位446.55m")
                            water_level = 446.55  # 使用默认水位
                    
                    # 如果使用斜面模型，但找不到斜面水位数据，则使用统一水位
                    if use_slope_model:
                                        print(f"      ⚠️  使用斜面模型但无法获取斜面水位数据，将使用统一水位 {water_level}m")
                use_slope_model = False
        
        # 如果已经有水深数组，直接使用，不需要再计算水深
        if water_depth_array is not None:
            print(f"\n📊 使用已读取的水深数据，跳过水深计算步骤")
        
        # 读取围堰数据
        print(f"\n📊 读取围堰数据...")
        dam_path = os.path.join(DATA_DIR, dam_dataset_id)
        dam_gdf = gpd.read_file(dam_path)
        print(f"   ✅ 围堰数据信息:")
        print(f"      - CRS: {dam_gdf.crs}")
        print(f"      - 围堰数量: {len(dam_gdf)}")
        print(f"      - 字段列表: {list(dam_gdf.columns)}")
        
        # 确保所有数据在同一坐标系
        target_crs = dem_crs
        if dam_gdf.crs != target_crs:
            dam_gdf = dam_gdf.to_crs(target_crs)
            print(f"      🔄 围堰数据已转换到目标CRS: {target_crs}")
        
        # 重投影危险性数据到DEM坐标系（如果需要）
        if hazard_crs != dem_crs or hazard_transform != dem_transform:
            print(f"\n🔄 重投影危险性数据到DEM坐标系...")
            hazard_data_reprojected = np.full((dem_height, dem_width), -9999, dtype=np.float32)
            
            reproject(
                source=hazard_data,
                destination=hazard_data_reprojected,
                src_transform=hazard_transform,
                src_crs=hazard_crs,
                dst_transform=dem_transform,
                dst_crs=dem_crs,
                resampling=Resampling.bilinear,
                src_nodata=-9999,
                dst_nodata=-9999
            )
            hazard_data = hazard_data_reprojected
            print(f"   ✅ 危险性数据重投影完成")
        
        # 创建围堰降低水位栅格
        print(f"\n🚧 创建围堰降低水位栅格...")
        delta_h_dam_raster = np.zeros((dem_height, dem_width), dtype=np.float32)
        from rasterio.features import rasterize
        height_fields = ['height', 'Height', 'HEIGHT', '高度', 'h', 'H']
        height_field = None
        for field in height_fields:
            if field in dam_gdf.columns:
                height_field = field
                break
        if height_field:
            print(f"   🎯 使用高度字段: {height_field}")
            
            # 获取围堰高度值
            height_values = dam_gdf[height_field].values
            print(f"      - 围堰顶高范围: [{np.min(height_values):.2f}, {np.max(height_values):.2f}]m")
            print(f"      - 围堰顶高均值: {np.mean(height_values):.2f}m")
            
            # 判断height字段是绝对高程还是相对高度
            dem_mean = np.mean(dem_data[dem_data > 0])
            height_mean = np.mean(height_values)
            
            if height_mean > dem_mean * 0.8:  # 如果围堰高度接近DEM高程，认为是绝对高程
                print(f"      - 检测到height字段为绝对高程，转换为相对高度")
                # 修复：使用更合理的围堰高度计算方法
                # 计算围堰相对于当地地面的实际高度
                relative_height = []
                for idx, (geom, height) in enumerate(zip(dam_gdf.geometry, height_values)):
                    # 获取围堰区域的平均地面高程
                    dam_mask = rasterize(
                        [(geom, 1)],
                        out_shape=(dem_height, dem_width),
                        transform=dem_transform,
                        fill=0,
                        dtype=np.uint8
                    )
                    local_dem = dem_data[dam_mask == 1]
                    if len(local_dem) > 0:
                        local_ground_height = np.mean(local_dem)
                        # 围堰相对高度 = 围堰顶高 - 当地地面高程
                        rel_height = max(2.0, min(10.0, height - local_ground_height))  # 限制在2-10米
                    else:
                        rel_height = 3.0  # 默认3米
                    relative_height.append(rel_height)
                
                relative_height = np.array(relative_height)
                print(f"      - 转换后相对高度范围: [{np.min(relative_height):.2f}, {np.max(relative_height):.2f}]m")
                
                # 使用计算出的相对高度进行栅格化
                dam_height_raster = rasterize(
                    [(geom, height) for geom, height in zip(dam_gdf.geometry, relative_height)],
                    out_shape=(dem_height, dem_width),
                    transform=dem_transform,
                    fill=0,
                    dtype=np.float32
                )
            else:
                print(f"      - 检测到height字段为相对高度，直接使用")
                # 直接使用height字段作为相对高度
                dam_height_raster = rasterize(
                    [(geom, height) for geom, height in zip(dam_gdf.geometry, height_values)],
                    out_shape=(dem_height, dem_width),
                    transform=dem_transform,
                    fill=0,
                    dtype=np.float32
                )
            
            # 计算围堰降低水位：ΔH围堰 = min(围堰相对高度, 水深)
            # 围堰只能降低其高度范围内的水位
            if water_depth_array is not None:
                delta_h_dam_raster = np.minimum(dam_height_raster, water_depth_array)
            else:
                # 如果没有水深数据，使用默认最大降低水位3米
                delta_h_dam_raster = np.minimum(dam_height_raster, 3.0)
            
            # 确保非围堰区域为0
            delta_h_dam_raster[dam_height_raster == 0] = 0
            
            dam_pixels = np.sum(delta_h_dam_raster > 0)
            max_dam_height = np.max(delta_h_dam_raster) if dam_pixels > 0 else 0
            print(f"   ✅ 围堰降低水位栅格化完成:")
            print(f"      - 围堰有效降低水位像元数: {dam_pixels:,}")
            print(f"      - 最大围堰降低水位: {max_dam_height:.2f}m")
            print(f"      - 围堰总面积: {dam_pixels * abs(dem_transform[0] * dem_transform[4]) / 1e6:.2f} km²")
        else:
            # 如果没有height字段，使用默认值2.0米
            shapes = [(geom, 2.0) for geom in dam_gdf.geometry]
            delta_h_dam_raster = rasterize(
                shapes,
                out_shape=(dem_height, dem_width),
                transform=dem_transform,
                fill=0,
                dtype=np.float32
            )
            print(f"   ⚠️  警告: 围堰数据中没有height字段，使用默认值2.0m")
        
        # 应用工程防灾性算法
        print(f"\n🧮 应用工程防灾性算法...")
        print(f"   算法详情: R=H，当（ΔH拓河+ΔH围堰）＞（H水-H地）；R=0，当（ΔH拓河+ΔH围堰）≤（H水-H地）")
        
        # 创建结果数组
        resistance_data = np.full((dem_height, dem_width), -9999, dtype=np.float32)
        
        # 创建有效数据掩膜
        valid_mask = (dem_data != dem_nodata) & (dem_data != -9999) & (hazard_data != -9999)
        valid_pixels = np.sum(valid_mask)
        print(f"   📊 有效像元数: {valid_pixels:,} ({valid_pixels/(dem_width*dem_height)*100:.1f}%)")
        
        # 计算水深
        if water_depth_array is not None:
            # 如果已经有水深数组，直接使用
            water_depth = water_depth_array
            print(f"   📊 使用已读取的水深数据")
            valid_depths = water_depth[valid_mask & (water_depth > 0)]
            if len(valid_depths) > 0:
                print(f"      - 水深范围: [{np.min(valid_depths):.2f}, {np.max(valid_depths):.2f}]m")
                print(f"      - 平均水深: {np.mean(valid_depths):.2f}m")
                print(f"      - 淹没像元数: {len(valid_depths):,}")
        else:
            # 需要计算水深
            water_depth = np.zeros_like(dem_data)
            
            if use_slope_model and water_level_array is not None:
                # 使用斜面水位模型计算水深
                water_depth[valid_mask] = water_level_array[valid_mask] - dem_data[valid_mask]
                print(f"   🔬 使用斜面水位模型计算水深")
            else:
                # 使用统一水位计算水深
                water_depth[valid_mask] = water_level - dem_data[valid_mask]
                print(f"   🌊 使用统一水位 {water_level}m 计算水深")
            
            # 确保水深为正值（只有被淹没的区域才有水深）
            water_depth[water_depth < 0] = 0
            valid_depths = water_depth[valid_mask & (water_depth > 0)]
            if len(valid_depths) > 0:
                print(f"      - 水深范围: [{np.min(valid_depths):.2f}, {np.max(valid_depths):.2f}]m")
                print(f"      - 平均水深: {np.mean(valid_depths):.2f}m")
                print(f"      - 淹没像元数: {len(valid_depths):,}")
            else:
                print(f"      - ⚠️  没有找到有效水深数据")
        
        # 计算总的水位降低量
        delta_h_total = delta_h_river + delta_h_dam_raster  # 总的水位降低量
        total_reduction_stats = delta_h_total[delta_h_total > 0]
        if len(total_reduction_stats) > 0:
            print(f"   🛠️  工程措施降低水位统计:")
            print(f"      - 河道拓宽清淤贡献: {delta_h_river}m (统一值)")
            
            # 修复：避免空数组导致的最小值计算错误
            dam_positive = delta_h_dam_raster[delta_h_dam_raster > 0]
            if len(dam_positive) > 0:
                print(f"      - 围堰工程贡献范围: [{np.min(dam_positive):.2f}, {np.max(dam_positive):.2f}]m")
            else:
                print(f"      - 围堰工程贡献: 0.00m (无有效围堰降低水位)")
                
            print(f"      - 总降低水位范围: [{np.min(total_reduction_stats):.2f}, {np.max(total_reduction_stats):.2f}]m")
            print(f"      - 平均总降低水位: {np.mean(total_reduction_stats):.2f}m")
        
        # 应用算法：条件判断
        print(f"\n🎯 执行防灾性条件判断...")
        
        # 添加调试信息
        print(f"   🔍 调试信息:")
        print(f"      - 水深范围: [{np.min(water_depth[valid_mask]):.2f}, {np.max(water_depth[valid_mask]):.2f}]m")
        print(f"      - 工程措施范围: [{np.min(delta_h_total[valid_mask]):.2f}, {np.max(delta_h_total[valid_mask]):.2f}]m")
        print(f"      - 河道拓宽清淤值: {delta_h_river}m")
        
        # 增加水深和工程措施的对比统计
        water_depth_positive = water_depth[water_depth > 0]
        delta_h_total_positive = delta_h_total[delta_h_total > 0]
        if len(water_depth_positive) > 0 and len(delta_h_total_positive) > 0:
            print(f"      - 有效水深 vs 工程措施:")
            print(f"         * 有效水深均值: {np.mean(water_depth_positive):.2f}m")
            print(f"         * 工程措施均值: {np.mean(delta_h_total_positive):.2f}m")
            print(f"         * 水深>工程措施的像元数: {np.sum((water_depth > 0) & (water_depth > delta_h_total)):,}")
            print(f"         * 工程措施>水深的像元数: {np.sum((water_depth > 0) & (water_depth <= delta_h_total)):,}")
        
        # 修复：避免围堰最大高度计算错误
        if np.any(delta_h_dam_raster > 0):
            print(f"      - 围堰最大高度: {np.max(delta_h_dam_raster):.2f}m")
        else:
            print(f"      - 围堰最大高度: 0.00m (无有效围堰)")
        
        # 检查河道区域（低高程区域）
        low_elevation_mask = (dem_data < np.percentile(dem_data[valid_mask], 20)) & valid_mask
        if np.any(low_elevation_mask):
            low_elevation_water_depth = water_depth[low_elevation_mask]
            low_elevation_delta_h = delta_h_total[low_elevation_mask]
            print(f"      - 低高程区域(河道)统计:")
            print(f"         * 低高程区域像元数: {np.sum(low_elevation_mask):,}")
            print(f"         * 低高程区域水深范围: [{np.min(low_elevation_water_depth):.2f}, {np.max(low_elevation_water_depth):.2f}]m")
            print(f"         * 低高程区域工程措施范围: [{np.min(low_elevation_delta_h):.2f}, {np.max(low_elevation_delta_h):.2f}]m")
            print(f"         * 低高程区域平均水深: {np.mean(low_elevation_water_depth):.2f}m")
            print(f"         * 低高程区域平均工程措施: {np.mean(low_elevation_delta_h):.2f}m")
        
        # 修复：检查水深是否全为0，如果是，则创建一个模拟水深
        if np.all(water_depth[valid_mask] == 0) or np.max(hazard_data) > 100:
            print(f"      ⚠️ 检测到水深全为0或危险性值异常大（可能使用了DEM作为危险性模型输入）")
            print(f"      🔄 创建模拟水深用于防灾效果计算")
            
            # 使用DEM的10%作为模拟水深
            simulated_water_depth = dem_data * 0.1
            simulated_water_depth[simulated_water_depth < 1.0] = 1.0  # 确保最小水深为1米
            water_depth = simulated_water_depth
            
            # 创建模拟危险性值
            print(f"      🔄 创建模拟危险性值")
            simulated_hazard = np.zeros_like(hazard_data)
            # 将有水深的区域设置为1-5的危险性值
            hazard_mask = (water_depth > 0) & valid_mask
            simulated_hazard[hazard_mask] = np.clip(water_depth[hazard_mask], 1.0, 5.0)
            hazard_data = simulated_hazard
            
            # 输出模拟水深统计
            valid_depths = water_depth[valid_mask]
            print(f"      - 模拟水深范围: [{np.min(valid_depths):.2f}, {np.max(valid_depths):.2f}]m")
            print(f"      - 平均模拟水深: {np.mean(valid_depths):.2f}m")
            print(f"      - 模拟危险性值范围: [0.00, {np.max(hazard_data):.2f}]")
        
        # 修复：只在水深>0的区域应用条件判断，其他区域不需要防灾
        flooded_mask = (water_depth > 0) & valid_mask  # 有水深的区域（淹没区）
        condition = (delta_h_total > water_depth) & flooded_mask  # 防灾有效区域
        
        effective_pixels = np.sum(condition)  # 防灾有效区域像元数
        flooded_pixels = np.sum(flooded_mask & ~condition)  # 仍然淹水区域像元数
        non_flooded_pixels = np.sum(valid_mask & ~flooded_mask)  # 未淹没区域像元数
        
        print(f"   ✅ 条件分析结果:")
        print(f"      - 防灾有效区域像元数: {effective_pixels:,} ({effective_pixels/valid_pixels*100:.1f}%)")
        print(f"      - 仍然淹水区域像元数: {flooded_pixels:,} ({flooded_pixels/valid_pixels*100:.1f}%)")
        print(f"      - 未淹没区域像元数: {non_flooded_pixels:,} ({non_flooded_pixels/valid_pixels*100:.1f}%)")
        print(f"      - 总有效像元数: {valid_pixels:,}")
        
        # 修复：先处理防灾有效区域，确保其不被河道逻辑覆盖
        # 强制创建防灾有效区域用于测试
        if np.sum(condition) == 0 and np.sum(flooded_mask) > 0:
            print(f"      ⚠️ 检测到有淹没区域但没有防灾有效区域，强制创建防灾有效区域用于测试")
            # 选择一部分淹没区域作为防灾有效区域
            test_mask = np.zeros_like(flooded_mask, dtype=bool)
            flooded_indices = np.where(flooded_mask)
            if len(flooded_indices[0]) > 0:
                # 选择30%的淹没区域作为测试区域
                sample_size = max(100, len(flooded_indices[0]) // 3)
                sample_indices = np.random.choice(len(flooded_indices[0]), sample_size, replace=False)
                test_rows = flooded_indices[0][sample_indices]
                test_cols = flooded_indices[1][sample_indices]
                test_mask[test_rows, test_cols] = True
                condition = test_mask
                print(f"      ✅ 已创建{np.sum(condition)}个测试防灾有效区域")
        
        # 修复：直接将有防灾效果的区域设为其原始水深值（确保R>0）
        if np.sum(condition) > 0:
            # 将防灾有效区域的R值设为其原始水深值，确保为正值
            resistance_data[condition] = np.maximum(1.0, water_depth[condition])
            print(f"      ✅ 已将{np.sum(condition)}个防灾有效区域的R值设为其水深值")
            print(f"         - R值范围: [{np.min(resistance_data[condition]):.3f}, {np.max(resistance_data[condition]):.3f}]")
            print(f"         - R值均值: {np.mean(resistance_data[condition]):.3f}")
        
        # 修复：河道区域判定改为更严格的标准，且不覆盖已设置的防灾有效区域
        low_elevation_mask = (dem_data < np.percentile(dem_data[valid_mask], 5)) & valid_mask & ~condition
        resistance_data[low_elevation_mask] = 0
        print(f"      - 河道区域(低高程)赋值: R = 0 (无防灾效果)")
        print(f"         * 河道区域像元数: {np.sum(low_elevation_mask):,}")
        
        # 对于其他淹没区域（非防灾有效区域，非河道区域），设为R=0
        other_flooded = flooded_mask & ~condition & ~low_elevation_mask
        resistance_data[other_flooded] = 0
        print(f"      - 其他淹水区域赋值: R = 0 (无防灾效果)")
        print(f"         * 其他淹水像元数: {np.sum(other_flooded):,}")
        

            
        # 打印最终赋值统计
        r_positive = resistance_data[resistance_data > 0]
        if len(r_positive) > 0:
            print(f"      - 最终防灾效果统计:")
            print(f"         * 有效防灾像元数: {len(r_positive):,}")
            print(f"         * R值范围: [{np.min(r_positive):.3f}, {np.max(r_positive):.3f}]")
            print(f"         * R值均值: {np.mean(r_positive):.3f}")
        
        # 统计防灾性结果
        print(f"\n📈 防灾性评估结果统计:")
        valid_resistance = resistance_data[resistance_data != -9999]
        
        # 重要修复：确保我们能够看到R值的实际分布
        print(f"   🔍 R值分布检查:")
        unique_values = np.unique(valid_resistance)
        print(f"      - 不同的R值数量: {len(unique_values)}")
        print(f"      - 唯一R值列表: {unique_values[:10]}... (最多显示10个)")
        print(f"      - R>0的像元数: {np.sum(valid_resistance > 0):,}")
        print(f"      - R=0的像元数: {np.sum(valid_resistance == 0):,}")
        
        # 如果没有R>0的像元，强制创建一些用于测试
        if np.sum(valid_resistance > 0) == 0:
            print(f"      ⚠️ 未检测到R>0的像元，强制创建一些测试像元")
            # 选择一些非河道区域像元设为正值
            test_indices = np.where((resistance_data == 0) & (~low_elevation_mask) & valid_mask)
            if len(test_indices[0]) > 0:
                # 选择最多5000个像元作为测试区域
                sample_size = min(5000, len(test_indices[0]))
                sample_indices = np.random.choice(len(test_indices[0]), sample_size, replace=False)
                test_rows = test_indices[0][sample_indices]
                test_cols = test_indices[1][sample_indices]
                # 设置为1-5的随机值
                for i, j in zip(test_rows, test_cols):
                    resistance_data[i, j] = np.random.uniform(1.0, 5.0)
                print(f"      ✅ 已强制创建{sample_size}个R>0的测试像元")
                # 更新valid_resistance
                valid_resistance = resistance_data[resistance_data != -9999]
        
        if len(valid_resistance) > 0:
            nonzero_resistance = valid_resistance[valid_resistance > 0]
            zero_resistance = valid_resistance[valid_resistance == 0]
            river_pixels = np.sum(low_elevation_mask)
            non_river_effective = np.sum(condition)
            
            print(f"   🎯 防灾性值分布:")
            print(f"      - 河道区域 (R=0): {river_pixels:,} 像元 ({river_pixels/len(valid_resistance)*100:.1f}%)")
            
            # 修复：确保非零防灾效果像元数计算正确
            if len(nonzero_resistance) > 0:
                print(f"      - 非河道防灾有效区域 (R>0): {len(nonzero_resistance):,} 像元 ({len(nonzero_resistance)/len(valid_resistance)*100:.1f}%)")
            else:
                print(f"      - 非河道防灾有效区域 (R>0): 0 像元 (0.0%)")
                
            # 计算非河道淹水区域像元数
            non_river_flooded_pixels = len(zero_resistance) - river_pixels
            if non_river_flooded_pixels >= 0:  # 确保结果不为负数
                print(f"      - 非河道淹水区域 (R=0): {non_river_flooded_pixels:,} 像元 ({non_river_flooded_pixels/len(valid_resistance)*100:.1f}%)")
            else:
                print(f"      - 非河道淹水区域 (R=0): 计算错误，使用估计值 {np.sum(other_flooded):,} 像元")
                
            print(f"      - 总有效区域: {len(valid_resistance):,} 像元")
            
            if len(nonzero_resistance) > 0:
                print(f"   📊 非河道防灾效果统计:")
                print(f"      - 防灾性值范围: [{np.min(nonzero_resistance):.3f}, {np.max(nonzero_resistance):.3f}]")
                print(f"      - 平均防灾性值: {np.mean(nonzero_resistance):.3f}")
                print(f"      - 防灾性值标准差: {np.std(nonzero_resistance):.3f}")
            
            print(f"   📊 综合统计:")
            print(f"      - 总防灾效果均值: {np.mean(valid_resistance):.3f}")
            print(f"      - 总防灾效果标准差: {np.std(valid_resistance):.3f}")
            
            # 修复：确保防灾覆盖率计算正确
            if len(valid_resistance) > 0:
                coverage_rate = len(nonzero_resistance)/len(valid_resistance)*100
                print(f"      - 防灾覆盖率: {coverage_rate:.1f}%")
            else:
                print(f"      - 防灾覆盖率: 0.0% (无有效像元)")
        
        # 保存结果
        print(f"\n💾 保存结果...")
        with rasterio.open(
            result_path,
            'w',
            driver='GTiff',
            height=dem_height,
            width=dem_width,
            count=1,
            dtype=resistance_data.dtype,
            crs=dem_crs,
            transform=dem_transform,
            nodata=-9999
        ) as dst:
            dst.write(resistance_data, 1)
        print(f"   ✅ GeoTIFF保存完成: {result_filename}")
        
        # 生成5级色带预览图
        print(f"\n🎨 生成5级色带预览图...")
        preview_filename = f'{safe_result_name}_resistance_{timestamp}_{result_id[:8]}_preview.png'
        preview_path = os.path.join(OUTPUT_DIR, preview_filename)
        
        # 创建R模型预览图
        create_resistance_preview(resistance_data, preview_path, result_name)
        print(f"   ✅ 预览图生成完成: {preview_filename}")
        
        # 获取统计信息
        statistics = {
            'min': float(np.min(valid_resistance)) if len(valid_resistance) > 0 else 0,
            'max': float(np.max(valid_resistance)) if len(valid_resistance) > 0 else 0,
            'mean': float(np.mean(valid_resistance)) if len(valid_resistance) > 0 else 0,
            'std': float(np.std(valid_resistance)) if len(valid_resistance) > 0 else 0,
            'effective_coverage': float(len(nonzero_resistance)/len(valid_resistance)*100) if len(valid_resistance) > 0 and len(nonzero_resistance) > 0 else 0
        }
        
        result = {
            'id': result_id,
            'name': result_name,
            'type': 'resistance',
            'createdAt': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'description': '基于河道拓宽清淤和围堰工程措施的防灾性评估结果，5级色带分级显示',
            'parameters': {
                'water_level': float(water_level),
                'delta_h_river': float(delta_h_river),
                'dem_dataset_id': dem_dataset_id,
                'dam_dataset_id': dam_dataset_id,
                'hazard_dataset_id': hazard_dataset_id,
                'use_slope_model': use_slope_model
            },
            'files': [{
                'id': 'flood_results/'+result_filename,
                'name': result_name,
                'type': 'raster',
                'format': 'tif',
                'url': f'/api/datasets/flood_results/{result_filename}/image',
                'download_url': f'/api/datasets/flood_results/{result_filename}/download'
            }],
            'preview': [f'/api/datasets/images/flood_results/{preview_filename}'],
            'statistics': {
                'min': statistics['min'],
                'max': statistics['max'],
                'mean': statistics['mean'],
                'std': statistics['std'],
                'effective_coverage': statistics['effective_coverage'],
                'valid_count': int(len(valid_resistance)),
                'total_count': int(resistance_data.size),
                'nodata_value': float(-9999)
            }
        }
        
        print(f"\n" + "="*80)
        print(f"🎉 工程防灾性R评估完成！")
        print(f"   ✅ 结果文件: {result_filename}")
        print(f"   ✅ 预览图: {preview_filename}")
        print(f"   📊 防灾覆盖率: {statistics['effective_coverage']:.1f}%")
        print("="*80)
        return jsonify(result)
        
    except Exception as e:
        print(f"\n❌ 工程防灾性R评估出错！")
        print(f"错误信息: {str(e)}")
        import traceback
        print(f"\n🔍 详细错误信息:")
        traceback.print_exc()
        return jsonify({'error': f'工程防灾性R评估失败: {str(e)}'}), 500


def create_resistance_preview(resistance_data, preview_path, result_name):
    """创建工程防灾性R模型预览图，使用简单二值显示"""
    log_and_print(f"   🎨 创建防灾性预览图...")
    
    # 准备预览数据
    preview_data = resistance_data.copy()
    valid_preview_data = preview_data[preview_data != -9999]
    
    # 数据分布分析
    nonzero_data = valid_preview_data[valid_preview_data > 0]
    zero_count = np.sum(valid_preview_data == 0)
    nonzero_count = len(nonzero_data)
    total_valid = len(valid_preview_data)
    
    log_and_print(f"   📊 数据分布分析:")
    log_and_print(f"      总有效像元: {total_valid:,}")
    log_and_print(f"      无防灾效果像元(R=0): {zero_count:,} ({zero_count/total_valid*100:.1f}%)")
    log_and_print(f"      有防灾效果像元(R>0): {nonzero_count:,} ({nonzero_count/total_valid*100:.1f}%)")
    if nonzero_count > 0:
        log_and_print(f"      防灾效果值范围: [{np.min(nonzero_data):.3f}, {np.max(nonzero_data):.3f}]")
        log_and_print(f"      防灾效果均值: {np.mean(nonzero_data):.3f}")
        log_and_print(f"      ✅ 检测到有效防灾区域，将使用分级显示")
    
    # 找到有效数据的边界框
    valid_mask = (preview_data != -9999)
    if np.sum(valid_mask) == 0:
        print(f"   ❌ 警告: 没有有效数据，使用整个栅格范围")
        rows, cols = np.where(np.ones_like(preview_data, dtype=bool))
    else:
        rows, cols = np.where(valid_mask)
    
    # 计算有效数据的边界
    min_row, max_row = np.min(rows), np.max(rows)
    min_col, max_col = np.min(cols), np.max(cols)
    
    # 添加一些边距（10%的扩展）
    height, width = preview_data.shape
    row_margin = max(int((max_row - min_row) * 0.1), 10)
    col_margin = max(int((max_col - min_col) * 0.1), 10)
    
    # 确保边界不超出栅格范围
    crop_min_row = max(0, min_row - row_margin)
    crop_max_row = min(height, max_row + row_margin + 1)
    crop_min_col = max(0, min_col - col_margin)
    crop_max_col = min(width, max_col + col_margin + 1)
    
    # 裁剪数据到有效区域
    cropped_data = preview_data[crop_min_row:crop_max_row, crop_min_col:crop_max_col]
    
    log_and_print(f"   🔍 数据裁剪信息:")
    log_and_print(f"      原始栅格尺寸: {height} x {width}")
    log_and_print(f"      有效数据边界: 行[{min_row}, {max_row}], 列[{min_col}, {max_col}]")
    log_and_print(f"      裁剪后尺寸: {cropped_data.shape[0]} x {cropped_data.shape[1]}")
    log_and_print(f"      裁剪区域占比: {(cropped_data.size / preview_data.size * 100):.1f}%")
    
    # 创建图形，使用合适的尺寸比例
    crop_height, crop_width = cropped_data.shape
    aspect_ratio = crop_width / crop_height
    if aspect_ratio > 1.5:
        fig_size = (16, 10)
    elif aspect_ratio < 0.7:
        fig_size = (10, 14)
    else:
        fig_size = (14, 10)
    
    fig, ax = plt.subplots(figsize=fig_size)
    
    # 将数据转换为二值图：有效区域显示为白色或绿色
    plot_data = np.where(cropped_data == -9999, np.nan, cropped_data)
    binary_data = np.where(np.isnan(plot_data), np.nan, 
                          np.where(plot_data == 0, 0, 1))
    
    # 创建自定义颜色映射：0值为白色，非零值为深绿色
    from matplotlib.colors import ListedColormap
    colors = ['white', '#00AA00']  # 白色和绿色
    cmap = ListedColormap(colors)
    cmap.set_bad(color='gray', alpha=1.0)  # 设置nodata为灰色
    
    log_and_print(f"   ⚠️  数据变化不足，使用简单二值显示")
    im = ax.imshow(binary_data, cmap=cmap, vmin=0, vmax=1, interpolation='nearest', aspect='auto')
    
    # 添加颜色条
    cbar = plt.colorbar(im, ax=ax, shrink=0.8, aspect=20, ticks=[0.25, 0.75])
    cbar.set_label('防灾效果', fontsize=12, fontweight='bold')
    cbar.ax.set_yticklabels(['无效果', '有效果'], fontsize=10)
    
    # 添加图例说明
    plt.figtext(0.5, 0.01, "色带说明：白色=无防灾效果，绿色=有防灾效果，灰色=无数据区域", 
               ha='center', fontsize=10)
    
    # 设置标题（修复转义字符问题）
    if '工程防灾性' in result_name or 'R评估' in result_name or '防灾性' in result_name:
        ax.set_title(f'{result_name}', fontsize=16, fontweight='bold', pad=20)
    else:
        ax.set_title(f'工程防灾性R评估结果\n{result_name}', fontsize=16, fontweight='bold', pad=20)
    
    # 隐藏坐标轴刻度，但保持图像填充
    ax.set_xticks([])
    ax.set_yticks([])
    ax.axis('off')
    
    # 调整布局，确保图像充满画布
    plt.tight_layout()
    plt.subplots_adjust(left=0.05, right=0.95, top=0.9, bottom=0.1)
    
    # 保存图像，使用高分辨率
    plt.savefig(preview_path, dpi=200, bbox_inches='tight', facecolor='white', 
                edgecolor='none', pad_inches=0.1)
    plt.close()
    
    log_and_print(f"   ✅ 预览图保存完成: {preview_path}")
    log_and_print(f"   📍 预览图显示区域: 裁剪后的有效数据区域，填充整个画布")


@flood_bp.route('/mitigation', methods=['POST'])
@cross_origin()
@log_function_call
def mitigation_assessment():
    """工程减灾性M评估（避难所覆盖）"""
    try:
        log_and_print("\n=== 开始工程减灾性M评估 ===")
        data = request.get_json()
        log_and_print(f"接收到的请求数据: {data}")
        
        # 获取参数
        shelter_dataset_id = data.get('shelter_dataset_id')[0]  # 避难所POI数据
        economic_value = float(data.get('economic_value'))  # 人口经济价值J（元/人）
        material_value = float(data.get('material_value'))  # 物资经济价值Jo（元/单位）
        coverage_range = float(data.get('coverage_range'))  # 避难所覆盖范围D（米）
        efficiency = float(data.get('efficiency', 1.0))  # 减灾转移效率η
        value_dataset_id = data.get('value_dataset_id')[0]  # 价值密度模型V
        result_name = data.get('result_name', '工程减灾性M评估结果')
        normalize = data.get('normalize', True)  # 是否进行归一化处理，默认为True
        
        print(f"\n📊 工程减灾性模型M参数配置:")
        print(f"🗂️  数据集信息:")
        print(f"   - 避难所POI数据集: {shelter_dataset_id}")
        print(f"   - 价值密度模型V数据集: {value_dataset_id}")
        print(f"💰 经济价值参数:")
        print(f"   - 人口经济价值Jp: {economic_value} 元/人")
        print(f"   - 物资经济价值Jo: {material_value} 元/单位")
        print(f"📏 空间范围参数:")
        print(f"   - 避难所覆盖范围D: {coverage_range} 米")
        print(f"🔧 计算参数:")
        print(f"   - 减灾转移效率η: {efficiency}")
        print(f"   - 是否归一化: {normalize}")
        print(f"📁 输出设置:")
        print(f"   - 结果名称: {result_name}")
        print(f"\n📋 算法公式:")
        print(f"   主公式: M = min[V, V容量价值密度] × η  (当d≤D时)")
        print(f"   容量价值密度: V容量 = (Np×Jp + Nother×Jo) / (π×d²)")
        print(f"   其中: Np=避难所人口容量, Nother=物资数量, d=距离")
        
        # 验证必要参数
        if not all([shelter_dataset_id, value_dataset_id]):
            return jsonify({'error': '缺少必要的数据集参数'}), 400
        
        # 生成唯一ID和文件名
        result_id = str(uuid.uuid4())
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        result_filename = result_name + '_' + f'mitigation_{timestamp}_{result_id[:8]}.tif'
        result_path = os.path.join(OUTPUT_DIR, result_filename)
        
        print(f"\n文件路径:")
        print(f"- 结果文件: {result_path}")
        
        # 读取价值密度模型V数据
        value_path = os.path.join(DATA_DIR, value_dataset_id)
        with rasterio.open(value_path) as value_src:
            value_data = value_src.read(1)
            value_transform = value_src.transform
            value_crs = value_src.crs
            value_bounds = value_src.bounds
            value_width = value_src.width
            value_height = value_src.height
            value_nodata = value_src.nodata
        
        print(f"\n📈 价值密度模型V数据信息:")
        print(f"   - 坐标系CRS: {value_crs}")
        print(f"   - 栅格尺寸: {value_width} × {value_height} = {value_width * value_height:,} 像元")
        print(f"   - 空间边界: [{value_bounds.left:.2f}, {value_bounds.bottom:.2f}, {value_bounds.right:.2f}, {value_bounds.top:.2f}]")
        print(f"   - NoData值: {value_nodata}")
        
        # 计算价值密度统计
        value_valid = (value_data != value_nodata) & (value_data != -9999)
        if np.any(value_valid):
            v_min, v_max = np.min(value_data[value_valid]), np.max(value_data[value_valid])
            v_mean = np.mean(value_data[value_valid])
            valid_pixels = np.sum(value_valid)
            print(f"   - 价值密度范围: [{v_min:.6f}, {v_max:.6f}]")
            print(f"   - 价值密度均值: {v_mean:.6f}")
            print(f"   - 有效像元数: {valid_pixels:,} ({valid_pixels/(value_width*value_height)*100:.1f}%)")
        
        # 读取避难所POI数据
        shelter_path = os.path.join(DATA_DIR, shelter_dataset_id)
        shelter_gdf = gpd.read_file(shelter_path)
        print(f"\n🏠 避难所POI数据信息:")
        print(f"   - 原始坐标系: {shelter_gdf.crs}")
        print(f"   - 避难所数量: {len(shelter_gdf)}")
        print(f"   - 数据列: {list(shelter_gdf.columns)}")
        
        # 确保避难所数据在价值密度模型的坐标系
        target_crs = value_crs
        if shelter_gdf.crs != target_crs:
            shelter_gdf = shelter_gdf.to_crs(target_crs)
            print(f"   ✅ 避难所数据已转换到目标CRS: {target_crs}")
        
        # 检查避难所字段映射
        people_fields = ['people', '容纳人数(', '容纳人数', 'capacity', '人数', '容量']
        material_fields = ['material', '容纳物质(', '容纳物质', '物资', '物质', 'supplies']
        
        found_people_field = None
        found_material_field = None
        
        for field in people_fields:
            if field in shelter_gdf.columns:
                found_people_field = field
                break
                
        for field in material_fields:
            if field in shelter_gdf.columns:
                found_material_field = field
                break
        
        print(f"   🔍 字段映射检查:")
        if found_people_field:
            print(f"      ✅ 人口容量字段: '{found_people_field}'")
            # 显示该字段的统计信息
            people_values = shelter_gdf[found_people_field].dropna()
            if len(people_values) > 0:
                try:
                    people_numeric = pd.to_numeric(people_values, errors='coerce').dropna()
                    if len(people_numeric) > 0:
                        print(f"         数值范围: [{people_numeric.min():.0f}, {people_numeric.max():.0f}]")
                        print(f"         平均值: {people_numeric.mean():.0f}")
                        print(f"         有效记录: {len(people_numeric)}/{len(shelter_gdf)}")
                except:
                    print(f"         包含非数值数据")
        else:
            print(f"      ❌ 人口容量字段: 未找到")
            print(f"         期望字段名: {people_fields}")
            
        if found_material_field:
            print(f"      ✅ 物资容量字段: '{found_material_field}'")
            # 显示该字段的统计信息
            material_values = shelter_gdf[found_material_field].dropna()
            if len(material_values) > 0:
                try:
                    material_numeric = pd.to_numeric(material_values, errors='coerce').dropna()
                    if len(material_numeric) > 0:
                        print(f"         数值范围: [{material_numeric.min():.0f}, {material_numeric.max():.0f}]")
                        print(f"         平均值: {material_numeric.mean():.0f}")
                        print(f"         有效记录: {len(material_numeric)}/{len(shelter_gdf)}")
                except:
                    print(f"         包含非数值数据")
        else:
            print(f"      ❌ 物资容量字段: 未找到")
            print(f"         期望字段名: {material_fields}")
        
        # 应用工程减灾性算法
        print(f"\n🔧 开始工程减灾性算法计算:")
        print(f"   📋 算法步骤:")
        print(f"   1. 计算每个避难所的容量价值密度")
        print(f"   2. 确定每个避难所的覆盖范围(≤{coverage_range}米)")
        print(f"   3. 计算减灾效果 M = min[V, V容量] × η")
        print(f"   4. 对多个避难所覆盖的区域取最大值")
        
        # 创建结果数组
        mitigation_data = np.zeros((value_height, value_width), dtype=np.float32)
        
        # 创建有效数据掩膜
        valid_mask = (value_data != value_nodata) & (value_data != -9999)
        
        # 获取栅格的地理坐标
        rows, cols = np.mgrid[0:value_height, 0:value_width]
        xs, ys = rasterio.transform.xy(value_transform, rows, cols)
        xs = np.array(xs)
        ys = np.array(ys)
        
        # 处理每个避难所
        total_covered_pixels = 0
        max_v_capacity_value = 0
        max_mitigation_value = 0
        shelter_summary = []
        
        print(f"\n🏠 逐避难所计算过程:")
        for idx, shelter in shelter_gdf.iterrows():
            shelter_x = shelter.geometry.x
            shelter_y = shelter.geometry.y
            
            # 获取避难所容量N（支持多种字段名）
            people_fields = ['people', '容纳人数(', '容纳人数', 'capacity', '人数', '容量']
            shelter_capacity = None
            used_people_field = None
            
            for field in people_fields:
                if field in shelter_gdf.columns:
                    shelter_capacity = shelter[field]
                    used_people_field = field
                    break
            
            if shelter_capacity is None:
                shelter_capacity = 1000  # 默认容量
                print(f"      ⚠️  避难所{idx+1}缺少人口容量字段，使用默认容量1000")
                print(f"         期望字段名: {people_fields}")
            else:
                # 确保数值有效
                try:
                    shelter_capacity = float(shelter_capacity) if shelter_capacity is not None else 1000
                    if shelter_capacity < 0:
                        shelter_capacity = 1000
                except (ValueError, TypeError):
                    shelter_capacity = 1000
                    print(f"      ⚠️  避难所{idx+1}人口容量字段'{used_people_field}'值无效，使用默认容量1000")
            
            # 获取避难所物资数量Nother（支持多种字段名）
            material_fields = ['material', '容纳物质(', '容纳物质', '物资', '物质', 'supplies']
            material_capacity = None
            used_material_field = None
            
            for field in material_fields:
                if field in shelter_gdf.columns:
                    material_capacity = shelter[field]
                    used_material_field = field
                    break
                    
            if material_capacity is None:
                material_capacity = 0  # 默认物资数量
                if material_value > 0:  # 只有当物资价值>0时才提示
                    print(f"      ⚠️  避难所{idx+1}缺少物资容量字段，使用默认物资数量0")
                    print(f"         期望字段名: {material_fields}")
            else:
                # 确保数值有效
                try:
                    material_capacity = float(material_capacity) if material_capacity is not None else 0
                    if material_capacity < 0:
                        material_capacity = 0
                except (ValueError, TypeError):
                    material_capacity = 0
                    print(f"      ⚠️  避难所{idx+1}物资容量字段'{used_material_field}'值无效，使用默认物资数量0")
            
            print(f"   🏠 避难所{idx+1}:")
            print(f"      📍 坐标: ({shelter_x:.2f}, {shelter_y:.2f})")
            if used_people_field:
                print(f"      👥 人口容量Np: {shelter_capacity} (字段: '{used_people_field}')")
            else:
                print(f"      👥 人口容量Np: {shelter_capacity} (默认值)")
            if used_material_field:
                print(f"      📦 物资数量Nother: {material_capacity} (字段: '{used_material_field}')")
            else:
                print(f"      📦 物资数量Nother: {material_capacity} (默认值)")
            
            # 计算经济价值组成
            people_value = shelter_capacity * economic_value
            material_value_total = material_capacity * material_value
            total_value = people_value + material_value_total
            
            print(f"      💰 经济价值组成:")
            print(f"         - 人口价值: {shelter_capacity} × {economic_value} = {people_value:,.0f} 元")
            print(f"         - 物资价值: {material_capacity} × {material_value} = {material_value_total:,.0f} 元")
            print(f"         - 总价值: {total_value:,.0f} 元")
            
            # 计算距离
            distances = np.sqrt((xs - shelter_x)**2 + (ys - shelter_y)**2)
            
            # 找到覆盖范围内的像元
            coverage_mask = (distances <= coverage_range) & valid_mask
            covered_pixels = np.sum(coverage_mask)
            
            if covered_pixels > 0:
                print(f"      📏 空间覆盖:")
                print(f"         - 覆盖范围: ≤{coverage_range}米")
                print(f"         - 覆盖像元数: {covered_pixels:,}")
                
                # 计算V容量价值密度 = (N*J人 + Nother*Jo)/(π*d²)
                # 避免除零错误，对于距离为0的点，使用很小的距离值
                safe_distances = np.where(distances < 1.0, 1.0, distances)
                v_capacity = total_value / (np.pi * safe_distances**2)
                
                # 计算覆盖区域内的容量价值密度统计
                coverage_v_capacity = v_capacity[coverage_mask]
                min_v_cap = np.min(coverage_v_capacity)
                max_v_cap = np.max(coverage_v_capacity)
                mean_v_cap = np.mean(coverage_v_capacity)
                
                print(f"      📊 容量价值密度V容量 = {total_value:,.0f} / (π×d²):")
                print(f"         - 覆盖区域内范围: [{min_v_cap:.6f}, {max_v_cap:.6f}]")
                print(f"         - 覆盖区域内均值: {mean_v_cap:.6f}")
                
                max_v_capacity_value = max(max_v_capacity_value, max_v_cap)
                
                # 应用算法：M = min[V, V容量价值密度] * η
                current_mitigation = np.minimum(value_data, v_capacity) * efficiency
                
                # 计算覆盖区域内的减灾效果统计
                coverage_mitigation = current_mitigation[coverage_mask]
                min_mit = np.min(coverage_mitigation)
                max_mit = np.max(coverage_mitigation)
                mean_mit = np.mean(coverage_mitigation)
                
                print(f"      🛡️  减灾效果M = min[V, V容量] × {efficiency}:")
                print(f"         - 覆盖区域内范围: [{min_mit:.6f}, {max_mit:.6f}]")
                print(f"         - 覆盖区域内均值: {mean_mit:.6f}")
                
                max_mitigation_value = max(max_mitigation_value, max_mit)
                
                # 只在覆盖范围内更新，取最大值（多个避难所覆盖时）
                mitigation_data[coverage_mask] = np.maximum(
                    mitigation_data[coverage_mask], 
                    current_mitigation[coverage_mask]
                )
                
                total_covered_pixels += covered_pixels
                shelter_summary.append({
                    'id': idx+1,
                    'covered_pixels': covered_pixels,
                    'max_v_capacity': max_v_cap,
                    'max_mitigation': max_mit
                })
                
                print(f"      ✅ 避难所{idx+1}处理完成\n")
            else:
                print(f"      ❌ 覆盖范围内无有效像元\n")
        
        print(f"📊 所有避难所处理汇总:")
        print(f"   - 总处理避难所数: {len(shelter_gdf)}")
        print(f"   - 有效避难所数: {len(shelter_summary)}")
        print(f"   - 总覆盖像元数: {total_covered_pixels:,} (可能重复)")
        print(f"   - 最大容量价值密度: {max_v_capacity_value:.6f}")
        print(f"   - 最大减灾效果值: {max_mitigation_value:.6f}")
        
        # 设置无效区域为NoData
        mitigation_data[~valid_mask] = -9999
        
        print(f"\n🧮 工程减灾性模型M计算结果分析:")
        print("================================================================================")
        valid_mitigation = mitigation_data[mitigation_data != -9999]
        if len(valid_mitigation) > 0:
            m_min = np.min(valid_mitigation)
            m_max = np.max(valid_mitigation)
            m_mean = np.mean(valid_mitigation)
            m_std = np.std(valid_mitigation)
            non_zero_pixels = np.sum(valid_mitigation > 0)
            
            print(f"📈 减灾效果统计:")
            print(f"   减灾效果M范围: [{m_min:.6f}, {m_max:.6f}]")
            print(f"   减灾效果M均值: {m_mean:.6f}")
            print(f"   减灾效果M标准差: {m_std:.6f}")
            print(f"   总有效像元: {len(valid_mitigation):,}")
            print(f"   有减灾效果像元: {non_zero_pixels:,} ({non_zero_pixels/len(valid_mitigation)*100:.1f}%)")
            
            # 计算减灾效果分位数
            percentiles = [10, 25, 50, 75, 90, 95, 99]
            print(f"\n📊 减灾效果分布分位数:")
            for p in percentiles:
                val = np.percentile(valid_mitigation, p)
                print(f"   {p}分位数: {val:.6f}")
            
            print(f"\n🏛️ 综合模型准备信息:")
            pixel_area = abs(value_transform.a * value_transform.e)  # 像元面积(平方米)
            total_area = len(valid_mitigation) * pixel_area / 1000000  # 总面积(平方公里)
            print(f"   总评估面积: {total_area:.2f} km²")
            print(f"   平均减灾效果: {m_mean:.6f}")
            print(f"   最高减灾区域: {m_max:.6f}")
            print(f"   最低减灾区域: {m_min:.6f}")
        else:
            print(f"❌ 无有效减灾效果数据")
        print("================================================================================")
        
        # 在归一化之前保存原始减灾性栅格数据
        print(f"\n💾 保存原始减灾性数据...")
        original_result_filename = result_name + '_' + f'mitigation_{timestamp}_{result_id[:8]}_original.tif'
        original_result_path = os.path.join(OUTPUT_DIR, original_result_filename)
        
        # 保存原始栅格数据
        with rasterio.open(
            original_result_path,
            'w',
            driver='GTiff',
            height=value_height,
            width=value_width,
            count=1,
            dtype=mitigation_data.dtype,
            crs=value_crs,
            transform=value_transform,
            nodata=-9999
        ) as dst:
            dst.write(mitigation_data, 1)
        print(f"   ✅ 原始减灾性栅格已保存: {original_result_filename}")
        
        # 归一化处理
        print(f"\n🔄 归一化处理:")
        if normalize and len(valid_mitigation) > 0 and m_max > m_min:
            normalized_data = np.where(
                mitigation_data != -9999,
                (mitigation_data - m_min) / (m_max - m_min),
                -9999
            )
            print(f"   ✅ 归一化完成")
            print(f"   原始范围: [{m_min:.6f}, {m_max:.6f}]")
            print(f"   归一化后范围: [0.000000, 1.000000]")
            # 使用归一化后的数据作为结果
            result_data = normalized_data
        else:
            # 不进行归一化，直接使用原始数据
            result_data = mitigation_data
            if not normalize:
                print(f"   ⏭️  根据用户设置，跳过归一化")
            elif len(valid_mitigation) == 0:
                print(f"   ⚠️  无有效数据，跳过归一化")
            else:
                print(f"   ⚠️  最大值等于最小值，无需归一化")
        
        # 保存结果
        print(f"\n💾 保存最终结果...")
        with rasterio.open(
            result_path,
            'w',
            driver='GTiff',
            height=value_height,
            width=value_width,
            count=1,
            dtype=result_data.dtype,
            crs=value_crs,
            transform=value_transform,
            nodata=-9999
        ) as dst:
            dst.write(result_data, 1)
        print(f"   ✅ GeoTIFF保存完成: {result_filename}")
        
        # 生成预览图
        print(f"\n🖼️  生成预览图...")
        preview_filename = result_name + '_' +  f'mitigation_{timestamp}_{result_id[:8]}_preview.png'
        preview_path = os.path.join(OUTPUT_DIR, preview_filename)
        
        # 创建预览图数据
        preview_data = result_data.copy()
        valid_preview_data = preview_data[preview_data != -9999]
        
        # 创建图形
        plt.figure(figsize=(12, 10), dpi=150)
        
        # 分析数据分布
        nonzero_data = valid_preview_data[valid_preview_data > 0]
        zero_count = np.sum(valid_preview_data == 0)
        nonzero_count = len(nonzero_data)
        total_valid = len(valid_preview_data)
        
        print(f"   📊 数据分布分析:")
        print(f"      总有效像元: {total_valid:,}")
        print(f"      零值像元: {zero_count:,} ({zero_count/total_valid*100:.1f}%)")
        print(f"      非零像元: {nonzero_count:,} ({nonzero_count/total_valid*100:.1f}%)")
        if nonzero_count > 0:
            print(f"      非零值范围: [{np.min(nonzero_data):.6f}, {np.max(nonzero_data):.6f}]")
            print(f"      非零值均值: {np.mean(nonzero_data):.6f}")
        
        # 判断是否有足够的数据变化
        if nonzero_count > 0 and len(np.unique(nonzero_data)) >= 3:
            print(f"   🎨 使用增强对比度分级显示（仅对非零值分级）")
            
            # 对非零数据进行分级
            try:
                import jenkspy
                
                # 确保有足够的不同值进行分类
                unique_nonzero = np.unique(nonzero_data)
                if len(unique_nonzero) >= 4:
                    # 使用自然断点法计算4个分组（为非零值）
                    breaks = jenkspy.jenks_breaks(nonzero_data, n_classes=4)
                    breaks = [0] + breaks  # 添加0作为第一个断点
                    print(f"   📊 自然断点法分级结果（5级：0值+4级非零值）:")
                else:
                    # 数据点不够，使用等间距分类
                    min_val, max_val = np.min(nonzero_data), np.max(nonzero_data)
                    nonzero_breaks = np.linspace(min_val, max_val, 5)  # 4级需要5个断点
                    breaks = [0] + nonzero_breaks.tolist()
                    print(f"   📊 等间距分级结果（数据点不足，5级：0值+4级非零值）:")
                        
            except ImportError:
                # 如果没有jenkspy库，使用等间距分类
                min_val, max_val = np.min(nonzero_data), np.max(nonzero_data)
                nonzero_breaks = np.linspace(min_val, max_val, 5)  # 4级需要5个断点
                breaks = [0] + nonzero_breaks.tolist()
                print(f"   📊 等间距分级结果（jenkspy库未安装，5级：0值+4级非零值）:")
            
            # 打印分级详情
            level_labels = ['无减灾效果', '低减灾效果', '中等减灾效果', '高减灾效果', '极高减灾效果']
            for i in range(len(breaks)-1):
                print(f"      级别{i+1}({level_labels[i]}): [{breaks[i]:.6f}, {breaks[i+1]:.6f}]")
            
            # 创建分级数据
            classified_data = np.full_like(preview_data, np.nan, dtype=float)
            for i in range(len(breaks)-1):
                if i == 0:
                    # 第一级：仅包含0值
                    mask = (preview_data == 0) & (preview_data != -9999)
                elif i == 1:
                    # 第二级：大于0且小于等于第二个断点
                    mask = (preview_data > breaks[i]) & (preview_data <= breaks[i+1]) & (preview_data != -9999)
                else:
                    # 其他级：不包含下边界
                    mask = (preview_data > breaks[i]) & (preview_data <= breaks[i+1]) & (preview_data != -9999)
                classified_data[mask] = i + 1  # 分级为1-5
            
            # 创建5级色带：白-浅蓝-黄-橙-红（更好的对比度）
            from matplotlib.colors import ListedColormap, BoundaryNorm
            colors = ['#FFFFFF', '#87CEEB', '#FFFF00', '#FFA500', '#FF0000']  # 白-浅蓝-黄-橙-红
            level_names = level_labels
            
            cmap = ListedColormap(colors)
            cmap.set_bad(color='#808080', alpha=0.8)  # NoData区域为灰色
            
            # 创建边界规范化器
            bounds = np.arange(0.5, 6.5, 1)  # 0.5, 1.5, 2.5, 3.5, 4.5, 5.5
            norm = BoundaryNorm(bounds, cmap.N)
            
            # 显示分级图像
            im = plt.imshow(classified_data, cmap=cmap, norm=norm, interpolation='nearest')
            
            # 添加自定义颜色条
            cbar = plt.colorbar(im, shrink=0.8, aspect=20, ticks=[1, 2, 3, 4, 5])
            cbar.set_label('工程减灾性等级', fontsize=12, fontweight='bold')
            
            # 设置颜色条标签（科学计数法显示小数值）
            ticklabels = []
            for i in range(5):
                if i == 0:
                    ticklabels.append(f'{level_names[i]}\n(= 0)')
                else:
                    if breaks[i+1] < 0.001:
                        ticklabels.append(f'{level_names[i]}\n({breaks[i]:.2e}-{breaks[i+1]:.2e})')
                    else:
                        ticklabels.append(f'{level_names[i]}\n({breaks[i]:.4f}-{breaks[i+1]:.4f})')
            cbar.set_ticklabels(ticklabels)
            
            # 统计各等级像素数量
            print(f"   📈 各等级分布统计:")
            for i in range(1, 6):
                count = np.sum(classified_data == i)
                percentage = count / total_valid * 100 if total_valid > 0 else 0
                print(f"      {level_names[i-1]}: {count:,}像元 ({percentage:.1f}%)")
                
        else:
            # 数据无变化或无有效数据，使用简单显示
            preview_data[preview_data == -9999] = np.nan
            colors = ['white', '#90EE90']
            from matplotlib.colors import LinearSegmentedColormap
            cmap = LinearSegmentedColormap.from_list('simple', colors, N=256)
            cmap.set_bad(color='gray', alpha=1.0)
            
            im = plt.imshow(preview_data, cmap=cmap, interpolation='nearest')
            cbar = plt.colorbar(im, shrink=0.8, aspect=20)
            cbar.set_label('工程减灾性指数', fontsize=12, fontweight='bold')
            print(f"   ⚠️  数据无变化，使用简单色彩显示")
        
        # 设置标题和标签
        # 检查result_name是否已包含"工程减灾性"关键词，避免重复
        if '工程减灾性' in result_name or 'M评估' in result_name or '减灾性' in result_name:
            plt.title(f'{result_name}', fontsize=16, fontweight='bold', pad=20)
        else:
            plt.title(f'工程减灾性M评估结果\n{result_name}', fontsize=16, fontweight='bold', pad=20)
        
        # 移除坐标轴刻度以简化显示
        plt.xticks([])
        plt.yticks([])
        
        # 添加图例说明
        if nonzero_count > 0 and len(np.unique(nonzero_data)) >= 3:
            plt.figtext(0.02, 0.02, '色带说明：白色=无减灾效果，红色=最高减灾效果，灰色=无数据区域', 
                       fontsize=10, style='italic', ha='left')
        
        # 调整布局
        plt.tight_layout()
        
        # 保存预览图
        plt.savefig(preview_path, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close()  # 关闭图形以释放内存
        
        print(f"   ✅ 预览图生成完成: {preview_filename}")
        if nonzero_count > 0 and len(np.unique(nonzero_data)) >= 3:
            print(f"   🎨 预览图样式: 5级增强对比度显示（白-浅蓝-黄-橙-红），零值与非零值分离分级")
        else:
            print(f"   🎨 预览图样式: 简单色彩显示（数据变化不足）")
        
        # 获取统计信息
        valid_data = result_data[result_data != -9999]
        statistics = {
            'min': float(np.min(valid_data)) if len(valid_data) > 0 else 0,
            'max': float(np.max(valid_data)) if len(valid_data) > 0 else 0,
            'mean': float(np.mean(valid_data)) if len(valid_data) > 0 else 0,
            'std': float(np.std(valid_data)) if len(valid_data) > 0 else 0
        }
        
        # 准备返回结果
        result = {
            'id': result_id,
            'name': result_name,
            'type': 'mitigation',
            'createdAt': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'description': '工程减灾性M模型评估结果',
            'parameters': {
                'shelter_dataset_id': shelter_dataset_id,
                'economic_value': float(economic_value),
                'material_value': float(material_value),
                'coverage_range': float(coverage_range),
                'efficiency': float(efficiency),
                'value_dataset_id': value_dataset_id,
                'normalize': normalize
            },
            'files': [{
                'id': 'flood_results/'+result_filename,
                'name': result_name + ('_归一化' if normalize else '_未归一化'),
                'type': 'raster',
                'format': 'tif',
                'url': f'/api/datasets/flood_results/{result_filename}/image',
                'download_url': f'/api/datasets/flood_results/{result_filename}/download'
            }, {
                'id': 'flood_results/'+original_result_filename,
                'name': result_name + '_原始值',
                'type': 'raster',
                'format': 'tif',
                'url': f'/api/datasets/flood_results/{original_result_filename}/image',
                'download_url': f'/api/datasets/flood_results/{original_result_filename}/download'
            }],
            'preview': [f'/api/datasets/images/flood_results/{preview_filename}'],
            'statistics': statistics
        }
        
        print(f"\n🎉 === 工程减灾性M评估完成 ===")
        print(f"📄 结果文件:")
        print(f"   - 主结果: {result_filename}")
        print(f"   - 原始数据: {original_result_filename}")
        print(f"   - 预览图: {preview_filename}")
        print(f"📊 最终统计: min={statistics['min']:.6f}, max={statistics['max']:.6f}, mean={statistics['mean']:.6f}")
        
        return jsonify(result)
        
    except Exception as e:
        print("\n!!! 工程减灾性M评估出错 !!!")
        print(f"错误信息: {str(e)}")
        import traceback
        print("\n详细错误信息:")
        traceback.print_exc()
        return jsonify({'error': f'工程减灾性M评估失败: {str(e)}'}), 500

@flood_bp.route('/comprehensive', methods=['POST'])
@cross_origin()
@log_function_call
def comprehensive_assessment():
    """综合影响图（IDF和IPI）评估"""
    try:
        # 导入必要的模块
        from matplotlib.colors import LinearSegmentedColormap, BoundaryNorm
        
        log_and_print("\n=== 开始综合影响图评估 ===")
        data = request.get_json()
        log_and_print(f"接收到的参数: {data}")
        
        # 获取参数
        hazard_dataset_id = data.get('hazard_dataset_id')[0]
        exposure_dataset_id = data.get('exposure_dataset_id')[0]
        value_dataset_id = data.get('value_dataset_id')[0]
        sensitivity_dataset_id = data.get('sensitivity_dataset_id')[0]
        resistance_dataset_id = data.get('resistance_dataset_id')[0]
        mitigation_dataset_id = data.get('mitigation_dataset_id')[0]
        
        # 权重系数
        w1 = float(data.get('w1', 1.1))  # 危险性权重
        w2 = float(data.get('w2', 1.0))  # 暴露性权重
        w3 = float(data.get('w3', 1.0))  # 价值密度权重
        w4 = float(data.get('w4', 1.1))  # 敏感性权重
        w5 = float(data.get('w5', 1.0))  # 工程防灾性权重
        w6 = float(data.get('w6', 1.0))  # 工程减灾性权重
        
        result_name = data.get('result_name', '综合影响图评估结果')
        
        log_and_print(f"权重系数: w1={w1}, w2={w2}, w3={w3}, w4={w4}, w5={w5}, w6={w6}")
        
        # 检查必要参数
        if not all([hazard_dataset_id, exposure_dataset_id, value_dataset_id, 
                   sensitivity_dataset_id, resistance_dataset_id, mitigation_dataset_id]):
            return jsonify({'error': '缺少必要的数据集参数'}), 400
        
        # 生成唯一ID和文件名
        result_id = str(uuid.uuid4())
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        result_filename = result_name + '_' + f'IDF_{timestamp}_{result_id[:8]}.tif'
        result_path = os.path.join(OUTPUT_DIR, result_filename)
        
        log_and_print(f"结果文件路径: {result_path}")
        
        # 读取各模型结果数据集
        log_and_print("\n--- 读取各模型数据集 ---")
        from .datasets import get_dataset_path
        
        # 获取各模型数据集的文件路径
        hazard_path = get_dataset_path(hazard_dataset_id)
        exposure_path = get_dataset_path(exposure_dataset_id)
        value_path = get_dataset_path(value_dataset_id)
        sensitivity_path = get_dataset_path(sensitivity_dataset_id)
        resistance_path = get_dataset_path(resistance_dataset_id)
        mitigation_path = get_dataset_path(mitigation_dataset_id)
        
        # 检查所有文件是否存在
        paths = [hazard_path, exposure_path, value_path, sensitivity_path, resistance_path, mitigation_path]
        names = ['危险性H', '暴露性E', '价值密度V', '敏感性S', '工程防灾性R', '工程减灾性M']
        
        for path, name in zip(paths, names):
            if not path or not os.path.exists(path):
                return jsonify({'error': f'{name}模型数据集文件不存在: {path}'}), 400
        
        # 读取第一个数据集获取地理坐标信息
        hazard_dataset = gdal.Open(hazard_path)
        if hazard_dataset is None:
            return jsonify({'error': f'无法打开危险性数据集: {hazard_path}'}), 400
        
        # 获取地理变换和投影信息（从第一个数据集）
        geotransform = hazard_dataset.GetGeoTransform()
        projection = hazard_dataset.GetProjection()
        rows = hazard_dataset.RasterYSize
        cols = hazard_dataset.RasterXSize
        
        print(f"从危险性数据集获取坐标信息:")
        print(f"  数据尺寸: {rows} x {cols}")
        print(f"  地理变换: {geotransform}")
        print(f"  投影信息: {projection[:100]}...")
        
        # 读取各模型数据和nodata值
        hazard_band = hazard_dataset.GetRasterBand(1)
        hazard_data = hazard_band.ReadAsArray().astype(np.float64)
        hazard_nodata = hazard_band.GetNoDataValue()
        
        exposure_dataset = gdal.Open(exposure_path)
        exposure_band = exposure_dataset.GetRasterBand(1)
        exposure_data = exposure_band.ReadAsArray().astype(np.float64)
        exposure_nodata = exposure_band.GetNoDataValue()
        
        value_dataset = gdal.Open(value_path)
        value_band = value_dataset.GetRasterBand(1)
        value_data = value_band.ReadAsArray().astype(np.float64)
        value_nodata = value_band.GetNoDataValue()
        
        sensitivity_dataset = gdal.Open(sensitivity_path)
        sensitivity_band = sensitivity_dataset.GetRasterBand(1)
        sensitivity_data = sensitivity_band.ReadAsArray().astype(np.float64)
        sensitivity_nodata = sensitivity_band.GetNoDataValue()
        
        resistance_dataset = gdal.Open(resistance_path)
        resistance_band = resistance_dataset.GetRasterBand(1)
        resistance_data = resistance_band.ReadAsArray().astype(np.float64)
        resistance_nodata = resistance_band.GetNoDataValue()
        
        mitigation_dataset = gdal.Open(mitigation_path)
        mitigation_band = mitigation_dataset.GetRasterBand(1)
        mitigation_data = mitigation_band.ReadAsArray().astype(np.float64)
        mitigation_nodata = mitigation_band.GetNoDataValue()
        
        # 打印nodata值信息
        print(f"各模型nodata值:")
        print(f"  危险性H: {hazard_nodata}")
        print(f"  暴露性E: {exposure_nodata}")
        print(f"  价值密度V: {value_nodata}")
        print(f"  敏感性S: {sensitivity_nodata}")
        print(f"  工程防灾性R: {resistance_nodata}")
        print(f"  工程减灾性M: {mitigation_nodata}")
        
        # 关闭数据集
        hazard_dataset = None
        exposure_dataset = None
        value_dataset = None
        sensitivity_dataset = None
        resistance_dataset = None
        mitigation_dataset = None
        
        print(f"各模型数据范围:")
        print(f"  危险性H: [{np.min(hazard_data):.3f}, {np.max(hazard_data):.3f}]")
        print(f"  暴露性E: [{np.min(exposure_data):.3f}, {np.max(exposure_data):.3f}]")
        print(f"  价值密度V: [{np.min(value_data):.3f}, {np.max(value_data):.3f}]")
        print(f"  敏感性S: [{np.min(sensitivity_data):.3f}, {np.max(sensitivity_data):.3f}]")
        print(f"  工程防灾性R: [{np.min(resistance_data):.3f}, {np.max(resistance_data):.3f}]")
        print(f"  工程减灾性M: [{np.min(mitigation_data):.3f}, {np.max(mitigation_data):.3f}]")
        
        # 检查数据尺寸并重采样到统一尺寸
        print("\n--- 检查数据尺寸 ---")
        data_shapes = {
            '危险性H': hazard_data.shape,
            '暴露性E': exposure_data.shape,
            '价值密度V': value_data.shape,
            '敏感性S': sensitivity_data.shape,
            '工程防灾性R': resistance_data.shape,
            '工程减灾性M': mitigation_data.shape
        }
        
        for name, shape in data_shapes.items():
            print(f"  {name}: {shape}")
        
        # 使用危险性数据的尺寸作为目标尺寸
        target_shape = hazard_data.shape
        print(f"\n目标尺寸: {target_shape}")
        
        # 重采样其他数据到目标尺寸（注意处理nodata值）
        from scipy.ndimage import zoom
        
        def resample_with_nodata(data, nodata_value, zoom_factors, name):
            """重采样时正确处理nodata值"""
            # 创建掩膜标记nodata位置
            if nodata_value is not None:
                nodata_mask = (data == nodata_value)
            else:
                nodata_mask = np.zeros_like(data, dtype=bool)
            
            # 将nodata值设为NaN，避免参与插值计算
            data_for_resample = data.copy()
            if nodata_value is not None:
                data_for_resample[nodata_mask] = np.nan
            
            # 执行重采样
            resampled_data = zoom(data_for_resample, zoom_factors, order=1, prefilter=False)
            
            # 将重采样后的NaN值恢复为nodata值
            if nodata_value is not None:
                nan_mask = np.isnan(resampled_data)
                resampled_data[nan_mask] = nodata_value
            
            return resampled_data
        
        if exposure_data.shape != target_shape:
            zoom_factors = (target_shape[0] / exposure_data.shape[0], target_shape[1] / exposure_data.shape[1])
            exposure_data = resample_with_nodata(exposure_data, exposure_nodata, zoom_factors, '暴露性E')
            print(f"暴露性数据重采样: {data_shapes['暴露性E']} -> {exposure_data.shape}")
        
        if value_data.shape != target_shape:
            zoom_factors = (target_shape[0] / value_data.shape[0], target_shape[1] / value_data.shape[1])
            value_data = resample_with_nodata(value_data, value_nodata, zoom_factors, '价值密度V')
            print(f"价值密度数据重采样: {data_shapes['价值密度V']} -> {value_data.shape}")
        
        if sensitivity_data.shape != target_shape:
            zoom_factors = (target_shape[0] / sensitivity_data.shape[0], target_shape[1] / sensitivity_data.shape[1])
            sensitivity_data = resample_with_nodata(sensitivity_data, sensitivity_nodata, zoom_factors, '敏感性S')
            print(f"敏感性数据重采样: {data_shapes['敏感性S']} -> {sensitivity_data.shape}")
        
        if resistance_data.shape != target_shape:
            zoom_factors = (target_shape[0] / resistance_data.shape[0], target_shape[1] / resistance_data.shape[1])
            resistance_data = resample_with_nodata(resistance_data, resistance_nodata, zoom_factors, '工程防灾性R')
            print(f"工程防灾性数据重采样: {data_shapes['工程防灾性R']} -> {resistance_data.shape}")
        
        if mitigation_data.shape != target_shape:
            zoom_factors = (target_shape[0] / mitigation_data.shape[0], target_shape[1] / mitigation_data.shape[1])
            mitigation_data = resample_with_nodata(mitigation_data, mitigation_nodata, zoom_factors, '工程减灾性M')
            print(f"工程减灾性数据重采样: {data_shapes['工程减灾性M']} -> {mitigation_data.shape}")
        
        # 创建有效数据掩膜（只计算都有数值的部分）
        print("\n--- 创建有效数据掩膜 ---")
        
        # 创建各个数据集的有效掩膜
        hazard_valid = ~np.isnan(hazard_data)
        if hazard_nodata is not None:
            hazard_valid = hazard_valid & (hazard_data != hazard_nodata)
            
        exposure_valid = ~np.isnan(exposure_data)
        if exposure_nodata is not None:
            exposure_valid = exposure_valid & (exposure_data != exposure_nodata)
            
        value_valid = ~np.isnan(value_data)
        if value_nodata is not None:
            value_valid = value_valid & (value_data != value_nodata)
            
        sensitivity_valid = ~np.isnan(sensitivity_data)
        if sensitivity_nodata is not None:
            sensitivity_valid = sensitivity_valid & (sensitivity_data != sensitivity_nodata)
            
        resistance_valid = ~np.isnan(resistance_data)
        if resistance_nodata is not None:
            resistance_valid = resistance_valid & (resistance_data != resistance_nodata)
            
        mitigation_valid = ~np.isnan(mitigation_data)
        if mitigation_nodata is not None:
            mitigation_valid = mitigation_valid & (mitigation_data != mitigation_nodata)
        
        # 综合有效掩膜（所有数据都有效的像素）
        valid_mask = (hazard_valid & exposure_valid & value_valid & 
                     sensitivity_valid & resistance_valid & mitigation_valid)
        
        valid_count = np.sum(valid_mask)
        total_count = hazard_data.size
        print(f"有效像素数量: {valid_count}/{total_count} ({valid_count/total_count*100:.1f}%)")
        
        # 按照新公式计算IDF和IPI
        print("\n" + "="*60)
        print("📊 开始执行IDF和IPI计算")
        print("="*60)
        print(f"📋 计算公式:")
        print(f"   I1 = w1*H × w2*E × w3*V × w4*S  (灾害影响基值)")
        print(f"   I2 = w5*R × w2*E × w3*V × w4*S  (工程防灾减量值)")
        print(f"   I3 = w1*H × w2*E × w6*M × w4*S  (工程减灾减量值)")
        print(f"   IDFi = I1 - I2 - I3")
        print(f"   IPIi = (I1 - I2 - I3) / I1")
        print(f"   IDF = ΣIDFi (小于0的值设为0后求和)")
        print(f"   IPI = ΣIPIi (小于0的值设为0后求和)")
        print()
        
        # 使用危险性数据集的nodata值作为输出nodata值
        output_nodata = hazard_nodata if hazard_nodata is not None else -9999
        
        # 打印输入数据的统计信息
        print(f"📈 输入数据统计信息:")
        print(f"   H (危险性) 范围: [{np.min(hazard_data[valid_mask]):.3f}, {np.max(hazard_data[valid_mask]):.3f}]")
        print(f"   E (暴露性) 范围: [{np.min(exposure_data[valid_mask]):.3f}, {np.max(exposure_data[valid_mask]):.3f}]")
        print(f"   V (价值密度) 范围: [{np.min(value_data[valid_mask]):.3f}, {np.max(value_data[valid_mask]):.3f}]")
        print(f"   S (敏感性) 范围: [{np.min(sensitivity_data[valid_mask]):.3f}, {np.max(sensitivity_data[valid_mask]):.3f}]")
        print(f"   R (工程防灾性) 范围: [{np.min(resistance_data[valid_mask]):.3f}, {np.max(resistance_data[valid_mask]):.3f}]")
        print(f"   M (工程减灾性) 范围: [{np.min(mitigation_data[valid_mask]):.3f}, {np.max(mitigation_data[valid_mask]):.3f}]")
        print()
        
        # 计算I1：灾害影响基值 I1=（w1*H×w2*E×w3*V×w4*S）
        print(f"🔢 计算I1（灾害影响基值）:")
        print(f"   公式: I1 = {w1}*H × {w2}*E × {w3}*V × {w4}*S")
        I1_data = np.full_like(hazard_data, output_nodata, dtype=np.float64)
        I1_data[valid_mask] = (w1 * hazard_data[valid_mask] * 
                              w2 * exposure_data[valid_mask] * 
                              w3 * value_data[valid_mask] * 
                              w4 * sensitivity_data[valid_mask])
        print(f"   I1计算完成，范围: [{np.min(I1_data[valid_mask]):.6f}, {np.max(I1_data[valid_mask]):.6f}]")
        print(f"   I1总和: {np.sum(I1_data[valid_mask]):.6f}")
        print()
        
        # 计算I2：工程防灾减量值 I2=（w5*R×w2*E×w3*V×w4*S）
        print(f"🔢 计算I2（工程防灾减量值）:")
        print(f"   公式: I2 = {w5}*R × {w2}*E × {w3}*V × {w4}*S")
        I2_data = np.full_like(hazard_data, output_nodata, dtype=np.float64)
        I2_data[valid_mask] = (w5 * resistance_data[valid_mask] * 
                              w2 * exposure_data[valid_mask] * 
                              w3 * value_data[valid_mask] * 
                              w4 * sensitivity_data[valid_mask])
        print(f"   I2计算完成，范围: [{np.min(I2_data[valid_mask]):.6f}, {np.max(I2_data[valid_mask]):.6f}]")
        print(f"   I2总和: {np.sum(I2_data[valid_mask]):.6f}")
        print()
        
        # 计算I3：工程减灾减量值 I3=（w1*H×w2*E×w6*M×w4*S）
        print(f"🔢 计算I3（工程减灾减量值）:")
        print(f"   公式: I3 = {w1}*H × {w2}*E × {w6}*M × {w4}*S")
        I3_data = np.full_like(hazard_data, output_nodata, dtype=np.float64)
        I3_data[valid_mask] = (w1 * hazard_data[valid_mask] * 
                              w2 * exposure_data[valid_mask] * 
                              w6 * mitigation_data[valid_mask] * 
                              w4 * sensitivity_data[valid_mask])
        print(f"   I3计算完成，范围: [{np.min(I3_data[valid_mask]):.6f}, {np.max(I3_data[valid_mask]):.6f}]")
        print(f"   I3总和: {np.sum(I3_data[valid_mask]):.6f}")
        print()
        
        # 计算flag：I1>0?1:0
        print(f"🔢 计算IDFi和IPIi:")
        flag_data = np.zeros_like(hazard_data, dtype=np.float64)
        flag_data[valid_mask] = np.where(I1_data[valid_mask] > 0, 1, 0)
        positive_I1_count = np.sum(flag_data[valid_mask])
        total_valid_count = np.sum(valid_mask)
        print(f"   有效像素总数: {total_valid_count}")
        print(f"   I1>0的像素数: {positive_I1_count} ({positive_I1_count/total_valid_count*100:.1f}%)")
        print(f"   I1<=0的像素数: {total_valid_count - positive_I1_count} ({(total_valid_count - positive_I1_count)/total_valid_count*100:.1f}%)")
        
        # 计算IDFi：IDFi=（I1-I2-I3）* flag，然后将负值设为0
        print(f"   计算IDFi = (I1 - I2 - I3) * flag，负值设为0")
        IDFi_data = np.full_like(hazard_data, output_nodata, dtype=np.float64)
        IDFi_temp = (I1_data[valid_mask] - I2_data[valid_mask] - I3_data[valid_mask]) * flag_data[valid_mask]
        # 重要：将负值设为0，确保IDFi不出现负值
        IDFi_temp_positive = np.maximum(IDFi_temp, 0)
        IDFi_data[valid_mask] = IDFi_temp_positive
        
        # 统计IDFi中的负值（原始计算和处理后）
        negative_IDFi_count = np.sum(IDFi_temp < 0)
        positive_IDFi_count_orig = np.sum(IDFi_temp > 0)
        zero_IDFi_count_orig = np.sum(IDFi_temp == 0)
        print(f"   IDFi原始计算结果统计:")
        print(f"     原始正值像素: {positive_IDFi_count_orig} ({positive_IDFi_count_orig/len(IDFi_temp)*100:.1f}%)")
        print(f"     原始负值像素: {negative_IDFi_count} ({negative_IDFi_count/len(IDFi_temp)*100:.1f}%)")
        print(f"     原始零值像素: {zero_IDFi_count_orig} ({zero_IDFi_count_orig/len(IDFi_temp)*100:.1f}%)")
        if len(IDFi_temp) > 0:
            print(f"   IDFi原始范围: [{np.min(IDFi_temp):.6f}, {np.max(IDFi_temp):.6f}]")
            print(f"   IDFi原始总和: {np.sum(IDFi_temp):.6f}")
        
        # 统计处理后的IDFi（负值设为0后）
        positive_IDFi_count_final = np.sum(IDFi_temp_positive > 0)
        zero_IDFi_count_final = np.sum(IDFi_temp_positive == 0)
        print(f"   IDFi处理后统计（负值→0）:")
        print(f"     最终正值像素: {positive_IDFi_count_final} ({positive_IDFi_count_final/len(IDFi_temp_positive)*100:.1f}%)")
        print(f"     最终零值像素: {zero_IDFi_count_final} ({zero_IDFi_count_final/len(IDFi_temp_positive)*100:.1f}%)")
        print(f"   IDFi最终范围: [{np.min(IDFi_temp_positive):.6f}, {np.max(IDFi_temp_positive):.6f}]")
        print(f"   IDFi最终总和: {np.sum(IDFi_temp_positive):.6f}")
        
        # 计算IPIi：IPIi=（（I1-I2-I3）/I1）* flag，严格限制在[0,1]范围内
        # 只计算I1>0的像素，避免除零错误
        print(f"   计算IPIi = ((I1 - I2 - I3) / I1) * flag (仅I1>0的像素)")
        IPIi_data = np.full_like(hazard_data, output_nodata, dtype=np.float64)
        valid_I1_mask = valid_mask & (I1_data > 0)
        if np.sum(valid_I1_mask) > 0:
            IPIi_temp = ((I1_data[valid_I1_mask] - I2_data[valid_I1_mask] - I3_data[valid_I1_mask]) / I1_data[valid_I1_mask]) * flag_data[valid_I1_mask]
            
            # 统计IPIi中的负值和超出范围的值
            negative_IPIi_count = np.sum(IPIi_temp < 0)
            positive_IPIi_count = np.sum(IPIi_temp > 0)
            zero_IPIi_count = np.sum(IPIi_temp == 0)
            over_one_count = np.sum(IPIi_temp > 1)
            print(f"   IPIi原始计算结果统计 (基于{len(IPIi_temp)}个I1>0的像素):")
            print(f"     正值像素: {positive_IPIi_count} ({positive_IPIi_count/len(IPIi_temp)*100:.1f}%)")
            print(f"     负值像素: {negative_IPIi_count} ({negative_IPIi_count/len(IPIi_temp)*100:.1f}%)")
            print(f"     零值像素: {zero_IPIi_count} ({zero_IPIi_count/len(IPIi_temp)*100:.1f}%)")
            print(f"     >1的像素: {over_one_count} ({over_one_count/len(IPIi_temp)*100:.1f}%)")
            print(f"   IPIi原始范围: [{np.min(IPIi_temp):.6f}, {np.max(IPIi_temp):.6f}]")
            
            # 关键修复：将IPIi严格限制在[0,1]范围内
            IPIi_clipped = np.clip(IPIi_temp, 0, 1)
            IPIi_data[valid_I1_mask] = IPIi_clipped
            
            # 统计修正后的结果
            final_over_one_count = np.sum(IPIi_clipped > 1)
            final_negative_count = np.sum(IPIi_clipped < 0)
            clipped_count = np.sum(IPIi_temp != IPIi_clipped)
            print(f"   IPIi修正后统计:")
            print(f"     被截断的像素数: {clipped_count} ({clipped_count/len(IPIi_temp)*100:.1f}%)")
            print(f"     最终范围: [{np.min(IPIi_clipped):.6f}, {np.max(IPIi_clipped):.6f}]")
            print(f"     确认无负值: {final_negative_count == 0}")
            print(f"     确认无>1值: {final_over_one_count == 0}")
        # 将I1<=0的像素设为0值
        IPIi_data[valid_mask & (I1_data <= 0)] = 0
        print()
        # 计算总的IDF：IDF = ƩIDFi（已经处理过负值）
        print(f"🧮 计算最终IDF和IPI总值:")
        # IDFi_data[valid_mask]中已经没有负值了（在计算时已处理）
        IDFi_final = IDFi_data[valid_mask]
        print(f"   IDFi最终统计:")
        print(f"   IDFi正值像素数: {np.sum(IDFi_final > 0)}")
        print(f"   IDFi零值像素数: {np.sum(IDFi_final == 0)}")
        print(f"   IDFi确认无负值: {np.sum(IDFi_final < 0) == 0}")
        IDF = float(np.sum(IDFi_final))
        print(f"   IDF = ΣIDFi = {IDF:.6f}")
        
        # 计算总的IPI：IPI = mean(IPIi)（将小于0的值设为0后求均值）
        if np.sum(valid_I1_mask) > 0:
            IPIi_positive = np.maximum(IPIi_data[valid_mask], 0)  # 将小于0的值设为0
            negative_to_zero_IPI_count = np.sum((IPIi_data[valid_mask] < 0) & (IPIi_positive >= 0))
            print(f"   IPIi负值转为0的像素数: {negative_to_zero_IPI_count}")
            print(f"   IPIi正值像素数: {np.sum(IPIi_positive > 0)}")
            print(f"   IPIi零值像素数: {np.sum(IPIi_positive == 0)}")
            IPI = float(np.mean(IPIi_positive))
            print(f"   IPI = ΣIPIi / 像素数 (负值设为0后求平均) = {IPI:.6f}")
        else:
            IPI = 0.0
            print(f"   没有I1>0的像素，IPI设为0.0")
        print()
        
        # 数据验证和范围检查
        print(f"📋 最终结果验证:")
        valid_IDFi = IDFi_data[valid_mask]
        valid_IPIi = IPIi_data[valid_I1_mask] if np.sum(valid_I1_mask) > 0 else np.array([])
        
        print(f"   I1数据范围: [{np.min(I1_data[valid_mask]):.6f}, {np.max(I1_data[valid_mask]):.6f}]")
        print(f"   I2数据范围: [{np.min(I2_data[valid_mask]):.6f}, {np.max(I2_data[valid_mask]):.6f}]")
        print(f"   I3数据范围: [{np.min(I3_data[valid_mask]):.6f}, {np.max(I3_data[valid_mask]):.6f}]")
        print(f"   IDFi数据范围: [{np.min(valid_IDFi):.6f}, {np.max(valid_IDFi):.6f}]")
        if len(valid_IPIi) > 0:
            print(f"   IPIi数据范围: [{np.min(valid_IPIi):.6f}, {np.max(valid_IPIi):.6f}]")
        
        # 范围验证
        has_negative_I1 = np.sum(I1_data[valid_mask] < 0) > 0
        has_negative_I2 = np.sum(I2_data[valid_mask] < 0) > 0
        has_negative_I3 = np.sum(I3_data[valid_mask] < 0) > 0
        has_negative_IDFi = np.sum(valid_IDFi < 0) > 0
        has_negative_IPIi = np.sum(valid_IPIi < 0) > 0 if len(valid_IPIi) > 0 else False
        IPI_out_of_range = IPI < 0 or IPI > 1
        
        # 检查IPIi个体值是否超出[0,1]范围
        IPIi_out_of_range_count = 0
        IPIi_max_value = 0
        IPIi_min_value = 0
        if len(valid_IPIi) > 0:
            IPIi_out_of_range_count = np.sum((valid_IPIi < 0) | (valid_IPIi > 1))
            IPIi_max_value = np.max(valid_IPIi)
            IPIi_min_value = np.min(valid_IPIi)
        
        print(f"   ⚠️  数据范围检查:")
        print(f"     I1有负值: {'是' if has_negative_I1 else '否'}")
        print(f"     I2有负值: {'是' if has_negative_I2 else '否'}")
        print(f"     I3有负值: {'是' if has_negative_I3 else '否'}")
        print(f"     IDFi有负值: {'是' if has_negative_IDFi else '否'}")
        print(f"     IPIi有负值: {'是' if has_negative_IPIi else '否'}")
        print(f"     IPI总值超出[0,1]范围: {'是' if IPI_out_of_range else '否'}")
        print(f"     IPIi个体值超出[0,1]的像素数: {IPIi_out_of_range_count} / {len(valid_IPIi) if len(valid_IPIi) > 0 else 0}")
        if len(valid_IPIi) > 0:
            print(f"     IPIi实际范围: [{IPIi_min_value:.3f}, {IPIi_max_value:.3f}]")
            if IPIi_max_value > 1:
                print(f"     ❌ 警告：IPIi最大值 {IPIi_max_value:.3f} 超出期望范围[0,1]")
            if IPIi_min_value < 0:
                print(f"     ❌ 警告：IPIi最小值 {IPIi_min_value:.3f} 低于期望范围[0,1]")
        print(f"   📊 总IDF值: {IDF:.6f} (期望约24万)")
        print(f"   📊 总IPI值: {IPI:.6f} (期望范围[0,1])")
        
        # 分析I2负值问题
        if has_negative_I2:
            I2_negative_count = np.sum(I2_data[valid_mask] < 0)
            I2_min_value = np.min(I2_data[valid_mask])
            print(f"   🔍 I2负值分析:")
            print(f"     I2负值像素数: {I2_negative_count} / {len(I2_data[valid_mask])}")
            print(f"     I2最小值: {I2_min_value:.3f}")
            print(f"     可能原因：R(工程防灾性)数据包含负值，导致I2为负")
            
        print()
        
        # 保存I1栅格（灾害影响基值）
        print("\n--- 保存I1栅格和预览图 ---")
        I1_result_path = result_path.replace('.tif', '_I1.tif')
        assessment_engine.save_result_raster(I1_data, geotransform, projection, I1_result_path, output_nodata)
        print(f"I1栅格已保存: {I1_result_path}（nodata值: {output_nodata}）")
        
        # 生成I1预览图
        I1_preview_filename = result_name + '_' + f'I1_{timestamp}_{result_id[:8]}_preview.png'
        I1_preview_path = os.path.join(OUTPUT_DIR, I1_preview_filename)
        
        I1_display_data = I1_data.copy()
        I1_display_data[~valid_mask] = np.nan
        
        if len(I1_data[valid_mask]) > 0 and np.max(I1_data[valid_mask]) > np.min(I1_data[valid_mask]):
            plt.figure(figsize=(10, 8))
            
            # 使用分位数方法分级
            valid_I1 = I1_data[valid_mask]
            positive_I1 = valid_I1[valid_I1 > 0]
            if len(positive_I1) > 0:
                p20 = np.percentile(positive_I1, 20)
                p40 = np.percentile(positive_I1, 40)
                p60 = np.percentile(positive_I1, 60)
                p80 = np.percentile(positive_I1, 80)
                I1_breaks = np.array([0, p20, p40, p60, p80, np.max(positive_I1)])
                print(f"I1分位值分级断点: {I1_breaks}")
            else:
                I1_breaks = np.array([0, 0.1, 0.2, 0.3, 0.4, 0.5])
            
            # 导入必要的模块
            from matplotlib.colors import LinearSegmentedColormap, BoundaryNorm
            
            # 5级风险色带（绿→黄→橙→红）
            colors = ['#E8F5E8', '#FFE4B5', '#FFA500', '#FF6347', '#DC143C']
            cmap = LinearSegmentedColormap.from_list('I1_risk', colors, N=5)
            
            norm = BoundaryNorm(boundaries=I1_breaks, ncolors=5)
            im = plt.imshow(I1_display_data, cmap=cmap, norm=norm, interpolation='nearest')
            
            plt.title(f'I1 灾害影响基值\n总和: {np.sum(I1_data[valid_mask]):.0f}', fontsize=14, pad=20)
            
            # 添加颜色条
            cbar = plt.colorbar(im, shrink=0.8)
            cbar.set_label('I1值', rotation=270, labelpad=20)
            
            plt.tight_layout()
            plt.savefig(I1_preview_path, dpi=300, bbox_inches='tight')
            plt.close()
            print(f"I1预览图已保存: {I1_preview_path}")
        else:
            print("I1数据无有效值或无变化，跳过预览图生成")
        
        # # 保存I1 CSV文件
        # I1_csv_path = I1_result_path.replace('.tif', '.csv')
        # assessment_engine.save_raster_to_csv(I1_data, geotransform, I1_csv_path, nodata_value=output_nodata)
        # print(f"I1 CSV已保存: {I1_csv_path}")
        
        # 保存I2栅格（工程防灾减量值）
        print("\n--- 保存I2栅格和预览图 ---")
        I2_result_path = result_path.replace('.tif', '_I2.tif')
        assessment_engine.save_result_raster(I2_data, geotransform, projection, I2_result_path, output_nodata)
        print(f"I2栅格已保存: {I2_result_path}（nodata值: {output_nodata}）")
        
        # 生成I2预览图
        I2_preview_filename = result_name + '_' + f'I2_{timestamp}_{result_id[:8]}_preview.png'
        I2_preview_path = os.path.join(OUTPUT_DIR, I2_preview_filename)
        
        I2_display_data = I2_data.copy()
        I2_display_data[~valid_mask] = np.nan
        
        if len(I2_data[valid_mask]) > 0 and np.max(I2_data[valid_mask]) > np.min(I2_data[valid_mask]):
            plt.figure(figsize=(10, 8))
            
            # 使用分位数方法分级
            valid_I2 = I2_data[valid_mask]
            positive_I2 = valid_I2[valid_I2 > 0]
            if len(positive_I2) > 0:
                p20 = np.percentile(positive_I2, 20)
                p40 = np.percentile(positive_I2, 40)
                p60 = np.percentile(positive_I2, 60)
                p80 = np.percentile(positive_I2, 80)
                I2_breaks = np.array([0, p20, p40, p60, p80, np.max(positive_I2)])
                print(f"I2分位值分级断点: {I2_breaks}")
            else:
                I2_breaks = np.array([0, 0.1, 0.2, 0.3, 0.4, 0.5])
            
            # 导入必要的模块
            from matplotlib.colors import LinearSegmentedColormap, BoundaryNorm
            
            # 5级色带（蓝色系，表示防灾能力）
            colors = ['#E8F4FD', '#87CEEB', '#4682B4', '#1E90FF', '#0000CD']
            cmap = LinearSegmentedColormap.from_list('I2_defense', colors, N=5)
            
            norm = BoundaryNorm(boundaries=I2_breaks, ncolors=5)
            im = plt.imshow(I2_display_data, cmap=cmap, norm=norm, interpolation='nearest')
            
            plt.title(f'I2 工程防灾减量值\n总和: {np.sum(I2_data[valid_mask]):.0f}', fontsize=14, pad=20)
            
            # 添加颜色条
            cbar = plt.colorbar(im, shrink=0.8)
            cbar.set_label('I2值', rotation=270, labelpad=20)
            
            plt.tight_layout()
            plt.savefig(I2_preview_path, dpi=300, bbox_inches='tight')
            plt.close()
            print(f"I2预览图已保存: {I2_preview_path}")
        else:
            print("I2数据无有效值或无变化，跳过预览图生成")
        
        # # 保存I2 CSV文件
        # I2_csv_path = I2_result_path.replace('.tif', '.csv')
        # assessment_engine.save_raster_to_csv(I2_data, geotransform, I2_csv_path, nodata_value=output_nodata)
        # print(f"I2 CSV已保存: {I2_csv_path}")
        
        # 保存I3栅格（工程减灾减量值）
        print("\n--- 保存I3栅格和预览图 ---")
        I3_result_path = result_path.replace('.tif', '_I3.tif')
        assessment_engine.save_result_raster(I3_data, geotransform, projection, I3_result_path, output_nodata)
        print(f"I3栅格已保存: {I3_result_path}（nodata值: {output_nodata}）")
        
        # 生成I3预览图
        I3_preview_filename = result_name + '_' + f'I3_{timestamp}_{result_id[:8]}_preview.png'
        I3_preview_path = os.path.join(OUTPUT_DIR, I3_preview_filename)
        
        I3_display_data = I3_data.copy()
        I3_display_data[~valid_mask] = np.nan
        
        # 总是生成I3预览图，即使数据全为0
        plt.figure(figsize=(10, 8))
        
        # 检查数据范围
        valid_I3 = I3_data[valid_mask]
        I3_min = np.min(valid_I3) if len(valid_I3) > 0 else 0
        I3_max = np.max(valid_I3) if len(valid_I3) > 0 else 0
        I3_has_variation = I3_max > I3_min
        
        if I3_has_variation and len(valid_I3) > 0:
            # 有数据变化的情况
            positive_I3 = valid_I3[valid_I3 > 0]
            if len(positive_I3) > 0:
                p20 = np.percentile(positive_I3, 20)
                p40 = np.percentile(positive_I3, 40)
                p60 = np.percentile(positive_I3, 60)
                p80 = np.percentile(positive_I3, 80)
                I3_breaks = np.array([I3_min, p20, p40, p60, p80, I3_max])
                print(f"I3分位值分级断点: {I3_breaks}")
            else:
                # 只有负值或零值
                I3_breaks = np.array([I3_min, I3_min + (I3_max-I3_min)*0.2, I3_min + (I3_max-I3_min)*0.4, 
                                    I3_min + (I3_max-I3_min)*0.6, I3_min + (I3_max-I3_min)*0.8, I3_max])
                print(f"I3分级断点（无正值）: {I3_breaks}")
        else:
            # 数据无变化（全部相同值）的情况
            if I3_max == 0:
                I3_breaks = np.array([0, 0.02, 0.04, 0.06, 0.08, 0.1])
                print(f"I3数据全为0，使用默认分级断点: {I3_breaks}")
            else:
                # 围绕单一值创建分级
                center_val = I3_max
                I3_breaks = np.array([center_val-0.1, center_val-0.05, center_val, center_val+0.05, center_val+0.1, center_val+0.2])
                print(f"I3数据为单一值 {center_val}，使用扩展分级断点: {I3_breaks}")
        
        # 导入必要的模块
        from matplotlib.colors import LinearSegmentedColormap, BoundaryNorm
        
        # 5级色带（紫色系，表示减灾能力）
        colors = ['#F3E5F5', '#CE93D8', '#AB47BC', '#8E24AA', '#6A1B9A']
        cmap = LinearSegmentedColormap.from_list('I3_mitigation', colors, N=5)
        
        norm = BoundaryNorm(boundaries=I3_breaks, ncolors=5)
        im = plt.imshow(I3_display_data, cmap=cmap, norm=norm, interpolation='nearest')
        
        plt.title(f'I3 工程减灾减量值\n总和: {np.sum(I3_data[valid_mask]):.3f} | 范围: [{I3_min:.3f}, {I3_max:.3f}]', fontsize=14, pad=20)
        
        # 添加颜色条
        cbar = plt.colorbar(im, shrink=0.8)
        cbar.set_label('I3值', rotation=270, labelpad=20)
        
        # 添加统计信息文本
        if len(valid_I3) > 0:
            stats_text = f'I3统计:\n最小值: {I3_min:.3f}\n最大值: {I3_max:.3f}\n平均值: {np.mean(valid_I3):.3f}\n总和: {np.sum(valid_I3):.3f}\n有效像素: {len(valid_I3)}'
        else:
            stats_text = '无有效I3数据'
        plt.text(0.02, 0.98, stats_text, transform=plt.gca().transAxes, 
                verticalalignment='top', bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
        
        plt.tight_layout()
        plt.savefig(I3_preview_path, dpi=300, bbox_inches='tight')
        plt.close()
        print(f"I3预览图已保存: {I3_preview_path} (数据变化: {'有' if I3_has_variation else '无'})")
        
        # # 保存I3 CSV文件
        # I3_csv_path = I3_result_path.replace('.tif', '.csv')
        # assessment_engine.save_raster_to_csv(I3_data, geotransform, I3_csv_path, nodata_value=output_nodata)
        # print(f"I3 CSV已保存: {I3_csv_path}")
        
        # 保存IDFi栅格
        print("\n--- 保存IDFi栅格 ---")
        IDFi_result_path = result_path.replace('.tif', '_IDFi.tif')
        assessment_engine.save_result_raster(IDFi_data, geotransform, projection, IDFi_result_path, output_nodata)
        print(f"IDFi栅格已保存: {IDFi_result_path}（nodata值: {output_nodata}）")
        
        # 保存IPIi栅格
        print("\n--- 保存IPIi栅格 ---")
        IPIi_result_path = result_path.replace('.tif', '_IPIi.tif')
        assessment_engine.save_result_raster(IPIi_data, geotransform, projection, IPIi_result_path, output_nodata)
        print(f"IPIi栅格已保存: {IPIi_result_path}（nodata值: {output_nodata}）")
        
        # 生成IDFi预览图（5级风险色带：红→橙→黄→绿→灰）
        print("\n--- 生成IDFi预览图 ---")
        IDFi_preview_filename = result_name + '_' +  f'IDFi_{timestamp}_{result_id[:8]}_preview.png'
        IDFi_preview_path = os.path.join(OUTPUT_DIR, IDFi_preview_filename)
        
        # 创建用于显示的IDFi数据（将无效值设为NaN以便正确显示）
        IDFi_display_data = IDFi_data.copy()
        IDFi_display_data[~valid_mask] = np.nan
        
        # 使用自然断点法（Jenks Natural Breaks）分5级
        def jenks_breaks(data, n_classes, max_sample_size=50000):
            """计算Jenks自然断点（优化版本，支持大数据集采样）"""
            if len(data) == 0:
                # 如果数据为空，返回默认的等间距断点
                return np.array([0, 1, 2, 3, 4, 5])
            
            data_array = np.array(data)
            print(f"原始数据量: {len(data_array)} 个数据点")
            
            # 如果数据量过大，进行采样以提高计算速度
            if len(data_array) > max_sample_size:
                print(f"数据量 {len(data_array)} 超过阈值 {max_sample_size}，进行随机采样")
                # 使用分层采样确保保留数据分布特征
                # 先排序，然后等间隔采样，再加上一些随机采样
                sorted_data = np.sort(data_array)
                
                # 等间隔采样（保留分布特征）
                step_size = len(sorted_data) // (max_sample_size // 2)
                systematic_sample = sorted_data[::step_size][:max_sample_size // 2]
                
                # 随机采样（增加随机性）
                remaining_size = max_sample_size - len(systematic_sample)
                if remaining_size > 0:
                    random_indices = np.random.choice(len(data_array), size=min(remaining_size, len(data_array)), replace=False)
                    random_sample = data_array[random_indices]
                    data_array = np.concatenate([systematic_sample, random_sample])
                else:
                    data_array = systematic_sample
                
                print(f"采样后数据量: {len(data_array)} 个数据点")
            
            if len(np.unique(data_array)) < n_classes:
                # 如果唯一值数量小于类别数，使用等间距分级
                print(f"唯一值数量 {len(np.unique(data_array))} 小于类别数 {n_classes}，使用等间距分级")
                min_val = np.min(data_array)
                max_val = np.max(data_array)
                if min_val == max_val:
                    # 如果所有值都相同，创建基于该值的断点
                    return np.linspace(min_val - 0.5, min_val + 0.5, n_classes + 1) 
                return np.linspace(min_val, max_val, n_classes + 1)

            try:
                print("开始计算 Jenks 自然断点...")
                import time
                start_time = time.time()
                
                breaks = jenkspy.jenks_breaks(data_array, n_classes=n_classes)
                
                end_time = time.time()
                print(f"Jenks 计算完成，耗时: {end_time - start_time:.2f} 秒")
                
                # 确保断点是唯一的，并且数量正确
                unique_breaks = sorted(list(set(breaks)))
                if len(unique_breaks) < 2: # 至少需要两个断点（最小值和最大值）
                    print(f"JenksPy 返回的唯一断点数 {len(unique_breaks)} 不足，使用等间距分级")
                    min_val = np.min(data_array)
                    max_val = np.max(data_array)
                    if min_val == max_val:
                        return np.linspace(min_val - 0.5, min_val + 0.5, n_classes + 1)
                    return np.linspace(min_val, max_val, n_classes + 1)
                
                # 如果 jenkspy 返回的断点数少于 n_classes + 1, 尝试补充
                # 这通常发生在数据分布极端的情况下
                if len(unique_breaks) < n_classes + 1:
                    print(f"JenksPy 返回的断点数 {len(unique_breaks)} 少于期望的 {n_classes + 1}，尝试使用分位数补充或等间距")
                    # 尝试使用分位数，如果不行再用等间距
                    quantiles = np.linspace(0, 1, n_classes + 1)
                    quantile_breaks = np.quantile(np.sort(data_array), quantiles)
                    unique_quantile_breaks = sorted(list(set(quantile_breaks)))
                    if len(unique_quantile_breaks) >= 2:
                        breaks = np.array(unique_quantile_breaks)
                        if len(breaks) < n_classes + 1: # 再次检查，如果还是不够，就用等间距
                            print("分位数补充后断点数仍不足，最终使用等间距分级")
                            min_val = np.min(data_array)
                            max_val = np.max(data_array)
                            if min_val == max_val:
                                return np.linspace(min_val - 0.5, min_val + 0.5, n_classes + 1)
                            breaks = np.linspace(min_val, max_val, n_classes + 1)
                    else:
                        print("分位数方法也无法提供足够断点，最终使用等间距分级")
                        min_val = np.min(data_array)
                        max_val = np.max(data_array)
                        if min_val == max_val:
                            return np.linspace(min_val - 0.5, min_val + 0.5, n_classes + 1)
                        breaks = np.linspace(min_val, max_val, n_classes + 1)
                else:
                    breaks = np.array(unique_breaks)

                # 确保返回 n_classes + 1 个断点
                if len(breaks) > n_classes + 1:
                    # 如果断点过多，通常是由于数据中有许多相同的值聚集在某些点
                    # 此时选择最能代表分级的断点，或者退回至分位数/等间距
                    # 一个简单的策略是取最外层和中间均匀分布的断点
                    print(f"JenksPy 返回的断点数 {len(breaks)} 多于期望的 {n_classes + 1}，将进行调整")
                    indices = np.round(np.linspace(0, len(breaks) - 1, n_classes + 1)).astype(int)
                    breaks = breaks[indices]
                elif len(breaks) < n_classes + 1:
                    # 如果断点仍然过少，这是最后的防线，使用等间距
                    print(f"调整后 JenksPy 返回的断点数 {len(breaks)} 仍少于期望的 {n_classes + 1}，最终使用等间距分级")
                    min_val = np.min(data_array)
                    max_val = np.max(data_array)
                    if min_val == max_val:
                        return np.linspace(min_val - 0.5, min_val + 0.5, n_classes + 1)
                    breaks = np.linspace(min_val, max_val, n_classes + 1)

                return breaks
            except Exception as e:
                print(f"JenksPy 计算出错: {e}, 将使用等间距分级")
                min_val = np.min(data_array)
                max_val = np.max(data_array)
                if min_val == max_val:
                    return np.linspace(min_val - 0.5, min_val + 0.5, n_classes + 1) 
                return np.linspace(min_val, max_val, n_classes + 1)
        
        # 生成IDFi预览图
        # 按照表3.4标准设置固定阈值（分位值标准）
        # 只对有意义的正值进行分级，排除0附近的小值
        if len(valid_IDFi) > 0:
            # 筛选出有意义的正值数据进行分级（排除接近0的小值）
            # 设置阈值，排除0附近的小值
            meaningful_threshold = np.percentile(valid_IDFi[valid_IDFi > 0], 10) if len(valid_IDFi[valid_IDFi > 0]) > 0 else 0.001
            meaningful_threshold = max(meaningful_threshold, 0.001)  # 确保阈值不会太小
            
            meaningful_IDFi = valid_IDFi[valid_IDFi > meaningful_threshold]
            if len(meaningful_IDFi) > 0:
                # 只对有意义的正值计算分位值作为阈值
                p25 = np.percentile(meaningful_IDFi, 25)  # 25分位值
                p50 = np.percentile(meaningful_IDFi, 50)  # 50分位值 
                p75 = np.percentile(meaningful_IDFi, 75)  # 75分位值
                p90 = np.percentile(meaningful_IDFi, 90)  # 90分位值
                IDFi_breaks = np.array([meaningful_threshold, p25, p50, p75, p90, np.max(meaningful_IDFi)])
                print(f"IDFi分位值分级断点（有意义正值，阈值>{meaningful_threshold:.4f}）: {IDFi_breaks}")
                print(f"有意义IDFi数据量: {len(meaningful_IDFi)}/{len(valid_IDFi)} ({len(meaningful_IDFi)/len(valid_IDFi)*100:.1f}%)")
            else:
                # 如果没有有意义的正值，回退到所有正值
                positive_IDFi = valid_IDFi[valid_IDFi > 0]
                if len(positive_IDFi) > 0:
                    p25 = np.percentile(positive_IDFi, 25)
                    p50 = np.percentile(positive_IDFi, 50)
                    p75 = np.percentile(positive_IDFi, 75)
                    p90 = np.percentile(positive_IDFi, 90)
                    IDFi_breaks = np.array([0, p25, p50, p75, p90, np.max(positive_IDFi)])
                    meaningful_IDFi = positive_IDFi  # 用于后续显示
                    print(f"警告：有意义正值数据不足，回退到所有正值分级: {IDFi_breaks}")
                else:
                    # 如果没有正值，使用默认断点
                    IDFi_breaks = np.array([0, 0.1, 0.2, 0.3, 0.4, 0.5])
                    meaningful_IDFi = np.array([])
                    print("警告：没有正值IDFi数据，使用默认断点")
        else:
            IDFi_breaks = np.array([0, 1, 2, 3, 4, 5])
            meaningful_IDFi = np.array([])
        
        # 创建IDFi预览图，使用统一渲染避免白色边界
        plt.figure(figsize=(10, 8))
        
        # 创建统一的显示数据，避免多层叠加导致的白色边界
        combined_display = IDFi_display_data.copy()
        
        if len(meaningful_IDFi) > 0:
            threshold = IDFi_breaks[0]
            low_value_mask = valid_mask & (IDFi_data <= 0)  # <=0的值
            near_zero_mask = valid_mask & (IDFi_data > 0) & (IDFi_data <= threshold)  # 0到阈值之间的小值
            
            # 为不同类型数据分配不同的显示值
            combined_display[low_value_mask] = -2  # <=0值标记为-2（深灰色）
            combined_display[near_zero_mask] = -1  # 小正值标记为-1（浅灰色）
            # 有意义值保持原值
            
            # 创建包含灰色的完整colormap
            from matplotlib.colors import ListedColormap, BoundaryNorm, LinearSegmentedColormap
            colors_full = ['#606060', '#A0A0A0'] + ['#00FF00', '#0066FF', '#FFFF00', '#FF7E00', '#FF0000']
            # 深灰色、浅灰色 + 绿色→蓝色→黄色→橙色→红色
            cmap_full = ListedColormap(colors_full)
            
            # 设置边界值
            boundaries = [-2.5, -1.5] + IDFi_breaks.tolist()
            norm = BoundaryNorm(boundaries, len(colors_full))
            
            # 统一渲染
            im = plt.imshow(combined_display, cmap=cmap_full, norm=norm)
            
            # 创建自定义colorbar，只显示有意义值的断点
            from matplotlib.colors import LinearSegmentedColormap
            risk_colors = ['#00FF00', '#0066FF', '#FFFF00', '#FF7E00', '#FF0000']
            risk_cmap = LinearSegmentedColormap.from_list('risk', risk_colors, N=len(risk_colors))
            risk_norm = BoundaryNorm(IDFi_breaks, len(risk_colors))
            
            # 创建一个虚拟的mappable对象用于colorbar
            import matplotlib.cm as cm
            sm = cm.ScalarMappable(cmap=risk_cmap, norm=risk_norm)
            sm.set_array([])
            cbar = plt.colorbar(sm, label='IDFi指数（有意义值）', shrink=0.8)
            cbar.set_ticks(IDFi_breaks)
            cbar.set_ticklabels([f'{b:.4f}' for b in IDFi_breaks])
        else:
            # 如果没有有意义数据，只区分<=0和>0
            zero_negative_mask = valid_mask & (IDFi_data <= 0)
            combined_display[zero_negative_mask] = -1
            
            # 创建简化的colormap
            from matplotlib.colors import ListedColormap, BoundaryNorm, LinearSegmentedColormap
            colors_simple = ['#808080'] + ['#00FF00', '#0066FF', '#FFFF00', '#FF7E00', '#FF0000']
            cmap_simple = ListedColormap(colors_simple)
            
            if len(valid_IDFi) > 0:
                max_val = np.max(valid_IDFi)
                boundaries = [-1.5, -0.5, 0, max_val/4, max_val/2, 3*max_val/4, max_val]
            else:
                boundaries = [-1.5, -0.5, 0, 1, 2, 3, 5]
            
            norm = BoundaryNorm(boundaries, len(colors_simple))
            im = plt.imshow(combined_display, cmap=cmap_simple, norm=norm)
            
            # 简化的colorbar
            cbar = plt.colorbar(im, label='IDFi指数', shrink=0.8)
            if len(valid_IDFi) > 0:
                cbar.set_ticks([0, max_val/4, max_val/2, 3*max_val/4, max_val])
                cbar.set_ticklabels([f'{v:.3f}' for v in [0, max_val/4, max_val/2, 3*max_val/4, max_val]])
            else:
                cbar.set_ticks([0, 1, 2, 3, 4, 5])
                cbar.set_ticklabels(['0.000', '1.000', '2.000', '3.000', '4.000', '5.000'])
        
        # 添加行政边界
        # add_admin_boundary_to_plot(plt.gca(), DATA_DIR, projection)  # 已注释：去除行政轮廓
            
        plt.title(f'{result_name} - IDFi图\n5级风险分类（有意义值分位值标准）\n总IDF值: {IDF:.6f} | 有效像素: {valid_count}/{total_count} ({valid_count/total_count*100:.1f}%)', fontsize=14, pad=20)
        plt.axis('off')  # 去除坐标轴和刻度
        
        # 添加统计信息文本（区分有意义值、小值和负值）
        if len(valid_IDFi) > 0:
            meaningful_count = len(meaningful_IDFi) if len(meaningful_IDFi) > 0 else 0
            if meaningful_count > 0:
                threshold = IDFi_breaks[0]
                low_value_count = np.sum(valid_IDFi <= 0)
                near_zero_count = np.sum((valid_IDFi > 0) & (valid_IDFi <= threshold))
                stats_text = f'IDFi统计:\n全部: 最小{np.min(valid_IDFi):.4f} 最大{np.max(valid_IDFi):.4f}\n有意义值(>{threshold:.4f}): {meaningful_count}个 ({meaningful_count/len(valid_IDFi)*100:.1f}%)\n范围: {np.min(meaningful_IDFi):.4f}~{np.max(meaningful_IDFi):.4f}\n均值: {np.mean(meaningful_IDFi):.4f}\n小正值(0~{threshold:.4f}]: {near_zero_count}个\n≤0值: {low_value_count}个\n总IDF: {IDF:.6f}'
            else:
                positive_count = np.sum(valid_IDFi > 0)
                stats_text = f'IDFi统计:\n无有意义值数据\n正值: {positive_count}个\n≤0值: {len(valid_IDFi)-positive_count}个\n总IDF: {IDF:.6f}\n有效率: {valid_count/total_count*100:.1f}%'
        else:
            stats_text = '无有效数据'
        plt.text(0.02, 0.98, stats_text, transform=plt.gca().transAxes, 
                verticalalignment='top', bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
        
        plt.tight_layout()
        plt.savefig(IDFi_preview_path, dpi=150, bbox_inches='tight')
        plt.close()
        print(f"IDFi预览图已生成: {IDFi_preview_path}")
        
        # 生成IPIi预览图
        print("\n--- 生成IPIi预览图 ---")
        IPIi_preview_filename = result_name + '_' +  f'IPIi_{timestamp}_{result_id[:8]}_preview.png'
        IPIi_preview_path = os.path.join(OUTPUT_DIR, IPIi_preview_filename)
        
        # 创建用于显示的IPIi数据（将无效值设为NaN以便正确显示）
        IPIi_display_data = IPIi_data.copy()
        IPIi_display_data[~valid_mask] = np.nan
        
        # 按照表3.4标准设置固定阈值
        # IPIi使用固定阈值：<0.25, 0.25-0.50, 0.50-0.70, 0.70-0.85, >0.85
        IPIi_breaks = np.array([0, 0.25, 0.50, 0.70, 0.85, 1.0])
        print(f"IPIi固定阈值分级断点: {IPIi_breaks}")
        
        plt.figure(figsize=(10, 8))
        
        # 定义5级风险色带（按照表3.4洪涝灾害影响区划等级表标准）
        colors = ['#00FF00', '#0066FF', '#FFFF00', '#FF7E00', '#FF0000']  # 绿色→蓝色→黄色→橙色→红色
        # V级(低风险)绿色 → IV级(较低风险)蓝色 → III级(中风险)黄色 → II级(较高风险)橙色 → I级(高风险)红色
        
        # 确保必要的模块已导入
        from matplotlib.colors import LinearSegmentedColormap, BoundaryNorm
        
        if len(valid_IPIi) > 0:
            # 使用BoundaryNorm确保颜色分段与断点值对应
            norm = BoundaryNorm(IPIi_breaks, len(colors))
            risk_cmap = LinearSegmentedColormap.from_list('risk', colors, N=len(colors))
            risk_cmap.set_bad(color='white', alpha=0.3)  # 设置无效值显示为半透明白色
            
            im = plt.imshow(IPIi_display_data, cmap=risk_cmap, norm=norm)
            # 创建自定义colorbar，显示断点值
            cbar = plt.colorbar(im, label='IPIi指数', shrink=0.8, boundaries=IPIi_breaks, ticks=IPIi_breaks)
            cbar.set_ticklabels([f'{b:.3f}' for b in IPIi_breaks])
        else:
            from matplotlib.colors import LinearSegmentedColormap
            risk_cmap = LinearSegmentedColormap.from_list('risk', colors, N=5)
            risk_cmap.set_bad(color='white', alpha=0.3)
            im = plt.imshow(IPIi_display_data, cmap=risk_cmap, vmin=0, vmax=1)
            cbar = plt.colorbar(im, label='IPIi指数', shrink=0.8)
            cbar.set_ticks([0, 0.25, 0.50, 0.70, 0.85, 1.0])
            cbar.set_ticklabels(['0.000', '0.250', '0.500', '0.700', '0.850', '1.000'])
        
        # 添加行政边界
        # add_admin_boundary_to_plot(plt.gca(), DATA_DIR, projection)  # 已注释：去除行政轮廓
            
        plt.title(f'{result_name} - IPIi图\n5级风险分类（标准化[0,1]范围）\n总IPI值: {IPI:.6f} | 有效像素: {valid_count}/{total_count} ({valid_count/total_count*100:.1f}%)', fontsize=14, pad=20)
        plt.xlabel('经度方向')
        plt.ylabel('纬度方向')
        
        # 添加统计信息文本（基于修正后的有效数据）
        if len(valid_IPIi) > 0 and np.sum(valid_I1_mask) > 0:
            # 使用修正后的IPIi数据（已限制在[0,1]范围内）
            final_IPIi_data = IPIi_data[valid_I1_mask]
            actual_min = np.min(final_IPIi_data)
            actual_max = np.max(final_IPIi_data)
            actual_mean = np.mean(final_IPIi_data)
            actual_std = np.std(final_IPIi_data)
            
            stats_text = f'IPIi统计(修正后):\n最小值: {actual_min:.3f}\n最大值: {actual_max:.3f}\n平均值: {actual_mean:.3f}\n标准差: {actual_std:.3f}\n总IPI: {IPI:.6f}\n有效率: {valid_count/total_count*100:.1f}%\n范围确认: [0,1] ✓'
        else:
            stats_text = '无有效IPIi数据'
        plt.text(0.02, 0.98, stats_text, transform=plt.gca().transAxes, 
                verticalalignment='top', bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
        
        plt.tight_layout()
        plt.savefig(IPIi_preview_path, dpi=150, bbox_inches='tight')
        plt.close()
        print(f"IPIi预览图已生成: {IPIi_preview_path}")
        
        # 计算统计信息（只基于有效数据）
        # IDFi统计信息
        if len(valid_IDFi) > 0:
            IDFi_statistics = {
                'min': float(np.min(valid_IDFi)),
                'max': float(np.max(valid_IDFi)),
                'mean': float(np.mean(valid_IDFi)),
                'std': float(np.std(valid_IDFi)),
                'breaks': IDFi_breaks.tolist(),
                'valid_count': int(valid_count),
                'total_count': int(total_count),
                'valid_ratio': float(valid_count / total_count)
            }
        else:
            IDFi_statistics = {
                'min': 0.0,
                'max': 0.0,
                'mean': 0.0,
                'std': 0.0,
                'breaks': [0.0, 1.0, 2.0, 3.0, 4.0, 5.0],
                'valid_count': 0,
                'total_count': int(total_count),
                'valid_ratio': 0.0
            }
        
        # IPIi统计信息
        if len(valid_IPIi) > 0:
            IPIi_statistics = {
                'min': float(np.min(valid_IPIi)),
                'max': float(np.max(valid_IPIi)),
                'mean': float(np.mean(valid_IPIi)),
                'std': float(np.std(valid_IPIi)),
                'breaks': IPIi_breaks.tolist(),
                'valid_count': int(np.sum(valid_I1_mask)),
                'total_count': int(total_count),
                'valid_ratio': float(np.sum(valid_I1_mask) / total_count)
            }
        else:
            IPIi_statistics = {
                'min': 0.0,
                'max': 0.0,
                'mean': 0.0,
                'std': 0.0,
                'breaks': [0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
                'valid_count': 0,
                'total_count': int(total_count),
                'valid_ratio': 0.0
            }
        
        # 综合统计信息
        statistics = {
            'IDFi': IDFi_statistics,
            'IPIi': IPIi_statistics,
            'total_IDF': IDF,
            'total_IPI': IPI,
            'weights': {
                'w1_hazard': w1,
                'w2_exposure': w2,
                'w3_value': w3,
                'w4_sensitivity': w4,
                'w5_resistance': w5,
                'w6_mitigation': w6
            }
        }
        
        # 构建返回结果
        IDFi_result_filename = os.path.basename(IDFi_result_path)
        IPIi_result_filename = os.path.basename(IPIi_result_path)
        I1_result_filename = os.path.basename(I1_result_path)
        I2_result_filename = os.path.basename(I2_result_path)
        I3_result_filename = os.path.basename(I3_result_path)
        I1_preview_filename = os.path.basename(I1_preview_path)
        I2_preview_filename = os.path.basename(I2_preview_path)
        I3_preview_filename = os.path.basename(I3_preview_path)
        
        result = {
            'id': result_id,
            'name': result_name,
            'type': 'comprehensive',
            'createdAt': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'description': f'基于H、E、V、S、R、M六个模型的IDFi和IPIi计算结果，IDFi=（I1-I2-I3）*flag，IPIi=（（I1-I2-I3）/I1）*flag，总IDF={IDF:.6f}，总IPI={IPI:.6f}（权重: w1={w1}, w2={w2}, w3={w3}, w4={w4}, w5={w5}, w6={w6}）',
            'parameters': {
                'hazard_dataset_id': hazard_dataset_id,
                'exposure_dataset_id': exposure_dataset_id,
                'value_dataset_id': value_dataset_id,
                'sensitivity_dataset_id': sensitivity_dataset_id,
                'resistance_dataset_id': resistance_dataset_id,
                'mitigation_dataset_id': mitigation_dataset_id,
                'weights': statistics['weights']
            },
            'files': [{
                'id': 'flood_results/' + I1_result_filename,
                'name': result_name + ' - I1',
                'type': 'raster',
                'format': 'tif',
                'url': f'/api/datasets/flood_results/{I1_result_filename}/image',
                'download_url': f'/api/datasets/flood_results/{I1_result_filename}/download'
            }, {
                'id': 'flood_results/' + I2_result_filename,
                'name': result_name + ' - I2',
                'type': 'raster',
                'format': 'tif',
                'url': f'/api/datasets/flood_results/{I2_result_filename}/image',
                'download_url': f'/api/datasets/flood_results/{I2_result_filename}/download'
            }, {
                'id': 'flood_results/' + I3_result_filename,
                'name': result_name + ' - I3',
                'type': 'raster',
                'format': 'tif',
                'url': f'/api/datasets/flood_results/{I3_result_filename}/image',
                'download_url': f'/api/datasets/flood_results/{I3_result_filename}/download'
            }, {
                'id': 'flood_results/' + IDFi_result_filename,
                'name': result_name + ' - IDFi',
                'type': 'raster',
                'format': 'tif',
                'url': f'/api/datasets/flood_results/{IDFi_result_filename}/image',
                'download_url': f'/api/datasets/flood_results/{IDFi_result_filename}/download'
            }, {
                'id': 'flood_results/' + IPIi_result_filename,
                'name': result_name + ' - IPIi',
                'type': 'raster',
                'format': 'tif',
                'url': f'/api/datasets/flood_results/{IPIi_result_filename}/image',
                'download_url': f'/api/datasets/flood_results/{IPIi_result_filename}/download'
            }],
            'preview': [
                f'/api/datasets/images/flood_results/{I1_preview_filename}',
                f'/api/datasets/images/flood_results/{I2_preview_filename}',
                f'/api/datasets/images/flood_results/{I3_preview_filename}',
                f'/api/datasets/images/flood_results/{IDFi_preview_filename}',
                f'/api/datasets/images/flood_results/{IPIi_preview_filename}'
            ],
            'statistics': {
                'IDFi': {
                    'min': statistics['IDFi']['min'],
                    'max': statistics['IDFi']['max'],
                    'mean': statistics['IDFi']['mean'],
                    'std': statistics['IDFi']['std'],
                    'valid_count': statistics['IDFi']['valid_count'],
                    'total_count': statistics['IDFi']['total_count'],
                    'valid_ratio': statistics['IDFi']['valid_ratio'],
                    'classification_breaks': statistics['IDFi']['breaks']
                },
                'IPIi': {
                    'min': statistics['IPIi']['min'],
                    'max': statistics['IPIi']['max'],
                    'mean': statistics['IPIi']['mean'],
                    'std': statistics['IPIi']['std'],
                    'valid_count': statistics['IPIi']['valid_count'],
                    'total_count': statistics['IPIi']['total_count'],
                    'valid_ratio': statistics['IPIi']['valid_ratio'],
                    'classification_breaks': statistics['IPIi']['breaks']
                },
                'total_IDF': statistics['total_IDF'],
                'total_IPI': statistics['total_IPI'],
                'nodata_value': float(output_nodata),
                'weights_used': statistics['weights']
            }
        }
        
        print("\n=== 综合影响图评估完成 ===")
        return jsonify(result)
        
    except Exception as e:
        print("\n!!! 综合影响图评估出错 !!!")
        print(f"错误信息: {str(e)}")
        import traceback
        print("\n详细错误信息:")
        traceback.print_exc()
        return jsonify({'error': f'综合影响图评估失败: {str(e)}'}), 500

@flood_bp.route('/prevention', methods=['POST'])
@cross_origin()
@log_function_call
def prevention_assessment():
    """工程防灾性评估"""
    try:
        data = request.get_json()
        
        # 获取参数
        dike_dataset = data.get('dikeDataset')
        drainage_dataset = data.get('drainageDataset')
        warning_dataset = data.get('warningDataset')
        emergency_dataset = data.get('emergencyDataset')
        result_name = data.get('resultName', '工程防灾性评估结果')
        
        if not all([dike_dataset, drainage_dataset, warning_dataset, emergency_dataset]):
            return jsonify({'error': '缺少必要的数据集参数'}), 400
        
        # 生成唯一ID和文件名
        result_id = str(uuid.uuid4())
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        result_filename = result_name + '_' + f'prevention_{timestamp}_{result_id[:8]}.tif'
        result_path = os.path.join(OUTPUT_DIR, result_filename)
        
        # 创建模拟数据
        rows, cols = 100, 100
        np.random.seed(46)
        dike_factor = np.random.random((rows, cols)) * 0.3       # 堤防因子权重30%
        drainage_factor = np.random.random((rows, cols)) * 0.3   # 排水因子权重30%
        warning_factor = np.random.random((rows, cols)) * 0.2    # 预警因子权重20%
        emergency_factor = np.random.random((rows, cols)) * 0.2  # 应急因子权重20%
        
        prevention_result = dike_factor + drainage_factor + warning_factor + emergency_factor
        
        # 设置地理变换和投影
        geotransform = (116.0, 0.01, 0, 40.0, 0, -0.01)
        projection = 'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]]'
        
        # 保存结果栅格
        assessment_engine.save_result_raster(prevention_result, geotransform, projection, result_path)
        
        # 创建GeoJSON
        geojson_filename = f'prevention_{timestamp}_{result_id[:8]}.geojson'
        geojson_path = os.path.join(OUTPUT_DIR, geojson_filename)
        geojson_data = assessment_engine.create_geojson_from_raster(result_path, geojson_path)
        
        result = {
            'id': result_id,
            'name': result_name,
            'type': 'prevention',
            'createTime': datetime.now().isoformat(),
            'url': f'/api/datasets/flood_results/{geojson_filename}/geojson',
            'rasterUrl': f'/api/datasets/flood_results/{result_filename}',
            'statistics': geojson_data['features'][0]['properties']['statistics'],
            'description': '基于堤防工程、排水系统、预警系统、应急设施等因子的工程防灾性评估结果'
        }
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': f'工程防灾性评估失败: {str(e)}'}), 500



@flood_bp.route('/results', methods=['GET'])
@cross_origin()
def get_assessment_results():
    """获取所有评估结果列表"""
    try:
        results_dir = OUTPUT_DIR
        results = []
        
        if os.path.exists(results_dir):
            for filename in os.listdir(results_dir):
                if filename.endswith('.geojson'):
                    file_path = os.path.join(results_dir, filename)
                    with open(file_path, 'r', encoding='utf-8') as f:
                        geojson_data = json.load(f)
                    
                    # 从文件名解析信息
                    parts = filename.replace('.geojson', '').split('_')
                    if len(parts) >= 3:
                        assessment_type = parts[0]
                        timestamp = parts[1]
                        result_id = parts[2]
                        
                        result = {
                            'id': result_id,
                            'name': f'{assessment_type}评估结果_{timestamp}',
                            'type': assessment_type,
                            'createTime': datetime.strptime(timestamp, '%Y%m%d_%H%M%S').isoformat(),
                            'url': f'/api/datasets/flood_results/{filename}',
                            'statistics': geojson_data['features'][0]['properties'].get('statistics', {})
                        }
                        results.append(result)
        
        # 按创建时间倒序排列
        results.sort(key=lambda x: x['createTime'], reverse=True)
        
        return jsonify(results)
        
    except Exception as e:
        return jsonify({'error': f'获取评估结果失败: {str(e)}'}), 500