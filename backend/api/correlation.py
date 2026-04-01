import os
import uuid
import json
from flask import Blueprint, request, jsonify, current_app, send_file
from werkzeug.utils import secure_filename
from .datasets import get_dataset_path, get_dataset_by_id
from .utils import ensure_directory_exists
from utils.相关性分析 import RasterCorrelationAnalysis

# 创建蓝图
correlation_bp = Blueprint('correlation', __name__, url_prefix='/correlation')

# 存储相关性分析结果的目录
CORRELATION_RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'correlation_analysis_results')
ensure_directory_exists(CORRELATION_RESULTS_DIR)

# 存储相关性分析结果的内存缓存
correlation_results = []

@correlation_bp.route('/analyze', methods=['POST'])
def analyze_correlation():
    """执行相关性分析"""
    try:
        # 获取请求参数
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': '无效的请求数据'}), 400
        
        dataset_ids = data.get('dataset_ids', [])
        result_name = data.get('result_name', f'correlation_analysis_{uuid.uuid4().hex[:8]}')
        correlation_method = data.get('correlation_method', 'pearson')  # pearson 或 spearman
        raster_names = data.get('raster_names', [])  # 自定义栅格名称
        
        if not dataset_ids or len(dataset_ids) < 2:
            return jsonify({'success': False, 'message': '至少需要选择2个数据集进行相关性分析'}), 400
        
        if correlation_method not in ['pearson', 'spearman']:
            return jsonify({'success': False, 'message': '相关性方法必须是pearson或spearman'}), 400
        
        # 验证栅格名称数量
        if raster_names and len(raster_names) != len(dataset_ids):
            return jsonify({'success': False, 'message': '栅格名称数量必须与数据集数量一致'}), 400
        
        # 验证数据集并获取路径
        raster_paths = []
        dataset_names = []
        
        for i, dataset_id in enumerate(dataset_ids):
            dataset_info = get_dataset_by_id(dataset_id)
            if not dataset_info:
                return jsonify({'success': False, 'message': f'找不到ID为{dataset_id}的数据集'}), 404
            
            dataset_path = get_dataset_path(dataset_id)
            if not dataset_path or not os.path.exists(dataset_path):
                return jsonify({'success': False, 'message': f'数据集文件不存在: {dataset_id}'}), 404
            
            # 检查是否为栅格数据
            if dataset_info.get('type') != 'raster':
                return jsonify({'success': False, 'message': f'数据集{dataset_id}不是栅格数据'}), 400
            
            raster_paths.append(dataset_path)
            # 使用自定义名称或默认名称
            if raster_names and i < len(raster_names) and raster_names[i].strip():
                dataset_names.append(raster_names[i].strip())
            else:
                dataset_names.append(dataset_info.get('name', f'Dataset_{dataset_id}'))
        
        print(f'开始执行相关性分析: {dataset_names}')
        # 执行相关性分析
        analysis_result = perform_correlation_analysis(
            raster_paths, 
            dataset_names, 
            result_name, 
            correlation_method
        )
        
        # 生成唯一ID
        analysis_id = uuid.uuid4().hex
        
        # 添加到结果列表
        result = {
            'id': analysis_id,
            'name': result_name,
            'method': correlation_method,
            'dataset_count': len(dataset_ids),
            'created_at': str(analysis_result['timestamp']),
            'file_paths': analysis_result['file_paths']
        }
        correlation_results.append(result)
        
        # 创建文件列表
        files = []
        
        # 添加热力图文件
        if 'heatmap' in analysis_result['file_paths']:
            heatmap_basename = os.path.basename(analysis_result['file_paths']['heatmap'])
            files.append({
                "id": f"correlation_analysis_results\\{heatmap_basename}",
                "name": "相关性热力图",
                "type": "image",
                "format": "png",
                "url": f"/api/datasets/images/correlation_analysis_results/{heatmap_basename}",
                "downloadUrl": f"/api/datasets/correlation_analysis_results\\{heatmap_basename}/download"
            })
        
        # 添加散点图矩阵文件
        if 'scatter_matrix' in analysis_result['file_paths']:
            scatter_basename = os.path.basename(analysis_result['file_paths']['scatter_matrix'])
            files.append({
                "id": f"correlation_analysis_results\\{scatter_basename}",
                "name": "散点图矩阵",
                "type": "image",
                "format": "png",
                "url": f"/api/datasets/images/correlation_analysis_results/{scatter_basename}",
                "downloadUrl": f"/api/datasets/correlation_analysis_results\\{scatter_basename}/download"
            })
        
        # 添加报告文件
        if 'report' in analysis_result['file_paths']:
            report_basename = os.path.basename(analysis_result['file_paths']['report'])
            files.append({
                "id": f"correlation_analysis_results\\{report_basename}",
                "name": "相关性分析报告",
                "type": "document",
                "format": "txt",
                "downloadUrl": f"/api/datasets/correlation_analysis_results\\{report_basename}/download"
            })
        
        # 添加相关性矩阵CSV文件
        if 'correlation_matrix' in analysis_result['file_paths']:
            matrix_basename = os.path.basename(analysis_result['file_paths']['correlation_matrix'])
            files.append({
                "id": f"correlation_analysis_results\\{matrix_basename}",
                "name": "相关性矩阵数据",
                "type": "data",
                "format": "csv",
                "downloadUrl": f"/api/datasets/correlation_analysis_results\\{matrix_basename}/download"
            })
        
        # 返回结果
        result = {
            "id": analysis_id,
            "name": result_name,
            "type": "correlation_analysis",
            "status": "complete",
            "createdAt": str(analysis_result['timestamp']),
            "files": files,
            "properties": {
                "method": correlation_method,
                "datasetCount": len(dataset_ids),
                "datasetNames": dataset_names
            }
        }
        
        return jsonify(result)
    
    except Exception as e:
        current_app.logger.error(f'相关性分析时出错: {str(e)}')
        return jsonify({'success': False, 'message': f'相关性分析时出错: {str(e)}'}), 500


