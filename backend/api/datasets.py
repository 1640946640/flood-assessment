from flask import Blueprint, jsonify, request, send_file
import os
import json
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio.features import shapes
import numpy as np
from shapely.geometry import shape, mapping
import geojson
from pathlib import Path
import math
from datetime import datetime

# 创建蓝图
datasets_bp = Blueprint("datasets", __name__)

# 数据文件夹路径
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

# 定义允许访问的图片路径列表
ALLOWED_IMAGE_PATHS = [
    "flood_results",
    "correlation_analysis_results",
    "total"             # 特殊路径，用于获取所有图片
]


def check_shapefile_files(shp_path):
    """检查shapefile必需的文件是否都存在"""
    base_path = os.path.splitext(shp_path)[0]
    required_extensions = [".shp", ".shx", ".dbf"]
    missing_files = []

    for ext in required_extensions:
        if not os.path.exists(base_path + ext):
            missing_files.append(ext)

    return len(missing_files) == 0, missing_files


def is_geojson(json_path):
    """检查JSON文件是否是GeoJSON格式"""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # 检查GeoJSON的必要字段
            if 'type' in data and data['type'] in ['FeatureCollection', 'Feature', 'Point', 'LineString', 'Polygon', 'MultiPoint', 'MultiLineString', 'MultiPolygon', 'GeometryCollection']:
                # 进一步检查FeatureCollection是否包含features数组
                if data['type'] == 'FeatureCollection' and 'features' in data and isinstance(data['features'], list):
                    return True
                # 检查单个Feature是否包含geometry
                elif data['type'] == 'Feature' and 'geometry' in data:
                    return True
                # 检查是否是几何对象
                elif data['type'] in ['Point', 'LineString', 'Polygon', 'MultiPoint', 'MultiLineString', 'MultiPolygon'] and 'coordinates' in data:
                    return True
                # 检查是否是几何集合
                elif data['type'] == 'GeometryCollection' and 'geometries' in data:
                    return True
            return False
    except Exception as e:
        print(f"Error checking if file is GeoJSON: {str(e)}")
        return False


def get_file_info(file_path):
    """获取文件信息"""
    try:
        file_name = os.path.basename(file_path)
        name_without_ext = os.path.splitext(file_name)[0]
        extension = os.path.splitext(file_path)[1].lower()

        file_info = {
            "id": file_name,
            "name": name_without_ext,
            "path": file_path,
            "type": None,
            "properties": {},
        }

        if extension == ".shp" or extension == ".geojson" or (extension == ".json" and is_geojson(file_path)):
            try:
                # 使用绝对路径
                abs_path = os.path.abspath(file_path)
                print(f"Reading vector file: {abs_path}")

                # 对于Shapefile检查必需文件是否完整
                if extension == ".shp":
                    files_complete, missing_files = check_shapefile_files(abs_path)
                    if not files_complete:
                        print(
                            f"Warning: Missing required files for shapefile {abs_path}: {', '.join(missing_files)}"
                        )
                        return None

                    # 设置GDAL配置
                    import fiona
                    fiona.Env(SHAPE_RESTORE_SHX="YES")

                # 尝试读取矢量数据
                gdf = None
                
                # GeoJSON文件通常不需要多种编码尝试，直接读取即可
                if extension == ".geojson" or extension == ".json":
                    try:
                        gdf = gpd.read_file(abs_path)
                        print(f"Successfully read GeoJSON file: {abs_path}")
                    except Exception as e:
                        print(f"Error reading GeoJSON {abs_path}: {str(e)}")
                        import traceback
                        traceback.print_exc()
                        return None
                else:
                    # Shapefile需要尝试多种编码
                    encodings_to_try = ["utf-8", "gbk", "gb2312", "latin1"]
                    for encoding in encodings_to_try:
                        try:
                            gdf = gpd.read_file(abs_path, encoding=encoding)
                            print(f"Successfully read shapefile with encoding: {encoding}")
                            break  # 成功读取，跳出循环
                        except UnicodeDecodeError:
                            print(f"Failed to read shapefile with encoding: {encoding}")
                        except Exception as e:
                            # 其他可能的 fiona 或 geopandas 错误
                            print(
                                f"Error reading shapefile {abs_path} with encoding {encoding}: {str(e)}"
                            )
                            # 不再尝试其他编码，因为可能不是编码问题
                            break

                if gdf is None:
                    print(
                        f"Failed to read vector file {abs_path}"
                    )
                    return None

                # 获取几何类型，处理可能的None值
                geom_type = str(gdf.geom_type.iloc[0]) if not gdf.empty else "Unknown"

                # 获取坐标系信息
                crs_info = str(gdf.crs)
                
                # 处理bounds，避免nan值
                bounds = None
                if not gdf.empty:
                    bounds_array = gdf.total_bounds
                    if not np.any(np.isnan(bounds_array)) and not np.any(np.isinf(bounds_array)):
                        bounds = bounds_array.tolist()

                file_info.update(
                    {
                        "type": "vector",
                        "properties": {
                            "feature_count": len(gdf),
                            "crs": crs_info,
                            "geometry_type": geom_type,
                            "fields": [col for col in gdf.columns if col != "geometry"],
                            "bounds": bounds,
                            "format": extension[1:],  # 记录文件格式
                        },
                    }
                )

                # 如果不是WGS84坐标系，记录原始坐标系信息
                if gdf.crs and gdf.crs.to_epsg() != 4326:
                    print(f"检测到非WGS84坐标系: {crs_info}")
                    file_info["properties"]["original_crs"] = crs_info
                print(f"Successfully read vector file: {abs_path}")

            except Exception as e:
                print(f"Error reading vector file {abs_path}: {str(e)}")
                import traceback

                traceback.print_exc()
                return None

        elif extension == ".tif":
            try:
                # 使用绝对路径
                abs_path = os.path.abspath(file_path)
                print(f"Reading raster: {abs_path}")

                with rasterio.open(abs_path) as dataset:
                    if dataset is None:
                        print(f"Warning: Failed to open raster: {abs_path}")
                        return None

                    # 获取坐标系信息
                    crs_info = str(dataset.crs)

                    # 读取第一个波段数据并处理nodata值
                    band_data = dataset.read(1)
                    
                    # 处理无效值和NaN值
                    if dataset.nodata is not None:
                        valid_mask = (band_data != dataset.nodata) & ~np.isnan(band_data)
                    else:
                        valid_mask = ~np.isnan(band_data)
                        
                    valid_data = band_data[valid_mask]
                    
                    # 计算有效数据的最大最小值
                    min_val = float(np.nanmin(valid_data)) if valid_data.size > 0 else 0
                    max_val = float(np.nanmax(valid_data)) if valid_data.size > 0 else 1
                    
                    # 处理nodata值，避免nan导致JSON序列化失败
                    nodata_val = dataset.nodata
                    if nodata_val is not None and (np.isnan(nodata_val) or np.isinf(nodata_val)):
                        nodata_val = None
                    
                    # 处理bounds，避免nan值
                    bounds = list(dataset.bounds)
                    if np.any(np.isnan(bounds)) or np.any(np.isinf(bounds)):
                        bounds = None

                    file_info.update(
                        {
                            "type": "raster",
                            "properties": {
                                "width": dataset.width,
                                "height": dataset.height,
                                "bands": dataset.count,
                                "crs": crs_info,
                                "bounds": bounds,
                                "resolution": dataset.res,
                                "min": min_val,
                                "max": max_val,
                                "nodata": nodata_val
                            },
                        }
                    )

                    # 如果不是WGS84坐标系，记录原始坐标系信息
                    if dataset.crs and dataset.crs.to_epsg() != 4326:
                        print(f"检测到非WGS84栅格坐标系: {crs_info}")
                        file_info["properties"]["original_crs"] = crs_info
                print(f"Successfully read raster: {abs_path}")

            except Exception as e:
                print(f"Error reading raster {abs_path}: {str(e)}")
                import traceback

                traceback.print_exc()
                return None

        return file_info

    except Exception as e:
        print(f"General error processing file {file_path}: {str(e)}")
        import traceback

        traceback.print_exc()
        return None


def get_datasets():
    """获取所有数据集信息"""
    datasets = {"vector": [], "raster": []}

    # 遍历数据文件夹
    for file_name in os.listdir(DATA_DIR):
        file_path = os.path.join(DATA_DIR, file_name)
        extension = os.path.splitext(file_name)[1].lower()

        # 只处理.shp、.tif、.csv、.xls、.xlsx文件
        if extension not in [".shp", ".tif", ".csv", ".xls", ".xlsx"]:
            continue

        file_info = get_file_info(file_path)
        print("file_info", file_path)
        if file_info:
            datasets[file_info["type"]].append(file_info)

    return jsonify({"status": "success", "data": datasets})


