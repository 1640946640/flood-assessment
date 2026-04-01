from flask import Blueprint, request, jsonify, send_file
from flask_cors import cross_origin
import os
import numpy as np
import pandas as pd
from osgeo import gdal
import rasterio
from rasterio.transform import xy
import tempfile
import uuid
from datetime import datetime
import io
import sys

# 添加utils目录到路径
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'utils'))
from export_csv import export_multi_raster_to_csv

export_bp = Blueprint('export', __name__, url_prefix='/api/export')

# 数据文件夹路径
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

class CSVExporter:
    """CSV导出工具类"""
    
    def __init__(self):
        pass
    
    def read_raster_data(self, raster_path):
        """读取栅格数据"""
        try:
            with rasterio.open(raster_path) as src:
                data = src.read(1)
                transform = src.transform
                crs = src.crs
                nodata = src.nodata
                bounds = src.bounds
                
            return {
                'data': data,
                'transform': transform,
                'crs': crs,
                'nodata': nodata,
                'bounds': bounds
            }
        except Exception as e:
            raise Exception(f"读取栅格文件失败 {raster_path}: {str(e)}")
    
    def get_coordinates_from_indices(self, transform, rows, cols):
        """从像素索引获取地理坐标"""
        xs, ys = xy(transform, rows, cols)
        return np.array(xs), np.array(ys)
    
    def extract_valid_data(self, risk_data, dem_data, risk_nodata, dem_nodata, 
                          include_nodata=False, include_zero=True):
        """提取有效数据点"""
        # 创建掩膜
        risk_valid = risk_data != risk_nodata if risk_nodata is not None else np.ones_like(risk_data, dtype=bool)
        dem_valid = dem_data != dem_nodata if dem_nodata is not None else np.ones_like(dem_data, dtype=bool)
        
        if include_nodata:
            # 包含无数据值
            valid_mask = np.ones_like(risk_data, dtype=bool)
        else:
            # 只包含两个栅格都有效的数据
            valid_mask = risk_valid & dem_valid
        
        if not include_zero:
            # 排除零值
            zero_mask = (risk_data == 0) | (dem_data == 0)
            valid_mask = valid_mask & (~zero_mask)
        
        return valid_mask
    
    def create_csv_data(self, risk_info, dem_info, include_nodata=False, include_zero=True):
        """创建CSV数据"""
        risk_data = risk_info['data']
        dem_data = dem_info['data']
        risk_transform = risk_info['transform']
        
        # 检查数据形状是否一致
        if risk_data.shape != dem_data.shape:
            raise Exception("风险栅格和DEM栅格的尺寸不一致")
        
        # 提取有效数据
        valid_mask = self.extract_valid_data(
            risk_data, dem_data, 
            risk_info['nodata'], dem_info['nodata'],
            include_nodata, include_zero
        )
        
        # 获取有效数据的行列索引
        valid_rows, valid_cols = np.where(valid_mask)
        
        if len(valid_rows) == 0:
            raise Exception("没有找到有效的数据点")
        
        # 获取地理坐标
        x_coords, y_coords = self.get_coordinates_from_indices(
            risk_transform, valid_rows, valid_cols
        )
        
        # 提取对应的数据值
        risk_values = risk_data[valid_rows, valid_cols]
        dem_values = dem_data[valid_rows, valid_cols]
        
        # 创建DataFrame
        df = pd.DataFrame({
            'X坐标': x_coords,
            'Y坐标': y_coords,
            '高程': dem_values,
            '风险值': risk_values
        })
        
        # 处理无数据值的显示
        if include_nodata:
            # 将nodata值替换为特殊标记
            if risk_info['nodata'] is not None:
                df.loc[df['风险值'] == risk_info['nodata'], '风险值'] = 'NoData'
            if dem_info['nodata'] is not None:
                df.loc[df['高程'] == dem_info['nodata'], '高程'] = 'NoData'
        
        return df

