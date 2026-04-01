import os
import uuid
import json
import numpy as np
import pandas as pd
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app, send_file
from werkzeug.utils import secure_filename
from .datasets import get_dataset_path, get_dataset_by_id
from .utils import ensure_directory_exists
import rasterio

# 创建蓝图
raster_statistics_bp = Blueprint('raster_statistics', __name__)

# 存储栅格统计结果的目录
RASTER_STATISTICS_RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'raster_statistics_results')
ensure_directory_exists(RASTER_STATISTICS_RESULTS_DIR)

# 存储栅格统计结果的内存缓存
statistics_results = []

@raster_statistics_bp.route('/analyze', methods=['POST'])
def analyze_raster_statistics():
    """执行栅格统计分析"""
    try:
        # 获取请求参数
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': '无效的请求数据'}), 400
        
        dataset_id = data.get('dataset_id')
        statistics_type = data.get('statistics_type', 'single_value')  # single_value 或 range_value
        result_name = data.get('result_name', f'raster_statistics_{uuid.uuid4().hex[:8]}')
        
        if not dataset_id:
            return jsonify({'success': False, 'message': '请选择一个数据集'}), 400
        
        if statistics_type not in ['single_value', 'range_value']:
            return jsonify({'success': False, 'message': '统计类型必须是single_value或range_value'}), 400
        
        # 验证数据集并获取路径
        dataset_info = get_dataset_by_id(dataset_id)
        if not dataset_info:
            return jsonify({'success': False, 'message': f'找不到ID为{dataset_id}的数据集'}), 404
        
        dataset_path = get_dataset_path(dataset_id)
        if not dataset_path or not os.path.exists(dataset_path):
            return jsonify({'success': False, 'message': f'数据集文件不存在: {dataset_id}'}), 404
        
        # 检查是否为栅格数据
        if dataset_info.get('type') != 'raster':
            return jsonify({'success': False, 'message': f'数据集{dataset_id}不是栅格数据'}), 400
        
        # 获取统计参数
        if statistics_type == 'single_value':
            single_value = data.get('single_value')
            if single_value is None:
                return jsonify({'success': False, 'message': '请提供要统计的单一值'}), 400
            statistics_params = {'single_value': single_value}
        else:  # range_value
            min_value = data.get('min_value')
            max_value = data.get('max_value')
            if min_value is None or max_value is None:
                return jsonify({'success': False, 'message': '请提供值范围的最小值和最大值'}), 400
            if min_value > max_value:
                return jsonify({'success': False, 'message': '最小值不能大于最大值'}), 400
            statistics_params = {'min_value': min_value, 'max_value': max_value}
        
        print(f'开始执行栅格统计: {dataset_info.get("name")}')
        
        # 执行栅格统计分析
        analysis_result = perform_raster_statistics(
            dataset_path,
            dataset_info.get('name', f'Dataset_{dataset_id}'),
            statistics_type,
            statistics_params,
            result_name
        )
        
        # 生成唯一ID
        analysis_id = uuid.uuid4().hex
        
        # 添加到结果列表
        result = {
            'id': analysis_id,
            'name': result_name,
            'type': 'raster_statistics',
            'status': 'complete',
            'createdAt': str(analysis_result['timestamp']),
            'csvUrl': f'/api/datasets/raster_statistics_results/{analysis_result["csv_filename"]}/download',
            'statistics': analysis_result['statistics'],
            'properties': {
                'statisticsType': statistics_type,
                'datasetName': dataset_info.get('name', f'Dataset_{dataset_id}')
            }
        }
        
        statistics_results.append(result)
        
        return jsonify(result)
    
    except Exception as e:
        current_app.logger.error(f'栅格统计分析时出错: {str(e)}')
        return jsonify({'success': False, 'message': f'栅格统计分析时出错: {str(e)}'}), 500