def get_dataset_preview(dataset_id):
    """获取数据集预览信息"""
    file_path = os.path.join(DATA_DIR, dataset_id)
    if not os.path.exists(file_path):
        return jsonify({"status": "error", "message": "Dataset not found"}), 404

    extension = os.path.splitext(dataset_id)[1].lower()
    preview_data = None

    try:
        if extension == ".shp":
            # 读取矢量数据前5条记录
            gdf = gpd.read_file(file_path)
            preview_data = {
                "type": "vector",
                "features": json.loads(gdf.head().to_json()),
            }
        elif extension == ".tif":
            # 读取栅格数据统计信息
            with rasterio.open(file_path) as dataset:
                stats = [
                    {
                        "min": float(dataset.statistics(i + 1).min),
                        "max": float(dataset.statistics(i + 1).max),
                        "mean": float(dataset.statistics(i + 1).mean),
                        "std": float(dataset.statistics(i + 1).std),
                    }
                    for i in range(dataset.count)
                ]
                preview_data = {"type": "raster", "statistics": stats}
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

    return jsonify({"status": "success", "data": preview_data})


# 获取所有数据集列表
@datasets_bp.route("", methods=["GET"])
def get_datasets():
    """获取所有数据集列表，支持文件夹层级结构，不读取文件详细信息"""
    try:
        datasets = []

        # 递归遍历数据文件夹
        def scan_directory(directory, relative_path=""):
            result = []

            # 遍历目录中的所有文件和文件夹
            for item_name in os.listdir(directory):
                item_path = os.path.join(directory, item_name)
                item_relative_path = (
                    os.path.join(relative_path, item_name)
                    if relative_path
                    else item_name
                )

                if os.path.isdir(item_path):
                    # 处理文件夹
                    folder_children = scan_directory(item_path, item_relative_path)
                    if folder_children:  # 只添加非空文件夹
                        result.append(
                            {
                                "id": item_relative_path,
                                "name": item_name,
                                "type": "folder",
                                "children": folder_children,
                                "isFolder": True,
                            }
                        )
                else:
                    # 处理文件
                    extension = os.path.splitext(item_name)[1].lower()
                    name_without_ext = os.path.splitext(item_name)[0]

                    # 只处理.shp、.geojson、.json、.tif文件和表格文件
                    if extension not in [".shp", ".geojson", ".json", ".tif", ".csv", ".xls", ".xlsx"]:
                        # 如果是.json，检查是否是GeoJSON格式
                        if extension == ".json":
                            if not is_geojson(os.path.join(directory, item_name)):
                                continue
                        else:
                            continue

                    # 根据文件扩展名判断类型，不读取文件内容
                    if extension == ".shp" or extension == ".geojson" or (extension == ".json" and is_geojson(os.path.join(directory, item_name))):
                        file_type = "vector"
                    elif extension == ".tif":
                        file_type = "raster"
                    else:  # csv 和 xls/xlsx 视为表格型向量数据
                        file_type = "vector"

                    # 构造前端需要的数据格式，只包含基本信息
                    dataset = {
                        "id": item_relative_path,
                        "name": name_without_ext,
                        "type": file_type,
                        "format": extension[1:],  # 移除点号
                        "url": f"/data/{item_relative_path}",
                        "description": "",  # 可以从元数据中读取或设置默认值
                        "properties": {},  # 空属性，详细信息将在需要时通过其他API获取
                        "isFolder": False,
                        "parentPath": relative_path,
                    }

                    # 为表格文件添加额外标识
                    if extension in [".csv", ".xls", ".xlsx"]:
                        dataset["subtype"] = "table"
                        dataset["properties"]["is_table"] = True

                    result.append(dataset)

            return result

        # 开始扫描根目录
        datasets = scan_directory(DATA_DIR)

        return jsonify(datasets)

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# 获取数据集详情
@datasets_bp.route("/<path:dataset_id>", methods=["GET"])
def get_dataset(dataset_id):
    # 查找实际文件
    file_path = os.path.join(DATA_DIR, dataset_id)
    if not os.path.exists(file_path):
        return jsonify({"status": "error", "message": "Dataset not found"}), 404

    # 获取文件信息
    file_info = get_file_info(file_path)
    if not file_info:
        return jsonify({"status": "error", "message": "Cannot read dataset"}), 500

    # 构造数据集详情
    # 栅格在dataset中，metadata中添加最大最小值

    dataset = {
        "id": dataset_id,
        "name": file_info["name"],
        "type": file_info["type"],
        "format": os.path.splitext(dataset_id)[1].lower()[1:],
        "url": f"/api/datasets/{dataset_id}",
        "properties": file_info["properties"],
        "metadata": {
            "crs": file_info["properties"].get("crs", "EPSG:4326"),
            "bounds": file_info["properties"].get("bounds", None),
            "created_at": datetime.now().isoformat(),
            "min": file_info["properties"].get("min", None),
            "max": file_info["properties"].get("max", None),
        },
    }

    return jsonify(dataset)


# 获取数据集字段信息
@datasets_bp.route("/<path:dataset_id>/fields", methods=["GET"])
def get_dataset_fields(dataset_id):
    """获取数据集的字段信息
    
    参数:
        dataset_id: 数据集ID（文件路径）
        
    返回:
        JSON格式的字段列表
    """
    file_path = os.path.join(DATA_DIR, dataset_id)
    
    if not os.path.exists(file_path):
        return jsonify({"status": "error", "message": "数据集不存在"}), 404
    
    extension = os.path.splitext(file_path)[1].lower()
    
    try:
        if extension == ".shp" or extension == ".geojson" or (extension == ".json" and is_geojson(file_path)):
            # 矢量数据
            gdf = None
            
            # GeoJSON格式可以直接读取
            if extension == ".geojson" or extension == ".json":
                try:
                    gdf = gpd.read_file(file_path)
                    print(f"成功读取GeoJSON文件: {file_path}")
                except Exception as e:
                    print(f"读取GeoJSON文件出错: {str(e)}")
                    return jsonify({"status": "error", "message": f"无法读取GeoJSON数据: {str(e)}"}), 500
            else:
                # Shapefile需要尝试多种编码
                encodings_to_try = ["utf-8", "gbk", "gb2312", "latin1"]
                for encoding in encodings_to_try:
                    try:
                        gdf = gpd.read_file(file_path, encoding=encoding)
                        print(f"成功使用编码 {encoding} 读取Shapefile")
                        break
                    except UnicodeDecodeError:
                        print(f"使用编码 {encoding} 读取失败，尝试下一个")
                        continue
                    except Exception as e:
                        print(f"读取Shapefile出错: {str(e)}")
                        break
            
            if gdf is None:
                return jsonify({"status": "error", "message": "无法读取矢量数据"}), 500
            
            # 提取字段信息
            fields = []
            for column in gdf.columns:
                if column == "geometry":
                    continue
                    
                # 使用函数获取友好的字段类型名称
                field_type = get_friendly_field_type(gdf[column])
                
                fields.append({
                    "name": column,
                    "type": field_type
                })
            
            return jsonify(fields)
            
        elif extension == ".tif":
            # 栅格数据通常只有一个"值"字段
            fields = [
                {"name": "value", "type": "float"}
            ]
            
            # 尝试读取栅格以获取更多信息
            try:
                with rasterio.open(file_path) as src:
                    # 如果有多个波段，添加波段字段
                    if src.count > 1:
                        fields.append({"name": "band", "type": "integer"})
            except Exception as e:
                print(f"读取栅格文件出错: {str(e)}")
                # 即使读取出错也返回基本字段
            
            return jsonify(fields)
        
        elif extension in [".csv", ".xls", ".xlsx"]:
            # 表格数据
            df = None
            try:
                if extension == ".csv":
                    df = pd.read_csv(file_path)
                else:
                    df = pd.read_excel(file_path)
                
                fields = []
                for column in df.columns:
                    # 使用函数获取友好的字段类型名称
                    field_type = get_friendly_field_type(df[column])
                    
                    fields.append({
                        "name": column,
                        "type": field_type
                    })
                
                return jsonify(fields)
            except Exception as e:
                print(f"读取表格文件出错: {str(e)}")
                return jsonify({"status": "error", "message": f"无法读取表格数据: {str(e)}"}), 500
        else:
            return jsonify({"status": "error", "message": "不支持的文件格式"}), 400
            
    except Exception as e:
        print(f"获取字段信息出错: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": f"获取字段信息出错: {str(e)}"}), 500


