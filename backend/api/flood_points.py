import os
import uuid
import json
import numpy as np
import rasterio
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app, send_file
from scipy.ndimage import maximum_filter, minimum_filter, gaussian_filter
import geopandas as gpd
from shapely.geometry import Point
from .datasets import get_dataset_path, get_dataset_by_id
from .utils import ensure_directory_exists

# 创建蓝图
flood_points_bp = Blueprint('flood_points', __name__, url_prefix='/flood-points')

# 存储生成的易涝点结果的目录
FLOOD_POINTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'flood_points')
ensure_directory_exists(FLOOD_POINTS_DIR)

def calculate_flow_direction(dem_array):
    """
    计算流向 - 使用D8算法
    返回流向矩阵，值为0-7代表8个方向
    """
    rows, cols = dem_array.shape
    flow_dir = np.full((rows, cols), -1, dtype=np.int8)
    
    # D8方向编码：从正东开始顺时针
    # 0:东, 1:东南, 2:南, 3:西南, 4:西, 5:西北, 6:北, 7:东北
    directions = [
        (0, 1),   # 东
        (1, 1),   # 东南
        (1, 0),   # 南
        (1, -1),  # 西南
        (0, -1),  # 西
        (-1, -1), # 西北
        (-1, 0),  # 北
        (-1, 1)   # 东北
    ]
    
    for i in range(1, rows-1):
        for j in range(1, cols-1):
            center_elev = dem_array[i, j]
            if np.isnan(center_elev):
                continue
                
            max_slope = -1
            steepest_dir = -1
            
            for dir_idx, (di, dj) in enumerate(directions):
                ni, nj = i + di, j + dj
                if 0 <= ni < rows and 0 <= nj < cols:
                    neighbor_elev = dem_array[ni, nj]
                    if not np.isnan(neighbor_elev):
                        # 计算坡度
                        if di == 0 or dj == 0:  # 正交方向
                            distance = 1.0
                        else:  # 对角方向
                            distance = np.sqrt(2)
                        
                        slope = (center_elev - neighbor_elev) / distance
                        if slope > max_slope:
                            max_slope = slope
                            steepest_dir = dir_idx
            
            flow_dir[i, j] = steepest_dir
    
    return flow_dir

def calculate_flow_accumulation_improved(dem_array, flow_dir):
    """
    改进的流向累积计算
    """
    rows, cols = dem_array.shape
    flow_acc = np.ones((rows, cols), dtype=np.float32)
    
    # 按高程排序处理（从高到低）
    valid_mask = ~np.isnan(dem_array)
    elevations = dem_array[valid_mask]
    indices = np.where(valid_mask)
    
    # 创建按高程排序的索引
    sort_indices = np.argsort(elevations)[::-1]  # 从高到低
    
    directions = [
        (0, 1),   # 东
        (1, 1),   # 东南
        (1, 0),   # 南
        (1, -1),  # 西南
        (0, -1),  # 西
        (-1, -1), # 西北
        (-1, 0),  # 北
        (-1, 1)   # 东北
    ]
    
    # 按从高到低的顺序处理每个像元
    for idx in sort_indices:
        i, j = indices[0][idx], indices[1][idx]
        
        if flow_dir[i, j] >= 0:  # 有有效流向
            di, dj = directions[flow_dir[i, j]]
            ni, nj = i + di, j + dj
            
            if 0 <= ni < rows and 0 <= nj < cols:
                flow_acc[ni, nj] += flow_acc[i, j]
    
    return flow_acc

def calculate_topographic_wetness_index(dem_array, flow_acc, resolution):
    """
    计算地形湿润指数 (TWI)
    TWI = ln(a / tan(β))
    其中 a 是单位等高线长度的汇流面积，β 是坡度角
    """
    # 计算坡度
    dx, dy = np.gradient(dem_array, resolution)
    slope_rad = np.arctan(np.sqrt(dx*dx + dy*dy))
    
    # 避免除零
    slope_rad = np.maximum(slope_rad, 0.001)  # 最小坡度0.001弧度
    
    # 计算单位等高线长度的汇流面积
    specific_catchment_area = flow_acc * resolution * resolution / resolution
    
    # 计算TWI
    twi = np.log(specific_catchment_area / np.tan(slope_rad))
    
    return twi, np.degrees(slope_rad)

def identify_depression_points(dem_array, window_size=5):
    """
    识别地形洼地点
    """
    # 使用更大的窗口识别局部最低点
    local_min = dem_array == minimum_filter(dem_array, size=window_size)
    
    # 计算洼地深度
    local_max = maximum_filter(dem_array, size=window_size)
    depression_depth = local_max - dem_array
    
    return local_min, depression_depth