@export_bp.route('/csv-preview', methods=['POST'])
@cross_origin()
def csv_preview():
    """CSV数据预览"""
    try:
        data = request.get_json()
        risk_raster_id = data.get('risk_raster')
        dem_raster_id = data.get('dem_raster')
        include_nodata = data.get('include_nodata', False)
        include_zero = data.get('include_zero', True)
        preview_count = data.get('preview_count', 10)
        
        if not risk_raster_id or not dem_raster_id:
            return jsonify({'error': '缺少必要的栅格文件参数'}), 400
        
        # 构建文件路径
        risk_path = os.path.join(DATA_DIR, risk_raster_id)
        dem_path = os.path.join(DATA_DIR, dem_raster_id)
        
        # 检查文件是否存在
        if not os.path.exists(risk_path):
            return jsonify({'error': f'风险栅格文件不存在: {risk_raster_id}'}), 404
        if not os.path.exists(dem_path):
            return jsonify({'error': f'DEM栅格文件不存在: {dem_raster_id}'}), 404
        
        # 创建导出器
        exporter = CSVExporter()
        
        # 读取栅格数据
        risk_info = exporter.read_raster_data(risk_path)
        dem_info = exporter.read_raster_data(dem_path)
        
        # 创建CSV数据
        df = exporter.create_csv_data(risk_info, dem_info, include_nodata, include_zero)
        
        # 获取预览数据
        preview_df = df.head(preview_count)
        preview_data = preview_df.to_dict('records')
        
        # 格式化预览数据
        for record in preview_data:
            if isinstance(record['X坐标'], (int, float)):
                record['x'] = round(record['X坐标'], 2)
            else:
                record['x'] = record['X坐标']
                
            if isinstance(record['Y坐标'], (int, float)):
                record['y'] = round(record['Y坐标'], 2)
            else:
                record['y'] = record['Y坐标']
                
            if isinstance(record['高程'], (int, float)):
                record['elevation'] = round(record['高程'], 2)
            else:
                record['elevation'] = record['高程']
                
            if isinstance(record['风险值'], (int, float)):
                record['risk'] = round(record['风险值'], 4)
            else:
                record['risk'] = record['风险值']
        
        return jsonify({
            'preview_data': preview_data,
            'total_count': len(df),
            'coordinate_system': str(risk_info['crs'])
        })
        
    except Exception as e:
        print(f"CSV预览错误: {str(e)}")
        return jsonify({'error': f'CSV预览失败: {str(e)}'}), 500