# 获取数据集统计信息
@datasets_bp.route("/<path:dataset_id>/statistics", methods=["GET"])
def get_dataset_statistics(dataset_id):
    """获取数据集的统计信息和直方图数据"""
    file_path = os.path.join(DATA_DIR, dataset_id)
    if not os.path.exists(file_path):
        return jsonify({"status": "error", "message": "Dataset not found"}), 404

    extension = os.path.splitext(dataset_id)[1].lower()
    statistics = {}

    try:
        if extension == ".shp" or extension == ".geojson" or (extension == ".json" and is_geojson(file_path)):
            # 矢量数据统计
            gdf = None
            
            # GeoJSON格式可以直接读取
            if extension == ".geojson" or extension == ".json":
                try:
                    gdf = gpd.read_file(file_path)
                    
                    # 处理bytes类型数据，将其转换为字符串，以便JSON序列化
                    for col in gdf.columns:
                        if col != 'geometry':
                            # 检查是否有bytes类型的数据
                            if gdf[col].dtype == 'object':
                                # 转换bytes为字符串，尝试多种编码
                                def decode_bytes_value(x):
                                    if isinstance(x, bytes):
                                        # 方法1：直接尝试多种编码来解码bytes
                                        for encoding in ['utf-8', 'gbk', 'gb2312', 'latin1']:
                                            try:
                                                decoded = x.decode(encoding)
                                                # 检查解码结果是否仍然是十六进制字符串
                                                if all(c in '0123456789abcdefABCDEF' for c in decoded):
                                                    # 可能是十六进制表示，尝试方法2
                                                    continue
                                                return decoded
                                            except UnicodeDecodeError:
                                                continue
                                        
                                        # 方法2：假设bytes解码后是十六进制字符串，需要进一步解码
                                        try:
                                            # 先用latin1解码（保证不会出错）得到十六进制字符串
                                            hex_str = x.decode('latin1', errors='replace')
                                            # 过滤掉非十六进制字符
                                            hex_str = ''.join(c for c in hex_str if c in '0123456789abcdefABCDEF')
                                            
                                            # 将十六进制字符串转换为字节序列
                                            byte_array = bytearray()
                                            for i in range(0, len(hex_str), 2):
                                                if i + 1 < len(hex_str):
                                                    byte_array.append(int(hex_str[i:i+2], 16))
                                            
                                            # 尝试用GBK/GB2312解码
                                            for encoding in ['gbk', 'gb2312']:
                                                try:
                                                    return byte_array.decode(encoding)
                                                except UnicodeDecodeError:
                                                    continue
                                        except Exception:
                                            pass
                                        
                                        # 如果所有方法都失败，使用utf-8并替换错误字符
                                        return x.decode('utf-8', errors='replace')
                                    return x
                                gdf[col] = gdf[col].apply(decode_bytes_value)
                except Exception as e:
                    print(f"Error reading GeoJSON {file_path}: {str(e)}")
                    return jsonify({"status": "error", "message": f"Failed to read GeoJSON: {str(e)}"}), 500
            else:
                # Shapefile需要尝试多种编码
                encodings_to_try = ["utf-8", "gbk", "gb2312", "latin1"]
                for encoding in encodings_to_try:
                    try:
                        gdf = gpd.read_file(file_path, encoding=encoding)
                        
                        # 处理bytes类型数据，将其转换为字符串，以便JSON序列化
                        for col in gdf.columns:
                            if col != 'geometry':
                                # 检查是否有bytes类型的数据
                                if gdf[col].dtype == 'object':
                                    # 转换bytes为字符串，尝试多种编码
                                    def decode_bytes_value(x):
                                        if isinstance(x, bytes):
                                            # 方法1：直接尝试多种编码来解码bytes
                                            for encoding in ['utf-8', 'gbk', 'gb2312', 'latin1']:
                                                try:
                                                    decoded = x.decode(encoding)
                                                    # 检查解码结果是否仍然是十六进制字符串
                                                    if all(c in '0123456789abcdefABCDEF' for c in decoded):
                                                        # 可能是十六进制表示，尝试方法2
                                                        continue
                                                    return decoded
                                                except UnicodeDecodeError:
                                                    continue
                                            
                                            # 方法2：假设bytes解码后是十六进制字符串，需要进一步解码
                                            try:
                                                # 先用latin1解码（保证不会出错）得到十六进制字符串
                                                hex_str = x.decode('latin1', errors='replace')
                                                # 过滤掉非十六进制字符
                                                hex_str = ''.join(c for c in hex_str if c in '0123456789abcdefABCDEF')
                                                
                                                # 将十六进制字符串转换为字节序列
                                                byte_array = bytearray()
                                                for i in range(0, len(hex_str), 2):
                                                    if i + 1 < len(hex_str):
                                                        byte_array.append(int(hex_str[i:i+2], 16))
                                                
                                                # 尝试用GBK/GB2312解码
                                                for encoding in ['gbk', 'gb2312']:
                                                    try:
                                                        return byte_array.decode(encoding)
                                                    except UnicodeDecodeError:
                                                        continue
                                            except Exception:
                                                pass
                                            
                                            # 如果所有方法都失败，使用utf-8并替换错误字符
                                            return x.decode('utf-8', errors='replace')
                                        return x
                                    gdf[col] = gdf[col].apply(decode_bytes_value)
                        break  # 成功读取，跳出循环
                    except UnicodeDecodeError:
                        continue
                    except Exception as e:
                        break

            if gdf is None:
                return (
                    jsonify(
                        {
                            "status": "error",
                            "message": "Failed to read vector data",
                        }
                    ),
                    500,
                )

            # 处理bytes类型数据，将其转换为字符串，以便JSON序列化
            for col in gdf.columns:
                if col != 'geometry':
                    # 检查是否有bytes类型的数据
                    if gdf[col].dtype == 'object':
                        # 转换bytes为字符串
                        gdf[col] = gdf[col].apply(lambda x: x.decode('utf-8', errors='ignore') if isinstance(x, bytes) else x)

        # 计算各个字段的统计信息
            stats = []
            for column in gdf.columns:
                if column == "geometry":
                    continue

                column_data = gdf[column]
                # 使用函数获取友好的字段类型名称
                column_type = get_friendly_field_type(column_data)

                # 根据数据类型计算不同的统计量
                if pd.api.types.is_numeric_dtype(column_data):
                    # 数值型字段
                    field_stats = {
                        "field": column,
                        "type": column_type,
                        "min": (
                            float(column_data.min())
                            if not pd.isna(column_data.min())
                            else 0
                        ),
                        "max": (
                            float(column_data.max())
                            if not pd.isna(column_data.max())
                            else 0
                        ),
                        "avg": (
                            float(column_data.mean())
                            if not pd.isna(column_data.mean())
                            else 0
                        ),
                        "std": (
                            float(column_data.std())
                            if not pd.isna(column_data.std())
                            else 0
                        ),
                        "count": int(column_data.count()),
                        # 添加分布数据用于直方图
                        "histogram": [],
                    }

                    # 计算直方图数据
                    try:
                        hist, bin_edges = np.histogram(column_data.dropna(), bins=10)
                        field_stats["histogram"] = {
                            "counts": hist.tolist(),
                            "bins": bin_edges.tolist(),
                        }
                    except Exception as e:
                        print(f"计算字段 {column} 直方图错误: {str(e)}")

                else:
                    # 非数值型字段(字符串等)
                    value_counts = column_data.value_counts()
                    field_stats = {
                        "field": column,
                        "type": column_type,
                        "count": int(column_data.count()),
                        "unique": int(column_data.nunique()),
                        "categories": [],
                    }

                    # 添加分类统计
                    try:
                        categories = []
                        # 限制最多返回20个类别
                        for cat, count in value_counts.head(20).items():
                            categories.append({"name": str(cat), "count": int(count)})
                        field_stats["categories"] = categories
                    except Exception as e:
                        print(f"计算字段 {column} 类别统计错误: {str(e)}")

                stats.append(field_stats)

            statistics = {"type": "vector", "feature_count": len(gdf), "stats": stats}

        elif extension == ".tif":
            # 栅格数据统计
            with rasterio.open(file_path) as src:
                band_stats = []

                for i in range(src.count):
                    band_idx = i + 1
                    band_data = src.read(band_idx)

                    # 处理无效值和NaN值
                    if src.nodata is not None:
                        valid_mask = (band_data != src.nodata) & ~np.isnan(band_data)
                    else:
                        valid_mask = ~np.isnan(band_data)
                        
                    valid_data = band_data[valid_mask]

                    if valid_data.size == 0:
                        continue

                    # 计算基本统计量
                    min_val = float(np.nanmin(valid_data))
                    max_val = float(np.nanmax(valid_data))
                    mean_val = float(np.nanmean(valid_data))
                    std_val = float(np.nanstd(valid_data))

                    # 计算直方图
                    try:
                        # 如果数据范围过大，限制直方图bin数量
                        if max_val - min_val > 100:
                            num_bins = 100
                        else:
                            num_bins = min(int(max_val - min_val + 1), 100)

                        num_bins = max(10, num_bins)  # 至少10个bins

                        hist, bin_edges = np.histogram(
                            valid_data, bins=num_bins, range=(min_val, max_val)
                        )

                        band_stat = {
                            "band": band_idx,
                            "min": min_val,
                            "max": max_val,
                            "mean": mean_val,
                            "std": std_val,
                            "histogram": {
                                "counts": hist.tolist(),
                                "bins": bin_edges.tolist(),
                            },
                        }
                    except Exception as e:
                        print(f"计算波段 {band_idx} 直方图错误: {str(e)}")
                        band_stat = {
                            "band": band_idx,
                            "min": min_val,
                            "max": max_val,
                            "mean": mean_val,
                            "std": std_val,
                        }

                    band_stats.append(band_stat)

                statistics = {
                    "type": "raster",
                    "width": src.width,
                    "height": src.height,
                    "bands": src.count,
                    "stats": band_stats,
                }

        elif extension in [".csv", ".xls", ".xlsx"]:
            # 表格数据统计（无几何）
            try:
                if extension == ".csv":
                    df = pd.read_csv(file_path)
                else:
                    df = pd.read_excel(file_path)
                    
                # 处理bytes类型数据，将其转换为字符串，以便JSON序列化
                for col in df.columns:
                    # 检查是否有bytes类型的数据
                    if df[col].dtype == 'object':
                        # 转换bytes为字符串，尝试多种编码
                        def decode_bytes_value(x):
                            if isinstance(x, bytes):
                                # 方法1：直接尝试多种编码来解码bytes
                                for encoding in ['utf-8', 'gbk', 'gb2312', 'latin1']:
                                    try:
                                        decoded = x.decode(encoding)
                                        # 检查解码结果是否仍然是十六进制字符串
                                        if all(c in '0123456789abcdefABCDEF' for c in decoded):
                                            # 可能是十六进制表示，尝试方法2
                                            continue
                                        return decoded
                                    except UnicodeDecodeError:
                                        continue
                                
                                # 方法2：假设bytes解码后是十六进制字符串，需要进一步解码
                                try:
                                    # 先用latin1解码（保证不会出错）得到十六进制字符串
                                    hex_str = x.decode('latin1', errors='replace')
                                    # 过滤掉非十六进制字符
                                    hex_str = ''.join(c for c in hex_str if c in '0123456789abcdefABCDEF')
                                    
                                    # 将十六进制字符串转换为字节序列
                                    byte_array = bytearray()
                                    for i in range(0, len(hex_str), 2):
                                        if i + 1 < len(hex_str):
                                            byte_array.append(int(hex_str[i:i+2], 16))
                                    
                                    # 尝试用GBK/GB2312解码
                                    for encoding in ['gbk', 'gb2312']:
                                        try:
                                            return byte_array.decode(encoding)
                                        except UnicodeDecodeError:
                                            continue
                                except Exception:
                                    pass
                                
                                # 如果所有方法都失败，使用utf-8并替换错误字符
                                return x.decode('utf-8', errors='replace')
                            return x
                        df[col] = df[col].apply(decode_bytes_value)
            except Exception as e:
                return (
                    jsonify(
                        {
                            "status": "error",
                            "message": f"Failed to read table data: {str(e)}",
                        }
                    ),
                    500,
                )
            stats = []
            for column in df.columns:
                column_data = df[column]
                # 使用函数获取友好的字段类型名称
                column_type = get_friendly_field_type(column_data)
                if pd.api.types.is_numeric_dtype(column_data):
                    field_stats = {
                        "field": column,
                        "type": column_type,
                        "min": (
                            float(column_data.min())
                            if not pd.isna(column_data.min())
                            else 0
                        ),
                        "max": (
                            float(column_data.max())
                            if not pd.isna(column_data.max())
                            else 0
                        ),
                        "avg": (
                            float(column_data.mean())
                            if not pd.isna(column_data.mean())
                            else 0
                        ),
                        "std": (
                            float(column_data.std())
                            if not pd.isna(column_data.std())
                            else 0
                        ),
                        "count": int(column_data.count()),
                        "histogram": {},
                    }
                    try:
                        hist, bin_edges = np.histogram(column_data.dropna(), bins=10)
                        field_stats["histogram"] = {
                            "counts": hist.tolist(),
                            "bins": bin_edges.tolist(),
                        }
                    except Exception:
                        pass
                else:
                    value_counts = column_data.value_counts()
                    field_stats = {
                        "field": column,
                        "type": column_type,
                        "count": int(column_data.count()),
                        "unique": int(column_data.nunique()),
                        "categories": [],
                    }
                    try:
                        categories = []
                        for cat, count in value_counts.head(20).items():
                            categories.append({"name": str(cat), "count": int(count)})
                        field_stats["categories"] = categories
                    except Exception:
                        pass
                stats.append(field_stats)
            statistics = {"type": "vector", "feature_count": len(df), "stats": stats}

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

    return jsonify(statistics)