def perform_raster_statistics(raster_path, dataset_name, statistics_type, statistics_params, result_name):
    """执行栅格统计分析
    
    参数:
        raster_path (str): 栅格文件路径
        dataset_name (str): 数据集名称
        statistics_type (str): 统计类型 ('single_value' 或 'range_value')
        statistics_params (dict): 统计参数
        result_name (str): 结果文件名
    
    返回:
        dict: 分析结果信息
    """
    
    # 读取栅格数据
    with rasterio.open(raster_path) as src:
        # 读取栅格数据
        raster_data = src.read(1)  # 读取第一个波段
        nodata_value = src.nodata
        
        # 获取栅格基本信息
        height, width = raster_data.shape
        total_pixels = height * width
        
        # 自动计算像元大小
        transform = src.transform
        crs = src.crs
        
        # 获取像元的X和Y方向分辨率
        pixel_width = abs(transform[0])  # X方向像元大小
        pixel_height = abs(transform[4])  # Y方向像元大小
        
        # 判断坐标系类型并计算面积
        if crs and crs.is_geographic:
            # 地理坐标系（经纬度），需要转换为米
            # 使用栅格中心点的纬度来计算
            bounds = src.bounds
            center_lat = (bounds.bottom + bounds.top) / 2
            
            # 在给定纬度下，1度经度和1度纬度对应的米数
            import math
            lat_rad = math.radians(center_lat)
            meters_per_degree_lon = 111320 * math.cos(lat_rad)
            meters_per_degree_lat = 110540
            
            # 计算像元面积（平方米）
            pixel_area = (pixel_width * meters_per_degree_lon) * (pixel_height * meters_per_degree_lat)
            pixel_size_info = f"地理坐标系: {pixel_width:.6f}°×{pixel_height:.6f}° (约{math.sqrt(pixel_area):.2f}m)"
        else:
            # 投影坐标系，单位通常是米
            pixel_area = pixel_width * pixel_height
            pixel_size_info = f"投影坐标系: {pixel_width:.2f}m×{pixel_height:.2f}m"
        
        # 处理nodata值
        if nodata_value is not None:
            valid_mask = raster_data != nodata_value
            valid_data = raster_data[valid_mask]
        else:
            valid_mask = np.ones_like(raster_data, dtype=bool)
            valid_data = raster_data.flatten()
        
        valid_count = np.sum(valid_mask)
        
        # 根据统计类型计算目标值
        if statistics_type == 'single_value':
            target_value = statistics_params['single_value']
            target_mask = (raster_data == target_value) & valid_mask
            target_count = np.sum(target_mask)
            statistics_value_text = str(target_value)
        else:  # range_value
            min_val = statistics_params['min_value']
            max_val = statistics_params['max_value']
            target_mask = (raster_data >= min_val) & (raster_data <= max_val) & valid_mask
            target_count = np.sum(target_mask)
            statistics_value_text = f"{min_val}-{max_val}"
        
        # 计算统计数据
        target_ratio = target_count / valid_count if valid_count > 0 else 0
        target_area = target_count * pixel_area
        valid_area = valid_count * pixel_area
        total_area = total_pixels * pixel_area
        
        # 准备统计结果
        statistics_data = {
            'datasetName': dataset_name,
            'statisticsType': statistics_type,
            'pixelWidth': float(pixel_width),
            'pixelHeight': float(pixel_height),
            'pixelArea': float(pixel_area),
            'pixelSizeInfo': pixel_size_info,
            'coordinateSystem': str(crs) if crs else 'Unknown',
            'totalCount': int(total_pixels),
            'validCount': int(valid_count),
            'targetCount': int(target_count),
            'targetRatio': float(target_ratio),
            'targetArea': float(target_area),
            'validArea': float(valid_area),
            'totalArea': float(total_area)
        }
        
        # 添加统计参数到结果中
        if statistics_type == 'single_value':
            statistics_data['singleValue'] = statistics_params['single_value']
        else:
            statistics_data['minValue'] = statistics_params['min_value']
            statistics_data['maxValue'] = statistics_params['max_value']
        
        # 生成CSV数据
        csv_data = {
            '数据集名称': [dataset_name],
            '统计类型': ['单一值统计' if statistics_type == 'single_value' else '范围值统计'],
            '统计值/范围': [statistics_value_text],
            '坐标系': [str(crs) if crs else 'Unknown'],
            '像元大小信息': [pixel_size_info],
            '像元宽度': [pixel_width],
            '像元高度': [pixel_height],
            '像元面积(m²)': [pixel_area],
            '总像元数量': [total_pixels],
            '有效像元数量': [valid_count],
            '目标值像元数量': [target_count],
            '目标值占比(%)': [target_ratio * 100],
            '目标值面积(m²)': [target_area],
            '有效值面积(m²)': [valid_area],
            '总面积(m²)': [total_area],
            '分析时间': [datetime.now().strftime('%Y-%m-%d %H:%M:%S')]
        }
        
        # 保存CSV文件
        df = pd.DataFrame(csv_data)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        csv_filename = f'{secure_filename(result_name)}_{timestamp}_statistics.csv'
        csv_path = os.path.join(RASTER_STATISTICS_RESULTS_DIR, csv_filename)
        df.to_csv(csv_path, index=False, encoding='utf-8-sig')
        
        # 返回结果信息
        return {
            'timestamp': datetime.now(),
            'csv_filename': csv_filename,
            'csv_path': csv_path,
            'statistics': statistics_data
        }


@raster_statistics_bp.route('/results', methods=['GET'])
def get_statistics_results():
    """获取栅格统计结果列表"""
    try:
        return jsonify({
            'success': True,
            'results': statistics_results
        })
    except Exception as e:
        current_app.logger.error(f'获取栅格统计结果时出错: {str(e)}')
        return jsonify({'success': False, 'message': f'获取结果时出错: {str(e)}'}), 500


@raster_statistics_bp.route('/results/<result_id>', methods=['GET'])
def get_statistics_result(result_id):
    """获取特定的栅格统计结果"""
    try:
        result = next((r for r in statistics_results if r['id'] == result_id), None)
        if not result:
            return jsonify({'success': False, 'message': '找不到指定的统计结果'}), 404
        
        return jsonify({
            'success': True,
            'result': result
        })
    except Exception as e:
        current_app.logger.error(f'获取栅格统计结果时出错: {str(e)}')
        return jsonify({'success': False, 'message': f'获取结果时出错: {str(e)}'}), 500