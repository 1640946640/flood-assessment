from flask import Blueprint, request, jsonify, send_file
from flask_cors import cross_origin
import os
import rasterio
from rasterio.warp import reproject, Resampling
import tempfile
import zipfile
import shutil
from datetime import datetime

alignment_bp = Blueprint('alignment', __name__, url_prefix='/api/alignment')

# 数据文件夹路径
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

class RasterAligner:
    """栅格对齐工具类"""
    
    def __init__(self):
        self.supported_methods = {
            'nearest': Resampling.nearest,
            'bilinear': Resampling.bilinear,
            'cubic': Resampling.cubic,
            'cubic_spline': Resampling.cubic_spline,
            'lanczos': Resampling.lanczos,
            'average': Resampling.average,
            'mode': Resampling.mode
        }
    
    def get_raster_info(self, raster_path):
        """获取栅格信息"""
        try:
            with rasterio.open(raster_path) as src:
                return {
                    'width': src.width,
                    'height': src.height,
                    'crs': str(src.crs),
                    'transform': list(src.transform),
                    'bounds': list(src.bounds),
                    'dtype': str(src.dtypes[0]),
                    'count': src.count
                }
        except Exception as e:
            raise Exception(f"读取栅格信息失败 {raster_path}: {str(e)}")
    
    def align_raster_to_template(self, input_path, template_path, output_path, resampling_method='bilinear'):
        """将栅格对齐到模板栅格"""
        try:
            # 获取重采样方法
            resampling = self.supported_methods.get(resampling_method, Resampling.bilinear)
            
            # 读取模板栅格信息
            with rasterio.open(template_path) as template_ds:
                template_meta = template_ds.meta.copy()
                template_transform = template_ds.transform
                template_crs = template_ds.crs
                template_width = template_ds.width
                template_height = template_ds.height
            
            # 对齐栅格
            with rasterio.open(input_path) as src:
                dst_meta = template_meta.copy()
                src_dtype = src.dtypes[0]
                src_nodata = src.nodata
                
                # 处理数据类型和nodata值的兼容性
                if src_dtype == 'uint8' and src_nodata is not None and (src_nodata < 0 or src_nodata > 255):
                    # 对于uint8类型，如果nodata值超出范围，使用255作为nodata值
                    dst_nodata = 255
                elif src_dtype == 'uint16' and src_nodata is not None and (src_nodata < 0 or src_nodata > 65535):
                    # 对于uint16类型，如果nodata值超出范围，使用65535作为nodata值
                    dst_nodata = 65535
                else:
                    dst_nodata = src_nodata
                
                dst_meta.update({
                    'dtype': src_dtype,
                    'count': src.count,
                    'nodata': dst_nodata
                })
                
                with rasterio.open(output_path, 'w', **dst_meta) as dst:
                    for i in range(1, src.count + 1):
                        reproject(
                            source=rasterio.band(src, i),
                            destination=rasterio.band(dst, i),
                            src_transform=src.transform,
                            src_crs=src.crs,
                            dst_transform=template_transform,
                            dst_crs=template_crs,
                            resampling=resampling,
                            dst_nodata=dst_nodata
                        )
            
            return True
        except Exception as e:
            raise Exception(f"栅格对齐失败: {str(e)}")
    
    def batch_align_rasters(self, input_dir, template_path, output_dir, resampling_method='bilinear'):
        """批量对齐栅格文件"""
        results = []
        errors = []
        
        # 确保输出目录存在
        os.makedirs(output_dir, exist_ok=True)
        
        # 遍历输入目录中的所有tif文件
        for filename in os.listdir(input_dir):
            if not filename.lower().endswith('.tif'):
                continue
                
            input_file = os.path.join(input_dir, filename)
            output_file = os.path.join(output_dir, filename)
            
            try:
                self.align_raster_to_template(input_file, template_path, output_file, resampling_method)
                results.append({
                    'filename': filename,
                    'status': 'success',
                    'output_path': output_file
                })
            except Exception as e:
                errors.append({
                    'filename': filename,
                    'status': 'error',
                    'error': str(e)
                })
        
        return results, errors