# 获取字段的友好类型名称
def get_friendly_field_type(column_data):
    """将pandas数据类型转换为更友好的类型名称"""
    if pd.api.types.is_integer_dtype(column_data):
        return "integer"
    elif pd.api.types.is_float_dtype(column_data):
        return "float"
    elif pd.api.types.is_bool_dtype(column_data):
        return "boolean"
    elif pd.api.types.is_datetime64_any_dtype(column_data):
        return "date"
    elif pd.api.types.is_object_dtype(column_data):
        return "string"
    else:
        return str(column_data.dtype)

# 获取图表数据
@datasets_bp.route("/<path:dataset_id>/chart", methods=["GET"])
def get_dataset_chart(dataset_id):
    """根据指定字段和图表类型生成图表数据"""
    try:
        print(f"get_dataset_chart: {dataset_id}")
        file_path = os.path.join(DATA_DIR, dataset_id)
        if not os.path.exists(file_path):
            return jsonify({"status": "error", "message": "Dataset not found"}), 404

        extension = os.path.splitext(dataset_id)[1].lower()
        if extension not in [".shp", ".geojson", ".json", ".csv", ".xls", ".xlsx"]:
            if extension == ".json" and not is_geojson(file_path):
                return (
                    jsonify(
                        {
                            "status": "error",
                            "message": "Only vector or table data supported for charts",
                        }
                    ),
                    400,
                )
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Only vector or table data supported for charts",
                    }
                ),
                400,
            )

        # 获取GET请求参数
        field = request.args.get("field")
        chart_type = request.args.get("chartType", "bar")
        group_by = request.args.get("groupBy")  # 可选分组字段

        print(
            f"图表请求参数: field={field}, chart_type={chart_type}, group_by={group_by}"
        )

        if not field:
            return (
                jsonify({"status": "error", "message": "Field parameter is required"}),
                400,
            )

        # 读取矢量数据
        if extension == ".shp" or extension == ".geojson" or (extension == ".json" and is_geojson(file_path)):
            # GeoJSON格式可以直接读取
            if extension == ".geojson" or extension == ".json":
                try:
                    gdf = gpd.read_file(file_path)
                    print(f"成功读取GeoJSON文件: {file_path}")
                    
                    # 处理bytes类型数据，将其转换为字符串，以便JSON序列化
                    for col in gdf.columns:
                        if col != 'geometry':
                            # 检查是否有bytes类型的数据
                            if gdf[col].dtype == 'object':
                                # 转换bytes为字符串，尝试多种编码
                                def decode_bytes_value(x):
                                    if isinstance(x, bytes):
                                        # 方法1：直接尝试多种编码来解码bytes
                                        for encoding in ['utf-8', 'gbk', 'gb2312', 'latin1']:
                                            try:
                                                decoded = x.decode(encoding)
                                                # 检查解码结果是否仍然是十六进制字符串
                                                if all(c in '0123456789abcdefABCDEF' for c in decoded):
                                                    # 可能是十六进制表示，尝试方法2
                                                    continue
                                                return decoded
                                            except UnicodeDecodeError:
                                                continue
                                        
                                        # 方法2：假设bytes解码后是十六进制字符串，需要进一步解码
                                        try:
                                            # 先用latin1解码（保证不会出错）得到十六进制字符串
                                            hex_str = x.decode('latin1', errors='replace')
                                            # 过滤掉非十六进制字符
                                            hex_str = ''.join(c for c in hex_str if c in '0123456789abcdefABCDEF')
                                            
                                            # 将十六进制字符串转换为字节序列
                                            byte_array = bytearray()
                                            for i in range(0, len(hex_str), 2):
                                                if i + 1 < len(hex_str):
                                                    byte_array.append(int(hex_str[i:i+2], 16))
                                            
                                            # 尝试用GBK/GB2312解码
                                            for encoding in ['gbk', 'gb2312']:
                                                try:
                                                    return byte_array.decode(encoding)
                                                except UnicodeDecodeError:
                                                    continue
                                        except Exception:
                                            pass
                                        
                                        # 如果所有方法都失败，使用utf-8并替换错误字符
                                        return x.decode('utf-8', errors='replace')
                                    return x
                                gdf[col] = gdf[col].apply(decode_bytes_value)
                except Exception as e:
                    print(f"读取GeoJSON文件出现错误: {str(e)}")
                    return jsonify({"status": "error", "message": f"无法读取GeoJSON数据: {str(e)}"}), 500
            else:
                # Shapefile需要尝试多种编码
                encodings_to_try = ["utf-8", "gbk", "gb2312", "latin1"]
                gdf = None
                for encoding in encodings_to_try:
                    try:
                        gdf = gpd.read_file(file_path, encoding=encoding)
                        print(f"成功使用编码 {encoding} 读取shapefile")
                        
                        # 处理bytes类型数据，将其转换为字符串，以便JSON序列化
                        for col in gdf.columns:
                            if col != 'geometry':
                                # 检查是否有bytes类型的数据
                                if gdf[col].dtype == 'object':
                                    # 转换bytes为字符串，尝试多种编码
                                    def decode_bytes_value(x):
                                        if isinstance(x, bytes):
                                            # 方法1：直接尝试多种编码来解码bytes
                                            for encoding in ['utf-8', 'gbk', 'gb2312', 'latin1']:
                                                try:
                                                    decoded = x.decode(encoding)
                                                    # 检查解码结果是否仍然是十六进制字符串
                                                    if all(c in '0123456789abcdefABCDEF' for c in decoded):
                                                        # 可能是十六进制表示，尝试方法2
                                                        continue
                                                    return decoded
                                                except UnicodeDecodeError:
                                                    continue
                                            
                                            # 方法2：假设bytes解码后是十六进制字符串，需要进一步解码
                                            try:
                                                # 先用latin1解码（保证不会出错）得到十六进制字符串
                                                hex_str = x.decode('latin1', errors='replace')
                                                # 过滤掉非十六进制字符
                                                hex_str = ''.join(c for c in hex_str if c in '0123456789abcdefABCDEF')
                                                
                                                # 将十六进制字符串转换为字节序列
                                                byte_array = bytearray()
                                                for i in range(0, len(hex_str), 2):
                                                    if i + 1 < len(hex_str):
                                                        byte_array.append(int(hex_str[i:i+2], 16))
                                                
                                                # 尝试用GBK/GB2312解码
                                                for encoding in ['gbk', 'gb2312']:
                                                    try:
                                                        return byte_array.decode(encoding)
                                                    except UnicodeDecodeError:
                                                        continue
                                            except Exception:
                                                pass
                                            
                                            # 如果所有方法都失败，使用utf-8并替换错误字符
                                            return x.decode('utf-8', errors='replace')
                                        return x
                                    gdf[col] = gdf[col].apply(decode_bytes_value)
                        break
                    except UnicodeDecodeError:
                        print(f"使用编码 {encoding} 读取失败，尝试下一个")
                        continue
                    except Exception as e:
                        print(f"读取shapefile出现错误: {str(e)}")
                        break
        else:
            # CSV 或 Excel
            try:
                if extension == ".csv":
                    gdf = pd.read_csv(file_path)
                else:
                    gdf = pd.read_excel(file_path)
                    
                # 处理bytes类型数据，将其转换为字符串，以便JSON序列化
                for col in gdf.columns:
                    # 检查是否有bytes类型的数据
                    if gdf[col].dtype == 'object':
                        # 转换bytes为字符串，尝试多种编码
                        def decode_bytes_value(x):
                            if isinstance(x, bytes):
                                # 方法1：直接尝试多种编码来解码bytes
                                for encoding in ['utf-8', 'gbk', 'gb2312', 'latin1']:
                                    try:
                                        decoded = x.decode(encoding)
                                        # 检查解码结果是否仍然是十六进制字符串
                                        if all(c in '0123456789abcdefABCDEF' for c in decoded):
                                            # 可能是十六进制表示，尝试方法2
                                            continue
                                        return decoded
                                    except UnicodeDecodeError:
                                        continue
                                
                                # 方法2：假设bytes解码后是十六进制字符串，需要进一步解码
                                try:
                                    # 先用latin1解码（保证不会出错）得到十六进制字符串
                                    hex_str = x.decode('latin1', errors='replace')
                                    # 过滤掉非十六进制字符
                                    hex_str = ''.join(c for c in hex_str if c in '0123456789abcdefABCDEF')
                                    
                                    # 将十六进制字符串转换为字节序列
                                    byte_array = bytearray()
                                    for i in range(0, len(hex_str), 2):
                                        if i + 1 < len(hex_str):
                                            byte_array.append(int(hex_str[i:i+2], 16))
                                    
                                    # 尝试用GBK/GB2312解码
                                    for encoding in ['gbk', 'gb2312']:
                                        try:
                                            return byte_array.decode(encoding)
                                        except UnicodeDecodeError:
                                            continue
                                except Exception:
                                    pass
                                
                                # 如果所有方法都失败，使用utf-8并替换错误字符
                                return x.decode('utf-8', errors='replace')
                            return x
                        gdf[col] = gdf[col].apply(decode_bytes_value)
            except Exception as e:
                return (
                    jsonify(
                        {"status": "error", "message": f"无法读取表格数据: {str(e)}"}
                    ),
                    500,
                )

        if gdf is None or field not in gdf.columns:
            if gdf is None:
                print(f"无法读取数据集 {dataset_id}")
            else:
                print(f"字段 {field} 不在数据集中，可用字段: {list(gdf.columns)}")
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": f"Cannot read dataset or field {field} not found",
                    }
                ),
                400,
            )

        # 根据图表类型生成数据
        chart_data = {}

        if chart_type == "pie":
            # 饼图数据
            if group_by and group_by in gdf.columns:
                # 按分组字段统计
                value_counts = gdf[group_by].value_counts()
                series = [
                    {"name": str(name), "value": int(count)}
                    for name, count in value_counts.items()
                ]
            else:
                # 按字段值分布统计
                if pd.api.types.is_numeric_dtype(gdf[field]):
                    # 数值型字段分段统计
                    bins = min(10, int(gdf[field].nunique()))
                    bins = max(bins, 5)  # 至少5个区间
                    hist, bin_edges = np.histogram(gdf[field].dropna(), bins=bins)
                    series = []
                    for i in range(len(hist)):
                        bin_name = f"{bin_edges[i]:.2f} - {bin_edges[i+1]:.2f}"
                        series.append({"name": bin_name, "value": int(hist[i])})
                else:
                    # 类别型字段
                    value_counts = gdf[field].value_counts().head(20)  # 最多20个类别
                    series = [
                        {"name": str(name), "value": int(count)}
                        for name, count in value_counts.items()
                    ]

            chart_data = {"series": series}

        elif chart_type == "bar" or chart_type == "line":
            # 柱状图/折线图数据
            if group_by and group_by in gdf.columns:
                # 按分组计算字段统计
                if pd.api.types.is_numeric_dtype(gdf[field]):
                    # 数值型字段计算平均值
                    grouped = gdf.groupby(group_by)[field].mean().reset_index()
                    categories = grouped[group_by].astype(str).tolist()
                    values = grouped[field].tolist()
                else:
                    # 类别型字段计算数量
                    grouped = gdf.groupby(group_by).size().reset_index(name="count")
                    categories = grouped[group_by].astype(str).tolist()
                    values = grouped["count"].tolist()

                chart_data = {
                    "xAxis": categories,
                    "series": [{"name": field, "data": values}],
                }
            else:
                # 没有分组，返回字段值分布
                if pd.api.types.is_numeric_dtype(gdf[field]):
                    # 数值型字段分段统计
                    bins = min(10, int(gdf[field].nunique()))
                    bins = max(bins, 5)  # 至少5个区间
                    hist, bin_edges = np.histogram(gdf[field].dropna(), bins=bins)
                    categories = [
                        f"{bin_edges[i]:.2f} - {bin_edges[i+1]:.2f}"
                        for i in range(len(hist))
                    ]

                    chart_data = {
                        "xAxis": categories,
                        "series": [{"name": field, "data": hist.tolist()}],
                    }
                else:
                    # 类别型字段
                    value_counts = gdf[field].value_counts().head(20)  # 最多20个类别
                    categories = [str(name) for name in value_counts.index]
                    values = value_counts.values.tolist()

                    chart_data = {
                        "xAxis": categories,
                        "series": [{"name": field, "data": values}],
                    }

        elif chart_type == "scatter":
            # 散点图需要两个字段
            second_field = request.args.get("secondField")
            if not second_field or second_field not in gdf.columns:
                return (
                    jsonify(
                        {
                            "status": "error",
                            "message": "Second field is required for scatter plot",
                        }
                    ),
                    400,
                )

            # 确保两个字段都是数值型
            if not pd.api.types.is_numeric_dtype(
                gdf[field]
            ) or not pd.api.types.is_numeric_dtype(gdf[second_field]):
                return (
                    jsonify(
                        {
                            "status": "error",
                            "message": "Both fields must be numeric for scatter plot",
                        }
                    ),
                    400,
                )

            # 准备散点图数据
            data_points = []
            for idx, row in gdf.iterrows():
                if pd.isna(row[field]) or pd.isna(row[second_field]):
                    continue
                data_points.append([float(row[field]), float(row[second_field])])

            chart_data = {
                "xAxis": {"name": field},
                "yAxis": {"name": second_field},
                "series": [{"name": "scatter", "type": "scatter", "data": data_points}],
            }

        else:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": f"Unsupported chart type: {chart_type}",
                    }
                ),
                400,
            )

        print(
            f"返回图表数据: {chart_type} 类型，数据大小约 {len(str(chart_data))} 字节"
        )
        return jsonify(chart_data)

    except Exception as e:
        import traceback

        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


