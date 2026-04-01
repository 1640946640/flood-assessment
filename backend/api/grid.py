import os
import uuid
import json
import geopandas as gpd
import numpy as np
import rasterio
from rasterio.transform import from_bounds
from rasterio.features import rasterize
from shapely.geometry import box, Polygon, MultiPolygon
from flask import Blueprint, request, jsonify, current_app, send_file
from werkzeug.utils import secure_filename
from .datasets import get_dataset_path, get_dataset_by_id
from .utils import ensure_directory_exists

# 创建蓝图
raster_bp = Blueprint('raster', __name__, url_prefix='/raster')

# 存储生成的栅格结果的目录
RASTER_RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'raster_results')
ensure_directory_exists(RASTER_RESULTS_DIR)

# 存储栅格结果的内存缓存
raster_results = []

@raster_bp.route('/generate', methods=['POST'])
def generate_raster_template():
    """生成栅格模板数据"""
    try:
        # 获取请求参数
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': '无效的请求数据'}), 400
        
        dataset_id = data.get('dataset_id')
        resolution = float(data.get('resolution', 30.0))  # 分辨率，单位：米
        result_name = data.get('result_name', f'raster_template_{uuid.uuid4().hex[:8]}')
        
        if not dataset_id:
            return jsonify({'success': False, 'message': '未提供数据集ID'}), 400
        
        if resolution <= 0:
            return jsonify({'success': False, 'message': '分辨率必须大于0'}), 400
        
        # 获取数据集路径
        dataset_info = get_dataset_by_id(dataset_id)
        if not dataset_info:
            return jsonify({'success': False, 'message': f'找不到ID为{dataset_id}的数据集'}), 404
        
        dataset_path = get_dataset_path(dataset_id)
        if not dataset_path or not os.path.exists(dataset_path):
            return jsonify({'success': False, 'message': f'数据集文件不存在'}), 404
        
        # 读取矢量数据
        gdf = gpd.read_file(dataset_path)
        
        # 检查是否为面数据
        if not all(isinstance(geom, (Polygon, MultiPolygon)) for geom in gdf.geometry):
            return jsonify({'success': False, 'message': '数据集不是面矢量数据'}), 400
        
        # 生成栅格模板
        raster_path, raster_info = create_raster_template(gdf, resolution, result_name)
        
        # 生成唯一ID
        raster_id = uuid.uuid4().hex
        
        # 添加到结果列表
        result = {
            'id': raster_id,
            'name': result_name,
            'resolution': resolution,
            'created_at': str(np.datetime64('now')),
            'file_path': raster_path
        }
        raster_results.append(result)
        
        # 获取数据范围
        min_x, min_y, max_x, max_y = raster_info['bounds']
        
        # 获取文件名（不含路径）
        file_basename = os.path.splitext(os.path.basename(raster_path))[0]
        
        # 创建文件列表
        files = [
            {
                "id": f"raster_results\\{os.path.basename(raster_path)}",
                "name": file_basename,
                "type": "raster",
                "format": "tiff",
                "url": f"/api/datasets/raster_results/{os.path.basename(raster_path)}/image"
            }
        ]
        
        # 返回结果（与analysis.py格式保持一致）
        result = {
            "id": raster_id,
            "name": file_basename,
            "type": "raster_template",
            "status": "complete",
            "createdAt": str(np.datetime64('now')),
            "files": files,
            "properties": {
                "sourceLayer": dataset_id,
                "resolution": resolution,
                "extent": {
                    "xmin": float(min_x),
                    "ymin": float(min_y),
                    "xmax": float(max_x),
                    "ymax": float(max_y)
                },
                "width": raster_info['width'],
                "height": raster_info['height']
            }
        }
        
        return jsonify(result)
    
    except Exception as e:
        current_app.logger.error(f'生成栅格模板时出错: {str(e)}')
        return jsonify({'success': False, 'message': f'生成栅格模板时出错: {str(e)}'}), 500