def perform_correlation_analysis(raster_paths, dataset_names, result_name, correlation_method):
    """执行相关性分析
    
    参数:
        raster_paths (list): 栅格文件路径列表
        dataset_names (list): 数据集名称列表
        result_name (str): 结果文件名
        correlation_method (str): 相关性方法 ('pearson' 或 'spearman')
    
    返回:
        dict: 分析结果信息
    """
    import numpy as np
    from datetime import datetime
    
    # 创建相关性分析器
    analyzer = RasterCorrelationAnalysis(output_dir=CORRELATION_RESULTS_DIR)
    
    # 加载栅格数据
    for i, raster_path in enumerate(raster_paths):
        analyzer.load_raster(raster_path, dataset_names[i])
    
    # 计算相关性矩阵
    corr_matrix, df_clean = analyzer.calculate_correlation_matrix(method=correlation_method)
    
    # 生成文件名前缀
    file_prefix = secure_filename(result_name)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # 生成文件名前缀（包含时间戳）
    file_prefix_with_timestamp = f'{file_prefix}_{timestamp}'
    
    # 生成热力图
    fig_heatmap, ax_heatmap, _ = analyzer.plot_correlation_heatmap(method=correlation_method, figsize=(12, 10), save_plot=True, file_prefix=file_prefix_with_timestamp)
    heatmap_path = os.path.join(CORRELATION_RESULTS_DIR, f'{file_prefix_with_timestamp}_correlation_heatmap_{correlation_method}.png')
    
    # 生成散点图矩阵
    fig_scatter = analyzer.plot_scatter_matrix(figsize=(15, 15), save_plot=True, file_prefix=file_prefix_with_timestamp)
    scatter_matrix_path = os.path.join(CORRELATION_RESULTS_DIR, f'{file_prefix_with_timestamp}_scatter_matrix.png')
    
    # 生成报告
    results = analyzer.generate_correlation_report(methods=[correlation_method], file_prefix=file_prefix_with_timestamp)
    report_path = os.path.join(CORRELATION_RESULTS_DIR, f'{file_prefix_with_timestamp}_correlation_report_{correlation_method}.txt')
    
    # 保存相关性矩阵为CSV
    matrix_path = os.path.join(CORRELATION_RESULTS_DIR, f'{file_prefix}_{timestamp}_correlation_matrix.csv')
    corr_matrix.to_csv(matrix_path, encoding='utf-8-sig')
    
    # 返回结果信息
    return {
        'timestamp': datetime.now(),
        'file_paths': {
            'heatmap': heatmap_path,
            'scatter_matrix': scatter_matrix_path,
            'report': report_path,
            'correlation_matrix': matrix_path
        }
    }