# 上传数据集
@datasets_bp.route("/upload", methods=["POST"])
def upload_dataset():
    # 实际应用中需要处理文件上传
    # 这里仅返回成功响应
    return jsonify(
        {
            "message": "数据集上传成功",
            "id": "new-dataset-" + str(np.random.randint(1000, 9999)),
        }
    )


# 获取GeoJSON数据
@datasets_bp.route("/<path:dataset_id>/geojson", methods=["GET"])
def get_dataset_geojson(dataset_id):
    """获取矢量数据的GeoJSON格式"""
    file_path = os.path.join(DATA_DIR, dataset_id)
    if not os.path.exists(file_path):
        return jsonify({"status": "error", "message": "Dataset not found"}), 404

    # 检查文件是否是矢量数据
    extension = os.path.splitext(dataset_id)[1].lower()
    if extension not in [".shp", ".geojson", ".json"]:
        return jsonify({"status": "error", "message": "Not a vector dataset"}), 400
    
    # 如果是JSON文件，检查是否是GeoJSON格式
    if extension == ".json" and not is_geojson(file_path):
        return jsonify({"status": "error", "message": "Not a valid GeoJSON file"}), 400

    # 获取请求参数，是否需要转换到WGS84
    to_wgs84 = request.args.get("to_wgs84", "false").lower() == "true"

    try:
        # 尝试使用多种编码读取
        encodings_to_try = ["utf-8", "gbk", "gb2312", "latin1"]
        gdf = None
        for encoding in encodings_to_try:
            try:
                gdf = gpd.read_file(file_path, encoding=encoding)
                break  # 成功读取，跳出循环
            except UnicodeDecodeError:
                continue
            except Exception as e:
                break

        if gdf is None:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "Failed to read vector data with any encoding",
                    }
                ),
                500,
            )

        # 获取原始坐标系信息
        original_crs = gdf.crs
        crs_wkt = None
        if original_crs:
            try:
                crs_wkt = original_crs.to_wkt()
            except:
                crs_wkt = str(original_crs)

        # 如果需要转换到WGS84且当前不是WGS84
        if to_wgs84 and original_crs and original_crs.to_epsg() != 4326:
            try:
                print(f"将数据从 {original_crs} 转换到 WGS84")
                gdf = gdf.to_crs(epsg=4326)
            except Exception as e:
                print(f"坐标转换失败: {str(e)}")
                # 继续使用原始坐标系

        # 处理bytes类型数据，将其转换为字符串，以便JSON序列化
        for col in gdf.columns:
            if col != 'geometry':
                # 检查是否有bytes类型的数据
                if gdf[col].dtype == 'object':
                    # 转换bytes为字符串，尝试多种编码
                    def decode_bytes_value(x):
                        if isinstance(x, bytes):
                            # 方法1：直接尝试多种编码来解码bytes
                            for encoding in ['utf-8', 'gbk', 'gb2312', 'latin1']:
                                try:
                                    decoded = x.decode(encoding)
                                    # 检查解码结果是否仍然是十六进制字符串
                                    if all(c in '0123456789abcdefABCDEF' for c in decoded):
                                        # 可能是十六进制表示，尝试方法2
                                        continue
                                    return decoded
                                except UnicodeDecodeError:
                                    continue
                            
                            # 方法2：假设bytes解码后是十六进制字符串，需要进一步解码
                            try:
                                # 先用latin1解码（保证不会出错）得到十六进制字符串
                                hex_str = x.decode('latin1', errors='replace')
                                # 过滤掉非十六进制字符
                                hex_str = ''.join(c for c in hex_str if c in '0123456789abcdefABCDEF')
                                
                                # 将十六进制字符串转换为字节序列
                                byte_array = bytearray()
                                for i in range(0, len(hex_str), 2):
                                    if i + 1 < len(hex_str):
                                        byte_array.append(int(hex_str[i:i+2], 16))
                                
                                # 尝试用GBK/GB2312解码
                                for encoding in ['gbk', 'gb2312']:
                                    try:
                                        return byte_array.decode(encoding)
                                    except UnicodeDecodeError:
                                        continue
                            except Exception:
                                pass
                            
                            # 如果所有方法都失败，使用utf-8并替换错误字符
                            return x.decode('utf-8', errors='replace')
                        return x
                    gdf[col] = gdf[col].apply(decode_bytes_value)
        
        # 转换为GeoJSON
        try:
            geojson_data = json.loads(gdf.to_json())
        except TypeError as e:
            # 如果仍然有序列化问题，尝试更严格的处理
            print(f"GeoJSON序列化错误: {str(e)}，尝试更严格的数据清理")
            
            # 查找并处理所有可能导致JSON序列化问题的数据类型
            for col in gdf.columns:
                if col != 'geometry':
                    # 将所有非字符串、非数字类型转换为字符串
                    gdf[col] = gdf[col].apply(lambda x: str(x) if not (isinstance(x, (int, float, str, bool, type(None)))) else x)
            
            # 再次尝试转换
            geojson_data = json.loads(gdf.to_json())

        # 添加坐标系信息到GeoJSON
        if original_crs:
            if "crs" not in geojson_data:
                geojson_data["crs"] = {
                    "type": "name",
                    "properties": {"name": str(original_crs)},
                }

        # 添加元数据
        geojson_data["metadata"] = {
            "crs": str(gdf.crs),
            "original_crs": str(original_crs) if original_crs else None,
            "crs_wkt": crs_wkt,
            "feature_count": len(gdf),
            "converted_to_wgs84": to_wgs84
            and original_crs
            and original_crs.to_epsg() != 4326,
        }

        # 设置正确的响应头
        response = jsonify(geojson_data)
        response.headers["Content-Type"] = "application/json"
        return response

    except Exception as e:
        import traceback

        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