@export_bp.route('/csv', methods=['POST'])
@cross_origin()
def export_csv():
    """导出CSV文件"""
    try:
        data = request.get_json()
        risk_raster_id = data.get('risk_raster')
        dem_raster_id = data.get('dem_raster')
        include_nodata = data.get('include_nodata', False)
        include_zero = data.get('include_zero', True)
        
        if not risk_raster_id or not dem_raster_id:
            return jsonify({'error': '缺少必要的栅格文件参数'}), 400
        
        # 构建文件路径
        risk_path = os.path.join(DATA_DIR, risk_raster_id)
        dem_path = os.path.join(DATA_DIR, dem_raster_id)
        
        # 检查文件是否存在
        if not os.path.exists(risk_path):
            return jsonify({'error': f'风险栅格文件不存在: {risk_raster_id}'}), 404
        if not os.path.exists(dem_path):
            return jsonify({'error': f'DEM栅格文件不存在: {dem_raster_id}'}), 404
        
        print(f"开始导出CSV: 风险栅格={risk_raster_id}, DEM={dem_raster_id}")
        
        # 创建导出器
        exporter = CSVExporter()
        
        # 读取栅格数据
        print("读取栅格数据...")
        risk_info = exporter.read_raster_data(risk_path)
        dem_info = exporter.read_raster_data(dem_path)
        
        # 创建CSV数据
        print("处理数据...")
        df = exporter.create_csv_data(risk_info, dem_info, include_nodata, include_zero)
        
        print(f"生成CSV数据，共 {len(df)} 行")
        
        # 添加元数据注释
        metadata_lines = [
            f"# 洪涝风险评估数据导出",
            f"# 导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"# 风险栅格: {risk_raster_id}",
            f"# DEM栅格: {dem_raster_id}",
            f"# 坐标系统: {risk_info['crs']}",
            f"# 数据点数量: {len(df)}",
            f"# 包含无数据值: {'是' if include_nodata else '否'}",
            f"# 包含零值: {'是' if include_zero else '否'}",
            f"#"
        ]
        
        # 创建内存中的CSV文件
        output = io.StringIO()
        
        # 写入元数据注释
        for line in metadata_lines:
            output.write(line + '\n')
        
        # 写入CSV数据
        df.to_csv(output, index=False, encoding='utf-8-sig')
        
        # 获取CSV内容
        csv_content = output.getvalue()
        output.close()
        
        # 创建字节流
        csv_bytes = io.BytesIO(csv_content.encode('utf-8-sig'))
        
        # 生成文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'risk_elevation_data_{timestamp}.csv'
        
        print(f"CSV导出完成: {filename}")
        
        return send_file(
            csv_bytes,
            mimetype='text/csv',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        print(f"CSV导出错误: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'CSV导出失败: {str(e)}'}), 500

@export_bp.route('/raster-info/<raster_id>', methods=['GET'])
@cross_origin()
def get_raster_info(raster_id):
    """获取栅格文件信息"""
    try:
        raster_path = os.path.join(DATA_DIR, raster_id)
        
        if not os.path.exists(raster_path):
            return jsonify({'error': f'栅格文件不存在: {raster_id}'}), 404
        
        with rasterio.open(raster_path) as src:
            info = {
                'crs': str(src.crs),
                'bounds': src.bounds,
                'width': src.width,
                'height': src.height,
                'nodata': src.nodata,
                'dtype': str(src.dtypes[0]),
                'transform': list(src.transform)
            }
        
        return jsonify(info)
        
    except Exception as e:
        print(f"获取栅格信息错误: {str(e)}")
        return jsonify({'error': f'获取栅格信息失败: {str(e)}'}), 500

@export_bp.route('/multi-raster-csv', methods=['POST'])
@cross_origin()
def export_multi_raster_csv():
    """多栅格CSV导出接口"""
    try:
        data = request.get_json()
        
        # 获取参数
        raster_files = data.get('raster_files', [])
        raster_names = data.get('raster_names', [])
        align_method = data.get('align_method', 'nearest')
        
        if not raster_files:
            return jsonify({'error': '请选择至少一个栅格文件'}), 400
        
        if len(raster_names) != len(raster_files):
            return jsonify({'error': '栅格名称数量必须与栅格文件数量一致'}), 400
        
        # 构建完整文件路径
        raster_paths = []
        for raster_file in raster_files:
            raster_path = os.path.join(DATA_DIR, raster_file)
            if not os.path.exists(raster_path):
                return jsonify({'error': f'栅格文件不存在: {raster_file}'}), 404
            raster_paths.append(raster_path)
        
        print(f"开始多栅格CSV导出: {len(raster_files)} 个文件")
        print(f"栅格文件: {raster_files}")
        print(f"栅格名称: {raster_names}")
        
        # 生成临时输出文件路径
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        temp_filename = f'multi_raster_export_{timestamp}.csv'
        temp_output_path = os.path.join(tempfile.gettempdir(), temp_filename)
        
        # 调用优化的导出函数
        result_count = export_multi_raster_to_csv(
            raster_paths=raster_paths,
            output_csv_path=temp_output_path,
            raster_names=raster_names,
            align_method=align_method
        )
        
        print(f"多栅格CSV导出完成: {result_count} 个数据点")
        
        # 读取生成的CSV文件
        with open(temp_output_path, 'r', encoding='utf-8') as f:
            csv_content = f.read()
        
        # 添加元数据注释
        metadata_lines = [
            f"# 多栅格数据导出",
            f"# 导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"# 栅格文件数量: {len(raster_files)}",
            f"# 栅格文件: {', '.join(raster_files)}",
            f"# 栅格名称: {', '.join(raster_names)}",
            f"# 对齐方法: {align_method}",
            f"# 坐标系统: WGS84 (EPSG:4326)",
            f"# 数据点数量: {result_count}",
            f"#"
        ]
        
        # 组合元数据和CSV内容
        final_content = '\n'.join(metadata_lines) + '\n' + csv_content
        
        # 创建字节流
        csv_bytes = io.BytesIO(final_content.encode('utf-8-sig'))
        
        # 清理临时文件
        try:
            os.remove(temp_output_path)
        except:
            pass
        
        # 生成下载文件名
        download_filename = f'multi_raster_data_{timestamp}.csv'
        
        return send_file(
            csv_bytes,
            mimetype='text/csv',
            as_attachment=True,
            download_name=download_filename
        )
        
    except Exception as e:
        print(f"多栅格CSV导出错误: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'多栅格CSV导出失败: {str(e)}'}), 500

@export_bp.route('/available-rasters', methods=['GET'])
@cross_origin()
def get_available_rasters():
    """获取可用的栅格文件列表"""
    try:
        raster_files = []
        
        # 扫描数据目录中的栅格文件
        for root, dirs, files in os.walk(DATA_DIR):
            for file in files:
                if file.lower().endswith(('.tif', '.tiff')):
                    # 获取相对于DATA_DIR的路径
                    rel_path = os.path.relpath(os.path.join(root, file), DATA_DIR)
                    
                    # 获取文件信息
                    full_path = os.path.join(root, file)
                    try:
                        with rasterio.open(full_path) as src:
                            file_info = {
                                'path': rel_path.replace('\\', '/'),  # 统一使用正斜杠
                                'name': os.path.splitext(file)[0],
                                'size': f"{src.width} x {src.height}",
                                'crs': str(src.crs) if src.crs else 'Unknown',
                                'bands': src.count,
                                'dtype': str(src.dtypes[0])
                            }
                            raster_files.append(file_info)
                    except Exception as e:
                        print(f"读取栅格文件信息失败 {rel_path}: {str(e)}")
                        continue
        
        # 按文件名排序
        raster_files.sort(key=lambda x: x['name'])
        
        return jsonify({
            'raster_files': raster_files,
            'total_count': len(raster_files)
        })
        
    except Exception as e:
        print(f"获取栅格文件列表错误: {str(e)}")
        return jsonify({'error': f'获取栅格文件列表失败: {str(e)}'}), 500