def identify_flood_points(dem_path, accumulation_threshold=1000, twi_threshold=10, 
                         depression_depth_threshold=0.5, min_distance=3):
    """
    识别易涝点 - 改进版本
    """
    with rasterio.open(dem_path) as src:
        dem_array = src.read(1).astype(np.float32)
        transform = src.transform
        resolution = abs(transform[0])  # 像元分辨率
        
        # 处理无效值
        dem_array[dem_array <= -9999] = np.nan
        
        # 平滑DEM以减少噪声
        dem_smoothed = gaussian_filter(dem_array, sigma=0.5)
        valid_mask = ~np.isnan(dem_smoothed)
        
        print(f"DEM shape: {dem_array.shape}, Resolution: {resolution}")
        print(f"Valid pixels: {np.sum(valid_mask)}")
        
        # 计算流向
        print("计算流向...")
        flow_dir = calculate_flow_direction(dem_smoothed)
        
        # 计算流向累积
        print("计算流向累积...")
        flow_acc = calculate_flow_accumulation_improved(dem_smoothed, flow_dir)
        
        # 计算地形湿润指数
        print("计算地形湿润指数...")
        twi, slope_degrees = calculate_topographic_wetness_index(dem_smoothed, flow_acc, resolution)
        
        # 识别洼地点
        print("识别洼地点...")
        local_min, depression_depth = identify_depression_points(dem_smoothed)
        
        # 综合判断易涝点
        flood_points_mask = (
            valid_mask &                                    # 有效数据
            (flow_acc >= accumulation_threshold) &          # 汇流累积量大
            (twi >= twi_threshold) &                       # 地形湿润指数高
            (depression_depth >= depression_depth_threshold) &  # 洼地深度足够
            local_min                                      # 局部低点
        )
        
        print(f"初步识别的易涝点数量: {np.sum(flood_points_mask)}")
        
        # 获取易涝点位置
        flood_indices = np.where(flood_points_mask)
        
        # 筛选点位，确保最小距离
        if len(flood_indices[0]) > 0:
            selected_points = []
            points_coords = list(zip(flood_indices[0], flood_indices[1]))
            
            # 按TWI值排序，优先选择TWI高的点
            twi_values = [twi[i, j] for i, j in points_coords]
            sorted_indices = np.argsort(twi_values)[::-1]
            
            for idx in sorted_indices:
                i, j = points_coords[idx]
                
                # 检查与已选点的距离
                too_close = False
                for selected_i, selected_j in selected_points:
                    distance = np.sqrt((i - selected_i)**2 + (j - selected_j)**2)
                    if distance < min_distance:
                        too_close = True
                        break
                
                if not too_close:
                    selected_points.append((i, j))
            
            print(f"筛选后的易涝点数量: {len(selected_points)}")
            
            # 构建GeoJSON特征
            points = []
            for i, j in selected_points:
                x, y = rasterio.transform.xy(transform, i, j)
                points.append({
                    'type': 'Feature',
                    'geometry': {
                        'type': 'Point',
                        'coordinates': [x, y]
                    },
                    'properties': {
                        'elevation': float(dem_array[i, j]) if not np.isnan(dem_array[i, j]) else None,
                        'flow_accumulation': float(flow_acc[i, j]),
                        'slope_degrees': float(slope_degrees[i, j]),
                        'twi': float(twi[i, j]),
                        'depression_depth': float(depression_depth[i, j]),
                        'risk_level': 'high' if twi[i, j] > twi_threshold * 1.5 else 'medium'
                    }
                })
        else:
            points = []
        
        # 获取数据范围
        bounds = src.bounds
        
        return {
            'type': 'FeatureCollection',
            'features': points,
            'bounds': {
                'minx': bounds.left,
                'miny': bounds.bottom,
                'maxx': bounds.right,
                'maxy': bounds.top
            },
            'statistics': {
                'total_candidates': int(np.sum(flood_points_mask)),
                'selected_points': len(points),
                'flow_acc_range': [float(np.nanmin(flow_acc)), float(np.nanmax(flow_acc))],
                'twi_range': [float(np.nanmin(twi)), float(np.nanmax(twi))],
                'slope_range': [float(np.nanmin(slope_degrees)), float(np.nanmax(slope_degrees))]
            }
        }