# 获取栅格瓦片服务
@datasets_bp.route("/<dataset_id>/tiles/<int:z>/<int:x>/<int:y>.png", methods=["GET"])
def get_dataset_tile(dataset_id, z, x, y):
    """获取栅格数据的瓦片服务"""
    file_path = os.path.join(DATA_DIR, dataset_id)
    if not os.path.exists(file_path):
        return jsonify({"status": "error", "message": "Dataset not found"}), 404

    # 检查文件是否是栅格数据
    extension = os.path.splitext(dataset_id)[1].lower()
    if extension != ".tif":
        return jsonify({"status": "error", "message": "Not a raster dataset"}), 400

    try:
        # 这里简化处理，实际生产环境应该使用缓存和预生成瓦片
        import io
        from PIL import Image
        import numpy as np
        import math

        # 获取瓦片范围
        n = 2.0**z
        west_edge = -180.0 + x * 360.0 / n
        east_edge = -180.0 + (x + 1) * 360.0 / n
        south_edge = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))
        north_edge = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))

        with rasterio.open(file_path) as src:
            # 创建一个临时瓦片
            tile_size = 256
            out_shape = (tile_size, tile_size)

            # 如果栅格在瓦片范围之外，返回空白瓦片
            if (
                src.bounds.right < west_edge
                or src.bounds.left > east_edge
                or src.bounds.top < south_edge
                or src.bounds.bottom > north_edge
            ):
                # 创建空白瓦片
                img = Image.new("RGBA", (tile_size, tile_size), (0, 0, 0, 0))
                output = io.BytesIO()
                img.save(output, format="PNG")
                output.seek(0)
                return send_file(output, mimetype="image/png")

            # 从栅格中读取数据
            window = rasterio.windows.from_bounds(
                west_edge, south_edge, east_edge, north_edge, transform=src.transform
            )

            try:
                # 读取数据并重采样到瓦片大小
                data = src.read(
                    out_shape=out_shape,
                    window=window,
                    resampling=rasterio.warp.Resampling.bilinear,
                )

                # 简单的值映射为RGB
                # 这里根据实际数据类型和范围调整
                if src.count == 1:
                    # 单波段数据映射为灰度图
                    band = data[0]
                    # 归一化到0-255
                    min_val = band.min()
                    max_val = band.max() if band.max() > min_val else min_val + 1
                    normalized = ((band - min_val) / (max_val - min_val) * 255).astype(
                        np.uint8
                    )

                    # 创建RGB图像
                    rgb = np.stack([normalized, normalized, normalized], axis=0)
                else:
                    # 多波段数据，取前三个波段作为RGB
                    bands_to_use = min(3, src.count)
                    rgb = np.stack([data[i] for i in range(bands_to_use)], axis=0)

                    # 归一化每个波段
                    for i in range(bands_to_use):
                        band = rgb[i]
                        min_val = band.min()
                        max_val = band.max() if band.max() > min_val else min_val + 1
                        rgb[i] = ((band - min_val) / (max_val - min_val) * 255).astype(
                            np.uint8
                        )

                    # 如果波段少于3个，填充剩余的波段
                    while rgb.shape[0] < 3:
                        rgb = np.concatenate([rgb, np.zeros_like(rgb[0:1])], axis=0)

                # 创建PNG图像
                rgb = np.moveaxis(rgb, 0, -1)  # 将通道轴移到最后
                img = Image.fromarray(rgb.astype(np.uint8), "RGB")
            except Exception as tile_error:
                print(f"Error processing tile data: {str(tile_error)}")
                # 创建错误瓦片
                img = Image.new("RGB", (tile_size, tile_size), (255, 0, 0))

            # 返回PNG图像
            output = io.BytesIO()
            img.save(output, format="PNG")
            output.seek(0)
            return send_file(output, mimetype="image/png")

    except Exception as e:
        print(f"Error generating tile: {str(e)}")
        import traceback

        traceback.print_exc()

        # 返回错误图像
        img = Image.new("RGB", (256, 256), (255, 0, 0))
        output = io.BytesIO()
        img.save(output, format="PNG")
        output.seek(0)
        return send_file(output, mimetype="image/png")


