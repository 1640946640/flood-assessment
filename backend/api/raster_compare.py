import os
import uuid
import json
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app, send_file
from werkzeug.utils import secure_filename
from .datasets import get_dataset_path, get_dataset_by_id
from .utils import ensure_directory_exists
from utils.compare2model import calculate_masked_ratio

# 创建蓝图
raster_compare_bp = Blueprint('raster_compare', __name__, url_prefix='/raster_compare')

# 存储栅格比较分析结果的目录
RASTER_COMPARE_RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'raster_compare_results')
ensure_directory_exists(RASTER_COMPARE_RESULTS_DIR)

# 存储栅格比较分析结果的内存缓存
raster_compare_results = []

@raster_compare_bp.route('/analyze', methods=['POST'])
def analyze_raster_compare():
    """执行栅格比较分析"""
    try:
        # 获取请求参数
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': '无效的请求数据'}), 400
        
        mask_dataset_id = data.get('mask_dataset_id')
        target_dataset_ids = data.get('target_dataset_ids', [])
        result_name = data.get('result_name', f'raster_compare_{uuid.uuid4().hex[:8]}')
        
        if not mask_dataset_id:
            return jsonify({'success': False, 'message': '必须指定掩膜数据集'}), 400
        
        if not target_dataset_ids:
            return jsonify({'success': False, 'message': '必须指定至少一个目标数据集'}), 400
        
        # 验证掩膜数据集
        mask_dataset_info = get_dataset_by_id(mask_dataset_id)
        if not mask_dataset_info:
            return jsonify({'success': False, 'message': f'找不到ID为{mask_dataset_id}的掩膜数据集'}), 404
        
        mask_dataset_path = get_dataset_path(mask_dataset_id)
        if not mask_dataset_path or not os.path.exists(mask_dataset_path):
            return jsonify({'success': False, 'message': f'掩膜数据集文件不存在: {mask_dataset_id}'}), 404
        
        # 验证目标数据集
        target_paths = []
        target_names = []
        
        for target_id in target_dataset_ids:
            target_info = get_dataset_by_id(target_id)
            if not target_info:
                return jsonify({'success': False, 'message': f'找不到ID为{target_id}的目标数据集'}), 404
            
            target_path = get_dataset_path(target_id)
            if not target_path or not os.path.exists(target_path):
                return jsonify({'success': False, 'message': f'目标数据集文件不存在: {target_id}'}), 404
            
            target_paths.append(target_path)
            target_names.append(target_info.get('name', f'dataset_{target_id}'))
        
        # 生成唯一的分析ID和时间戳
        analysis_id = f"raster_compare_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        timestamp = datetime.now()
        file_prefix = f"{result_name}_{timestamp.strftime('%Y%m%d_%H%M%S')}"
        
        # 执行栅格比较分析
        analysis_results = []
        file_paths = {}
        
        for i, (target_path, target_name) in enumerate(zip(target_paths, target_names)):
            try:
                # 计算掩膜比例
                result = calculate_masked_ratio(
                    mask_raster_path=mask_dataset_path,
                    target_raster_path=target_path,
                    output_stats=False
                )
                
                result['target_dataset_id'] = target_dataset_ids[i]
                result['target_dataset_name'] = target_name
                analysis_results.append(result)
                
            except Exception as e:
                print(f"处理目标数据集 {target_name} 时发生错误: {str(e)}")
                continue
        
        if not analysis_results:
            return jsonify({'success': False, 'message': '所有目标数据集处理失败'}), 500
        
        # 生成分析报告
        report_filename = f"{file_prefix}_analysis_report.txt"
        report_path = os.path.join(RASTER_COMPARE_RESULTS_DIR, report_filename)
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(f"栅格比较分析报告\n")
            f.write(f"="*50 + "\n")
            f.write(f"分析名称: {result_name}\n")
            f.write(f"分析时间: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"掩膜数据集: {mask_dataset_info.get('name', mask_dataset_id)}\n")
            f.write(f"目标数据集数量: {len(analysis_results)}\n\n")
            
            for i, result in enumerate(analysis_results):
                f.write(f"目标数据集 {i+1}: {result['target_dataset_name']}\n")
                f.write(f"  总像元数: {result['total_pixels']:,}\n")
                f.write(f"  掩膜区域像元数: {result['mask_pixels']:,}\n")
                f.write(f"  掩膜区域比例: {result['mask_ratio']:.4f} ({result['mask_ratio']*100:.2f}%)\n")
                f.write(f"  掩膜区域内有效像元数: {result['valid_pixels_in_mask']:,}\n")
                f.write(f"  掩膜区域内有效像元比例: {result['valid_ratio_in_mask']:.4f} ({result['valid_ratio_in_mask']*100:.2f}%)\n")
                f.write(f"  相对于总像元的比例: {result['valid_ratio_total']:.4f} ({result['valid_ratio_total']*100:.2f}%)\n")
                
                if 'min_value' in result:
                    f.write(f"  数值统计:\n")
                    f.write(f"    最小值: {result['min_value']:.6f}\n")
                    f.write(f"    最大值: {result['max_value']:.6f}\n")
                    f.write(f"    均值: {result['mean_value']:.6f}\n")
                    f.write(f"    中位数: {result['median_value']:.6f}\n")
                    f.write(f"    标准差: {result['std_value']:.6f}\n")
                
                f.write("\n")
        
        file_paths['report'] = report_path
        
        # 生成CSV结果文件
        import pandas as pd
        csv_filename = f"{file_prefix}_results.csv"
        csv_path = os.path.join(RASTER_COMPARE_RESULTS_DIR, csv_filename)
        
        df = pd.DataFrame(analysis_results)
        df.to_csv(csv_path, index=False, encoding='utf-8')
        file_paths['csv'] = csv_path
        
        # 存储分析结果
        analysis_result = {
            'id': analysis_id,
            'name': result_name,
            'timestamp': timestamp,
            'mask_dataset_id': mask_dataset_id,
            'mask_dataset_name': mask_dataset_info.get('name', mask_dataset_id),
            'target_dataset_ids': target_dataset_ids,
            'target_dataset_names': target_names,
            'results': analysis_results,
            'file_paths': file_paths
        }
        
        raster_compare_results.append(analysis_result)
        
        return jsonify({
            'success': True,
            'message': '栅格比较分析完成',
            'analysis_id': analysis_id,
            'results_count': len(analysis_results),
            'file_paths': file_paths
        })
        
    except Exception as e:
        print(f"栅格比较分析过程中发生错误: {str(e)}")
        return jsonify({'success': False, 'message': f'分析失败: {str(e)}'}), 500

@raster_compare_bp.route('/results', methods=['GET'])
def get_raster_compare_results():
    """获取栅格比较分析结果列表"""
    try:
        results = []
        
        for analysis_result in raster_compare_results:
            analysis_id = analysis_result['id']
            files = []
            
            # 添加报告文件
            if 'report' in analysis_result['file_paths']:
                report_basename = os.path.basename(analysis_result['file_paths']['report'])
                files.append({
                    "id": f"raster_compare_results/{report_basename}",
                    "name": "栅格比较分析报告",
                    "type": "document",
                    "format": "txt",
                    "downloadUrl": f"/api/datasets/raster_compare_results/{report_basename}/download"
                })
            
            # 添加CSV结果文件
            if 'csv' in analysis_result['file_paths']:
                csv_basename = os.path.basename(analysis_result['file_paths']['csv'])
                files.append({
                    "id": f"raster_compare_results/{csv_basename}",
                    "name": "栅格比较结果数据",
                    "type": "data",
                    "format": "csv",
                    "downloadUrl": f"/api/datasets/raster_compare_results/{csv_basename}/download"
                })
            
            # 添加掩膜后的栅格文件
            if 'masked_files' in analysis_result['file_paths']:
                for masked_file in analysis_result['file_paths']['masked_files']:
                    masked_basename = os.path.basename(masked_file)
                    files.append({
                        "id": f"raster_compare_results/{masked_basename}",
                        "name": f"掩膜后栅格 - {masked_basename}",
                        "type": "raster",
                        "format": "tif",
                        "downloadUrl": f"/api/datasets/raster_compare_results/{masked_basename}/download"
                    })
            
            # 返回结果
            result = {
                "id": analysis_id,
                "name": analysis_result['name'],
                "type": "raster_compare_analysis",
                "status": "complete",
                "createdAt": str(analysis_result['timestamp']),
                "files": files,
                "properties": {
                    "maskDatasetName": analysis_result['mask_dataset_name'],
                    "targetDatasetCount": len(analysis_result['target_dataset_ids']),
                    "targetDatasetNames": analysis_result['target_dataset_names'],
                }
            }
            
            results.append(result)
        
        return jsonify({
            'success': True,
            'results': results
        })
        
    except Exception as e:
        print(f"获取栅格比较分析结果时发生错误: {str(e)}")
        return jsonify({'success': False, 'message': f'获取结果失败: {str(e)}'}), 500

@raster_compare_bp.route('/<analysis_id>/download/<file_type>', methods=['GET'])
def download_raster_compare_file(analysis_id, file_type):
    """下载栅格比较分析文件"""
    try:
        # 在结果目录中查找匹配的文件
        for filename in os.listdir(RASTER_COMPARE_RESULTS_DIR):
            if analysis_id in filename:
                if file_type == 'report' and filename.endswith('_analysis_report.txt'):
                    file_path = os.path.join(RASTER_COMPARE_RESULTS_DIR, filename)
                    return send_file(file_path, as_attachment=True, download_name=filename)
                elif file_type == 'csv' and filename.endswith('_results.csv'):
                    file_path = os.path.join(RASTER_COMPARE_RESULTS_DIR, filename)
                    return send_file(file_path, as_attachment=True, download_name=filename)
                elif file_type == 'masked' and 'masked' in filename and filename.endswith('.tif'):
                    file_path = os.path.join(RASTER_COMPARE_RESULTS_DIR, filename)
                    return send_file(file_path, as_attachment=True, download_name=filename)
        
        return jsonify({'success': False, 'message': '文件未找到'}), 404
        
    except Exception as e:
        print(f"下载文件时发生错误: {str(e)}")
        return jsonify({'success': False, 'message': f'下载失败: {str(e)}'}), 500