@raster_bp.route('/<raster_id>/download', methods=['GET'])
def download_raster(raster_id):
    """下载栅格数据"""
    try:
        # 查找栅格文件
        raster_file = None
        for result in raster_results:
            if result['id'] == raster_id:
                raster_file = result['file_path']
                break
        
        if not raster_file or not os.path.exists(raster_file):
            return jsonify({'success': False, 'message': f'找不到ID为{raster_id}的栅格数据文件'}), 404
        
        # 发送文件
        return send_file(raster_file, as_attachment=True)
    
    except Exception as e:
        current_app.logger.error(f'下载栅格数据时出错: {str(e)}')
        return jsonify({'success': False, 'message': f'下载栅格数据时出错: {str(e)}'}), 500

def create_raster_template(gdf, resolution, result_name):
    """根据输入的面数据创建栅格模板
    
    参数:
        gdf (GeoDataFrame): 输入的面数据
        resolution (float): 栅格分辨率，单位：米
        result_name (str): 结果文件名
    
    返回:
        tuple: (raster_path, raster_info) 栅格文件路径和信息
    """
    # 检查坐标系并进行必要的转换
    original_crs = gdf.crs
    
    # 如果是地理坐标系（经纬度），需要转换为投影坐标系
    if gdf.crs and gdf.crs.is_geographic:
        # 获取数据的中心点来选择合适的UTM投影
        bounds = gdf.total_bounds
        center_lon = (bounds[0] + bounds[2]) / 2
        center_lat = (bounds[1] + bounds[3]) / 2
        
        # 根据中心经度计算UTM带号
        utm_zone = int((center_lon + 180) / 6) + 1
        
        # 根据纬度确定南北半球
        hemisphere = 'north' if center_lat >= 0 else 'south'
        
        # 构建UTM坐标系
        utm_crs = f'EPSG:{32600 + utm_zone if hemisphere == "north" else 32700 + utm_zone}'
        
        # 转换坐标系
        gdf_projected = gdf.to_crs(utm_crs)
        current_app.logger.info(f'坐标系已从 {original_crs} 转换为 {utm_crs}')
    else:
        # 如果已经是投影坐标系，直接使用
        gdf_projected = gdf.copy()
        current_app.logger.info(f'使用原始坐标系: {original_crs}')
    
    # 获取转换后数据的总边界
    minx, miny, maxx, maxy = gdf_projected.total_bounds
    
    # 计算栅格的宽度和高度（像素数）
    width = int(np.ceil((maxx - minx) / resolution))
    height = int(np.ceil((maxy - miny) / resolution))
    
    # 调整边界以适应像素网格
    maxx = minx + width * resolution
    maxy = miny + height * resolution
    
    # 创建仿射变换
    transform = from_bounds(minx, miny, maxx, maxy, width, height)
    
    # 将矢量数据栅格化
    shapes = [(geom, 1) for geom in gdf_projected.geometry]
    rasterized = rasterize(shapes, out_shape=(height, width), transform=transform, fill=0, dtype=np.uint8)
    
    # 构建文件路径
    file_basename = f'{secure_filename(result_name)}_template_{int(resolution)}m'
    raster_path = os.path.join(RASTER_RESULTS_DIR, f'{file_basename}.tif')
    
    # 保存栅格文件（使用投影后的坐标系）
    with rasterio.open(
        raster_path,
        'w',
        driver='GTiff',
        height=height,
        width=width,
        count=1,
        dtype=rasterized.dtype,
        crs=gdf_projected.crs,
        transform=transform,
        compress='lzw',
        nodata=0  # 设置nodata值为0，表示无效区域
    ) as dst:
        dst.write(rasterized, 1)
    
    # 返回文件路径和信息（边界坐标为投影坐标系）
    raster_info = {
        'bounds': (minx, miny, maxx, maxy),
        'width': width,
        'height': height,
        'resolution': resolution,
        'crs': str(gdf_projected.crs),
        'original_crs': str(original_crs)
    }
    
    return raster_path, raster_info