# 获取栅格数据的完整图像
@datasets_bp.route("/<path:dataset_id>/image", methods=["GET"])
def get_dataset_image(dataset_id):
    """获取栅格数据的完整图像"""
    file_path = os.path.join(DATA_DIR, dataset_id)
    if not os.path.exists(file_path):
        return jsonify({"status": "error", "message": "Dataset not found"}), 404

    # 检查文件是否是栅格数据
    extension = os.path.splitext(dataset_id)[1].lower()
    if extension != ".tif":
        return jsonify({"status": "error", "message": "Not a raster dataset"}), 400

    try:
        # 使用rasterio和PIL处理图像
        import io
        from PIL import Image
        import numpy as np

        with rasterio.open(file_path) as src:
            # 读取数据
            width = src.width
            height = src.height

            # 如果图像太大，进行下采样
            max_size = 2048  # 最大尺寸，防止图像过大
            scale = 1
            if width > max_size or height > max_size:
                scale = min(max_size / width, max_size / height)
                new_width = int(width * scale)
                new_height = int(height * scale)
                print(f"调整图像大小: 从 {width}x{height} 到 {new_width}x{new_height}")
                data = src.read(
                    out_shape=(src.count, new_height, new_width),
                    resampling=rasterio.warp.Resampling.bilinear,
                )
            else:
                data = src.read()

            # 处理不同波段的图像
            if src.count == 1:
                # 单波段数据映射为灰度图
                band = data[0]
                # 处理无效值
                print("nodata", src.nodata)
                if src.nodata is not None:
                    # 检查nodata是否为nan
                    if np.isnan(src.nodata):
                        # 当nodata为nan时，使用np.isnan()来创建掩码
                        mask = ~np.isnan(band)
                    else:
                        # 当nodata为具体数值时，使用不等于比较
                        mask = band != src.nodata
                    
                    if mask.any():
                        valid_data = band[mask]
                        min_val = valid_data.min()
                        max_val = valid_data.max()
                    else:
                        min_val = 0
                        max_val = 255
                else:
                    # 没有nodata值时，仍需处理可能存在的nan
                    mask = ~np.isnan(band)
                    if mask.any():
                        valid_data = band[mask]
                        min_val = valid_data.min()
                        max_val = valid_data.max()
                    else:
                        min_val = 0
                        max_val = 255

                # 确保有效范围
                if min_val == max_val:
                    max_val = min_val + 1

                # 归一化到0-255
                normalized = ((band - min_val) / (max_val - min_val) * 255).astype(
                    np.uint8
                )

                # 创建PIL图像 (灰度模式)
                img = Image.fromarray(normalized, 'L')

                # 将灰度图像转换为RGBA，以便添加透明度
                img = img.convert('RGBA')

                # 创建alpha通道
                alpha = np.full_like(band, 255, dtype=np.uint8)

                # 如果有nodata值，将对应像素的alpha设置为0
                if src.nodata is not None:
                    # 检查nodata是否为nan
                    if np.isnan(src.nodata):
                        # 当nodata为nan时，使用np.isnan()来找到nodata位置
                        nodata_mask = np.isnan(band)
                    else:
                        # 当nodata为具体数值时，使用相等比较
                        nodata_mask = (band == src.nodata)
                    # 将这些位置在alpha通道中设置为0
                    alpha[nodata_mask] = 0
                else:
                    # 没有nodata值时，仍需处理可能存在的nan值
                    nan_mask = np.isnan(band)
                    alpha[nan_mask] = 0

                alpha_img = Image.fromarray(alpha, 'L')
                img.putalpha(alpha_img)

            elif src.count == 3:
                # 3波段数据直接作为RGB
                # 对于RGB图像，我们通常不处理nodata透明度，除非有特殊需求
                # 如果需要处理，可以为每个波段分别创建mask并合并
                rgb = np.zeros((data.shape[1], data.shape[2], 3), dtype=np.uint8)

                for i in range(3):
                    band = data[i]
                    # 处理无效值和NaN值
                    if src.nodata is not None:
                        # 创建掩码，排除nodata值和NaN值
                        mask = (band != src.nodata) & ~np.isnan(band)
                        if mask.any():
                            valid_data = band[mask]
                            min_val = valid_data.min() if valid_data.size > 0 else 0
                            max_val = valid_data.max() if valid_data.size > 0 else 255
                        else:
                            min_val = 0
                            max_val = 255
                    else:
                        # 只排除NaN值
                        mask = ~np.isnan(band)
                        valid_data = band[mask] if mask.any() else band
                        min_val = valid_data.min() if valid_data.size > 0 else 0
                        max_val = valid_data.max() if valid_data.size > 0 else 255

                    # 确保有效范围
                    if min_val == max_val:
                         max_val = min_val + 1

                    # 归一化到0-255，处理NaN值
                    # 创建一个临时数组用于归一化，将NaN值替换为min_val
                    temp_band = np.copy(band)
                    if np.isnan(temp_band).any():
                        temp_band[np.isnan(temp_band)] = min_val
                    
                    # 归一化到0-255
                    normalized = ((temp_band - min_val) / (max_val - min_val) * 255).astype(np.uint8)
                    rgb[:, :, i] = normalized

                img = Image.fromarray(rgb, "RGB")
            
            else:
                # 处理其他波段数量（2波段、4波段等）
                print(f"处理 {src.count} 波段图像")
                
                if src.count == 2:
                    # 2波段：使用前两个波段作为RG，B设为0
                    rgb = np.zeros((data.shape[1], data.shape[2], 3), dtype=np.uint8)
                    
                    for i in range(2):
                        band = data[i]
                        # 处理无效值和NaN值
                        if src.nodata is not None:
                            mask = (band != src.nodata) & ~np.isnan(band)
                            if mask.any():
                                valid_data = band[mask]
                                min_val = valid_data.min() if valid_data.size > 0 else 0
                                max_val = valid_data.max() if valid_data.size > 0 else 255
                            else:
                                min_val = 0
                                max_val = 255
                        else:
                            mask = ~np.isnan(band)
                            valid_data = band[mask] if mask.any() else band
                            min_val = valid_data.min() if valid_data.size > 0 else 0
                            max_val = valid_data.max() if valid_data.size > 0 else 255

                        if min_val == max_val:
                            max_val = min_val + 1

                        temp_band = np.copy(band)
                        if np.isnan(temp_band).any():
                            temp_band[np.isnan(temp_band)] = min_val
                        
                        normalized = ((temp_band - min_val) / (max_val - min_val) * 255).astype(np.uint8)
                        rgb[:, :, i] = normalized
                    
                    img = Image.fromarray(rgb, "RGB")
                    
                elif src.count >= 4:
                    # 4波段或更多：使用前3个波段作为RGB
                    rgb = np.zeros((data.shape[1], data.shape[2], 3), dtype=np.uint8)
                    
                    for i in range(3):
                        band = data[i]
                        # 处理无效值和NaN值
                        if src.nodata is not None:
                            mask = (band != src.nodata) & ~np.isnan(band)
                            if mask.any():
                                valid_data = band[mask]
                                min_val = valid_data.min() if valid_data.size > 0 else 0
                                max_val = valid_data.max() if valid_data.size > 0 else 255
                            else:
                                min_val = 0
                                max_val = 255
                        else:
                            mask = ~np.isnan(band)
                            valid_data = band[mask] if mask.any() else band
                            min_val = valid_data.min() if valid_data.size > 0 else 0
                            max_val = valid_data.max() if valid_data.size > 0 else 255

                        if min_val == max_val:
                            max_val = min_val + 1

                        temp_band = np.copy(band)
                        if np.isnan(temp_band).any():
                            temp_band[np.isnan(temp_band)] = min_val
                        
                        normalized = ((temp_band - min_val) / (max_val - min_val) * 255).astype(np.uint8)
                        rgb[:, :, i] = normalized
                    
                    img = Image.fromarray(rgb, "RGB")
                
                else:
                    # 未知波段数量，创建错误图像
                    print(f"不支持的波段数量: {src.count}")
                    img = Image.new('RGB', (256, 256), color=(255, 0, 0))

            # 确保img已经被初始化（这个检查现在应该不会触发）
            if 'img' not in locals():
                # 如果img未定义，创建一个空白图像
                img = Image.new('RGB', (256, 256), color=(255, 255, 255))
                print("警告：无法正确处理图像数据，返回空白图像")
                
            # 将PIL图像保存到内存中的字节流
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='PNG')
            img_byte_arr = img_byte_arr.getvalue()

        # 返回图像文件
        return send_file(
            io.BytesIO(img_byte_arr),
            mimetype='image/png',
            as_attachment=False,
        )

    except Exception as e:
        print(f"获取栅格图像出错: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "status": "error",
            "message": f"获取栅格图像失败: {str(e)}"
        }), 500