@flood_points_bp.route('/calculate', methods=['POST'])
def calculate():
    """计算易涝点"""
    try:
        # 获取请求参数
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': '无效的请求数据'}), 400
        
        dataset_id = data.get('dataset_id')
        accumulation_threshold = float(data.get('accumulation_threshold', 1000))
        twi_threshold = float(data.get('twi_threshold', 2))
        depression_depth_threshold = float(data.get('depression_depth_threshold', 0.5))
        min_distance = int(data.get('min_distance', 3))
        result_name = data.get('result_name', f'flood_points_{uuid.uuid4().hex[:8]}')
        
        if not dataset_id:
            return jsonify({'success': False, 'message': '未提供数据集ID'}), 400
        
        # 获取数据集路径
        dataset_info = get_dataset_by_id(dataset_id)
        if not dataset_info:
            return jsonify({'success': False, 'message': f'找不到ID为{dataset_id}的数据集'}), 404
        
        dataset_path = get_dataset_path(dataset_id)
        if not dataset_path or not os.path.exists(dataset_path):
            return jsonify({'success': False, 'message': f'数据集文件不存在'}), 404
        
        # 生成易涝点
        result = identify_flood_points(
            dataset_path,
            accumulation_threshold,
            twi_threshold,
            depression_depth_threshold,
            min_distance
        )
        
        # 生成唯一ID
        result_id = uuid.uuid4().hex
        
        # 构建文件名
        file_basename = f'{result_name}_points'
        
        # 保存为GeoJSON文件
        geojson_path = os.path.join(FLOOD_POINTS_DIR, f'{file_basename}.geojson')
        with open(geojson_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        # 转换为GeoDataFrame并保存为Shapefile
        features = result['features']
        if features:
            geometries = [Point(f['geometry']['coordinates']) for f in features]
            properties = [f['properties'] for f in features]
            gdf = gpd.GeoDataFrame(properties, geometry=geometries)
            
            shp_path = os.path.join(FLOOD_POINTS_DIR, f'{file_basename}.shp')
            gdf.to_file(shp_path, encoding='utf-8')
        
        # 创建文件列表
        files = [
            {
                "id": f"flood_points\\{file_basename}.geojson",
                "name": file_basename,
                "type": "vector",
                "format": "geojson",
                "url": f"/api/datasets/flood_points/{file_basename}.geojson/geojson"
            }
        ]
        
        # 返回结果
        response = {
            "id": result_id,
            "name": file_basename,
            "type": "flood_points",
            "status": "complete",
            "createdAt": datetime.now().isoformat(),
            "files": files,
            "properties": {
                "sourceLayer": dataset_id,
                "accumulationThreshold": accumulation_threshold,
                "twiThreshold": twi_threshold,
                "depressionDepthThreshold": depression_depth_threshold,
                "minDistance": min_distance,
                "extent": {
                    "xmin": float(result['bounds']['minx']),
                    "ymin": float(result['bounds']['miny']),
                    "xmax": float(result['bounds']['maxx']),
                    "ymax": float(result['bounds']['maxy'])
                },
                "pointCount": len(features),
                "statistics": result['statistics']
            }
        }
        
        return jsonify(response)
    
    except Exception as e:
        current_app.logger.error(f'计算易涝点时出错: {str(e)}')
        return jsonify({'success': False, 'message': f'计算易涝点时出错: {str(e)}'}), 500

@flood_points_bp.route('/<result_id>/download', methods=['GET'])
def download_result(result_id):
    """下载易涝点数据"""
    try:
        # 查找易涝点文件
        shp_file = None
        for file in os.listdir(FLOOD_POINTS_DIR):
            file_path = os.path.join(FLOOD_POINTS_DIR, file)
            if os.path.isfile(file_path) and file.endswith('.geojson'):
                # 检查是否是对应的文件
                file_id = uuid.uuid5(uuid.NAMESPACE_DNS, file).hex
                if file_id == result_id:
                    # 找到对应的shapefile
                    shp_filename = os.path.splitext(file)[0] + '.shp'
                    shp_file = os.path.join(FLOOD_POINTS_DIR, shp_filename)
                    break
        
        if not shp_file or not os.path.exists(shp_file):
            return jsonify({'success': False, 'message': f'找不到ID为{result_id}的易涝点数据文件'}), 404
        
        # 发送文件
        return send_file(shp_file, as_attachment=True)
    
    except Exception as e:
        current_app.logger.error(f'下载易涝点数据时出错: {str(e)}')
        return jsonify({'success': False, 'message': f'下载易涝点数据时出错: {str(e)}'}), 500