@alignment_bp.route('/get-directories', methods=['GET'])
@cross_origin()
def get_directories():
    """获取数据目录下的所有子目录"""
    try:
        directories = []
        for item in os.listdir(DATA_DIR):
            item_path = os.path.join(DATA_DIR, item)
            if os.path.isdir(item_path):
                # 检查目录中是否有tif文件
                tif_count = len([f for f in os.listdir(item_path) if f.lower().endswith('.tif')])
                directories.append({
                    'name': item,
                    'path': item_path,
                    'tif_count': tif_count
                })
        
        return jsonify({
            'success': True,
            'directories': directories
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@alignment_bp.route('/get-raster-files', methods=['POST'])
@cross_origin()
def get_raster_files():
    """获取指定目录下的栅格文件列表"""
    try:
        data = request.get_json()
        directory_path = data.get('directory_path')
        
        if not directory_path or not os.path.exists(directory_path):
            return jsonify({
                'success': False,
                'error': '目录路径无效'
            }), 400
        
        raster_files = []
        aligner = RasterAligner()
        
        for filename in os.listdir(directory_path):
            if filename.lower().endswith('.tif'):
                file_path = os.path.join(directory_path, filename)
                try:
                    info = aligner.get_raster_info(file_path)
                    raster_files.append({
                        'filename': filename,
                        'path': file_path,
                        'info': info
                    })
                except Exception as e:
                    raster_files.append({
                        'filename': filename,
                        'path': file_path,
                        'error': str(e)
                    })
        
        return jsonify({
            'success': True,
            'raster_files': raster_files
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@alignment_bp.route('/align-rasters', methods=['POST'])
@cross_origin()
def align_rasters():
    """执行栅格对齐"""
    try:
        data = request.get_json()
        input_directory = data.get('input_directory')
        template_file = data.get('template_file')
        output_directory = data.get('output_directory')
        resampling_method = data.get('resampling_method', 'bilinear')
        
        # 验证参数
        if not all([input_directory, template_file, output_directory]):
            return jsonify({
                'success': False,
                'error': '缺少必要参数'
            }), 400
        
        if not os.path.exists(input_directory):
            return jsonify({
                'success': False,
                'error': '输入目录不存在'
            }), 400
        
        if not os.path.exists(template_file):
            return jsonify({
                'success': False,
                'error': '模板文件不存在'
            }), 400
        
        # 创建输出目录
        os.makedirs(output_directory, exist_ok=True)
        
        # 执行对齐
        aligner = RasterAligner()
        results, errors = aligner.batch_align_rasters(
            input_directory, template_file, output_directory, resampling_method
        )
        
        return jsonify({
            'success': True,
            'results': results,
            'errors': errors,
            'total_files': len(results) + len(errors),
            'success_count': len(results),
            'error_count': len(errors)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@alignment_bp.route('/download-aligned', methods=['POST'])
@cross_origin()
def download_aligned():
    """下载对齐后的文件"""
    try:
        data = request.get_json()
        output_directory = data.get('output_directory')
        
        if not output_directory or not os.path.exists(output_directory):
            return jsonify({
                'success': False,
                'error': '输出目录不存在'
            }), 400
        
        # 创建临时zip文件
        temp_dir = tempfile.mkdtemp()
        zip_filename = f"aligned_rasters_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        zip_path = os.path.join(temp_dir, zip_filename)
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for filename in os.listdir(output_directory):
                if filename.lower().endswith('.tif'):
                    file_path = os.path.join(output_directory, filename)
                    zipf.write(file_path, filename)
        
        return send_file(
            zip_path,
            as_attachment=True,
            download_name=zip_filename,
            mimetype='application/zip'
        )
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500