# 获取指定路径下的图片列表
@datasets_bp.route("/images/<path:image_path>", methods=["GET"])
def get_images(image_path):
    """获取指定路径下的图片列表"""
    try:
        print(f"请求的图片路径: {image_path}")
        
        # 检查路径是否合法
        if image_path not in ALLOWED_IMAGE_PATHS:
            return jsonify({
                "status": "error", 
                "message": "非法的访问路径，只允许访问预定义的图片目录"
            }), 403

        # 如果是total路径，获取所有允许路径下的图片
        if image_path == "total":
            all_images = []
            for allowed_path in ALLOWED_IMAGE_PATHS:
                if allowed_path == "total":
                    continue
                
                path_dir = os.path.join(DATA_DIR, allowed_path)
                if os.path.exists(path_dir) and os.path.isdir(path_dir):
                    # 递归遍历目录
                    for root, _, files in os.walk(path_dir):
                        for filename in files:
                            file_path = os.path.join(root, filename)
                            
                            if os.path.isfile(file_path) and filename.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".bmp")):
                                file_stats = os.stat(file_path)
                                
                                # 构建相对于DATA_DIR的路径
                                relative_path = os.path.relpath(file_path, DATA_DIR)
                                
                                image_info = {
                                    "id": relative_path.replace('\\', '/'),
                                    "name": os.path.splitext(filename)[0],
                                    "path": relative_path.replace('\\', '/'),  # 使用斜杠作为路径分隔符
                                    "size": file_stats.st_size,
                                    "source_dir": allowed_path,  # 添加来源目录信息
                                    "createTime": datetime.fromtimestamp(file_stats.st_ctime).strftime('%Y-%m-%d %H:%M:%S'),
                                    "modifyTime": datetime.fromtimestamp(file_stats.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                                    "extension": os.path.splitext(filename)[1].lower()
                                }
                                
                                all_images.append(image_info)
            
            # 按修改时间排序
            all_images.sort(key=lambda x: x["modifyTime"], reverse=True)
            return jsonify({"status": "success", "data": all_images})
        
        # 常规路径处理
        images_dir = os.path.join(DATA_DIR, image_path)
        
        # 确保文件夹存在
        if not os.path.exists(images_dir):
            os.makedirs(images_dir)
        
        if not os.path.isdir(images_dir):
            return jsonify({"status": "error", "message": "指定路径不是目录"}), 400
        
        images = []
        
        # 递归遍历文件夹中的所有文件
        for root, _, files in os.walk(images_dir):
            for filename in files:
                file_path = os.path.join(root, filename)
                
                # 只处理图片文件
                if os.path.isfile(file_path) and filename.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".bmp")):
                    # 构建相对于 DATA_DIR 的路径
                    relative_path = os.path.relpath(file_path, DATA_DIR)
                    file_stats = os.stat(file_path)
                    
                    image_info = {
                        "id": relative_path.replace('\\', '/'), # 使用斜杠作为ID分隔符
                        "name": os.path.splitext(filename)[0],
                        "path": relative_path.replace('\\', '/'), # 使用斜杠作为路径分隔符
                        "size": file_stats.st_size,
                        "createTime": datetime.fromtimestamp(file_stats.st_ctime).strftime('%Y-%m-%d %H:%M:%S'),
                        "modifyTime": datetime.fromtimestamp(file_stats.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                        "extension": os.path.splitext(filename)[1].lower()
                    }

                    
                    images.append(image_info)
        
        # 按修改时间排序
        images.sort(key=lambda x: x["modifyTime"], reverse=True)
        
        return jsonify({"status": "success", "data": images})
    
    except Exception as e:
        print(f"获取图片列表出错: {str(e)}")
        return jsonify({"status": "error", "message": f"获取图片列表失败: {str(e)}"}), 500


# 获取指定路径下的图片
@datasets_bp.route("/images/<path:image_path>/<image_id>", methods=["GET"])
def get_image(image_path, image_id):
    print("get_image")
    """获取指定路径下的单个图片"""
    try:
        # 构建图片文件路径
        image_path = os.path.join(DATA_DIR, image_path, image_id)
        
        # 确保路径在DATA_DIR范围内
        if not os.path.realpath(image_path).startswith(os.path.realpath(DATA_DIR)):
            return jsonify({"status": "error", "message": "访问路径不合法"}), 403
        
        # 检查文件是否存在
        if not os.path.exists(image_path) or not os.path.isfile(image_path):
            return jsonify({"status": "error", "message": "图片不存在"}), 404
        
        # 返回图片文件
        return send_file(image_path, mimetype=f"image/{os.path.splitext(image_id)[1][1:]}")
    
    except Exception as e:
        print(f"获取图片出错: {str(e)}")
        return jsonify({"status": "error", "message": f"获取图片失败: {str(e)}"}), 500


# 获取指定路径下的图片缩略图
@datasets_bp.route("/images/<path:image_path>/<image_id>/preview", methods=["GET"])
def get_image_preview(image_path, image_id):
    """获取指定路径下图片的缩略图"""
    try:
        # 构建图片文件路径
        image_path = os.path.join(DATA_DIR, image_path, image_id)
        
        # 确保路径在DATA_DIR范围内
        if not os.path.realpath(image_path).startswith(os.path.realpath(DATA_DIR)):
            return jsonify({"status": "error", "message": "访问路径不合法"}), 403
        
        # 检查文件是否存在
        if not os.path.exists(image_path) or not os.path.isfile(image_path):
            return jsonify({"status": "error", "message": "图片不存在"}), 404
        
        # 直接返回原图作为缩略图（可以根据需要实现图片缩放）
        return send_file(image_path, mimetype=f"image/{os.path.splitext(image_id)[1][1:]}")
    
    except Exception as e:
        print(f"获取图片缩略图出错: {str(e)}")
        return jsonify({"status": "error", "message": f"获取图片缩略图失败: {str(e)}"}), 500


# 根据数据集ID获取数据集路径
def get_dataset_path(dataset_id):
    """根据数据集ID获取数据集的完整文件路径
    
    参数:
        dataset_id: 数据集ID（相对于DATA_DIR的路径）
        
    返回:
        str: 数据集的完整文件路径
    """
    if not dataset_id:
        return None
    
    # 构建完整路径
    file_path = os.path.join(DATA_DIR, dataset_id)
    
    # 检查文件是否存在
    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        print(f"数据集不存在: {file_path}")
        return None
    
    return file_path


# 根据数据集ID获取数据集信息
def get_dataset_by_id(dataset_id):
    """根据数据集ID获取数据集的详细信息
    
    参数:
        dataset_id: 数据集ID（相对于DATA_DIR的路径）
        
    返回:
        dict: 数据集的详细信息，包括名称、类型、格式等
    """
    if not dataset_id:
        return None
    
    # 构建完整路径
    file_path = os.path.join(DATA_DIR, dataset_id)
    
    # 检查文件是否存在
    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        print(f"数据集不存在: {file_path}")
        return None
    
    try:
        # 获取文件信息
        file_info = get_file_info(file_path)
        
        # 构建数据集信息
        dataset_info = {
            'id': dataset_id,
            'name': os.path.splitext(os.path.basename(file_path))[0],
            'path': dataset_id,
            'type': file_info.get('type'),
            'format': file_info.get('format'),
            'size': os.path.getsize(file_path),
            'createTime': datetime.fromtimestamp(os.path.getctime(file_path)).strftime('%Y-%m-%d %H:%M:%S'),
            'modifyTime': datetime.fromtimestamp(os.path.getmtime(file_path)).strftime('%Y-%m-%d %H:%M:%S')
        }
        
        return dataset_info
    
    except Exception as e:
        print(f"获取数据集信息出错: {str(e)}")
        return None


@datasets_bp.route("/<path:dataset_id>/download", methods=["GET"])
def download_dataset(dataset_id):
    """下载数据集文件
    
    参数:
        dataset_id: 数据集ID（文件路径）
        
    返回:
        文件下载响应
    """
    try:
        # 检查路径是否合法
        if '..' in dataset_id or dataset_id.startswith('/'):
            return jsonify({"status": "error", "message": "非法的文件路径"}), 400
        
        # 构建完整文件路径
        file_path = os.path.join(DATA_DIR, dataset_id)
        
        # 检查文件是否存在
        if not os.path.exists(file_path):
            return jsonify({"status": "error", "message": "文件不存在"}), 404
        
        # 检查是否为文件（不是目录）
        if not os.path.isfile(file_path):
            return jsonify({"status": "error", "message": "指定路径不是文件"}), 400
        
        # 获取文件名
        filename = os.path.basename(file_path)
        
        # 返回文件下载响应
        return send_file(
            file_path,
            as_attachment=True,
            download_name=filename,
            mimetype='application/octet-stream'
        )
        
    except Exception as e:
        print(f"下载文件出错: {str(e)}")
        return jsonify({"status": "error", "message": f"下载失败: {str(e)}"}), 500
