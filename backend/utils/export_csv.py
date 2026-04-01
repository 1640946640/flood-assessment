import rasterio
import numpy as np
import pandas as pd
from rasterio.warp import transform_bounds, reproject, Resampling, transform
from rasterio.transform import from_bounds
from rasterio.crs import CRS
import os
import time

def export_multi_raster_to_csv(raster_paths, output_csv_path, raster_names=None, align_method='nearest'):
    """
    将多幅栅格数据按坐标导出为CSV文件，坐标统一转换为WGS84
    
    参数:
    raster_paths: 栅格文件路径列表
    output_csv_path: 输出CSV文件路径
    raster_names: 栅格名称列表（可选，用于CSV列名）
    align_method: 栅格对齐方法 ('nearest', 'bilinear', 'cubic')
    
    返回:
    导出的数据点数量
    """
    
    start_time = time.time()
    
    try:
        if not raster_paths:
            raise ValueError("栅格路径列表不能为空")
            
        # 如果没有提供栅格名称，使用默认名称
        if raster_names is None:
            raster_names = [f"Raster{i+1}" for i in range(len(raster_paths))]
        elif len(raster_names) != len(raster_paths):
            raise ValueError("栅格名称列表长度必须与栅格路径列表长度一致")
            
        # 目标坐标系：WGS84
        target_crs = CRS.from_epsg(4326)
        
        # 读取所有栅格数据
        raster_data = []
        transforms = []
        crss = []
        nodatas = []
        
        print(f"开始读取 {len(raster_paths)} 个栅格文件...")
        
        for i, raster_path in enumerate(raster_paths):
            print(f"读取栅格 {i+1}: {raster_path}")
            with rasterio.open(raster_path) as src:
                data = src.read(1)
                raster_data.append(data)
                transforms.append(src.transform)
                crss.append(src.crs)
                nodatas.append(src.nodata)
                print(f"  - 尺寸: {data.shape}")
                print(f"  - 坐标系: {src.crs}")
        
        # 以第一个栅格为基准进行对齐
        reference_data = raster_data[0]
        reference_transform = transforms[0]
        reference_crs = crss[0]
        
        # 将所有栅格对齐到第一个栅格的空间范围和分辨率
        aligned_data = [reference_data]  # 第一个栅格作为基准
        aligned_nodatas = [nodatas[0]]
        
        print("开始对齐其他栅格到基准栅格...")
        
        # 对齐其他栅格到第一个栅格
        for i in range(1, len(raster_data)):
            print(f"对齐栅格 {i+1} 到基准栅格...")
            
            current_data = raster_data[i]
            current_transform = transforms[i]
            current_crs = crss[i]
            current_nodata = nodatas[i]
            
            # 如果坐标系或尺寸不一致，需要重投影/重采样
            if current_crs != reference_crs or current_data.shape != reference_data.shape:
                print(f"  - 原坐标系: {current_crs}")
                print(f"  - 原尺寸: {current_data.shape}")
                print(f"  - 目标坐标系: {reference_crs}")
                print(f"  - 目标尺寸: {reference_data.shape}")
                
                height_ref, width_ref = reference_data.shape
                
                # 创建目标数组
                aligned_array = np.empty((height_ref, width_ref), dtype=current_data.dtype)
                
                # 重投影/重采样
                reproject(
                    source=current_data,
                    destination=aligned_array,
                    src_transform=current_transform,
                    src_crs=current_crs,
                    dst_transform=reference_transform,
                    dst_crs=reference_crs,
                    resampling=getattr(Resampling, align_method)
                )
                
                aligned_data.append(aligned_array)
                aligned_nodatas.append(current_nodata)
            else:
                # 坐标系和尺寸都一致，直接使用
                aligned_data.append(current_data)
                aligned_nodatas.append(current_nodata)
            
        # 获取栅格尺寸
        rows, cols = reference_data.shape
        
        # 创建坐标和值的列表
        coordinates_wgs84 = []
        all_values = [[] for _ in range(len(aligned_data))]
        
        print(f"开始优化处理 {rows} x {cols} = {rows * cols} 个像元...")
        
        # 步骤1: 向量化计算所有坐标
        print("步骤1: 批量计算坐标...")
        
        # 创建行列索引网格
        row_indices, col_indices = np.mgrid[0:rows, 0:cols]
        row_flat = row_indices.flatten()
        col_flat = col_indices.flatten()
        
        # 向量化计算所有像元的地理坐标（像元中心点）
        x_orig = (reference_transform[2] + 
                 (col_flat + 0.5) * reference_transform[0] + 
                 (row_flat + 0.5) * reference_transform[1])
        y_orig = (reference_transform[5] + 
                 (col_flat + 0.5) * reference_transform[3] + 
                 (row_flat + 0.5) * reference_transform[4])
        
        # 步骤2: 向量化检查无效值
        print("步骤2: 批量检查无效值...")
        
        # 创建有效像元掩码
        valid_mask = np.ones(len(x_orig), dtype=bool)
        
        # 将所有栅格数据展平并检查无效值
        flat_data_list = []
        for i, (data, nodata) in enumerate(zip(aligned_data, aligned_nodatas)):
            flat_data = data.flatten()
            flat_data_list.append(flat_data)
            
            # 检查NaN值
            nan_mask = np.isnan(flat_data)
            valid_mask &= ~nan_mask
            
            # 检查NoData值
            if nodata is not None:
                try:
                    if isinstance(nodata, (int, float)):
                        nodata_mask = np.isclose(flat_data, nodata)
                        valid_mask &= ~nodata_mask
                except (TypeError, ValueError):
                    pass
        
        # 步骤3: 批量坐标转换
        print("步骤3: 批量坐标转换到WGS84...")
        
        # 只处理有效的坐标点
        valid_x_orig = x_orig[valid_mask]
        valid_y_orig = y_orig[valid_mask]
        
        if reference_crs != target_crs and len(valid_x_orig) > 0:
            # 批量转换坐标到WGS84
            x_wgs84_list, y_wgs84_list = transform(
                reference_crs, target_crs, 
                valid_x_orig.tolist(), valid_y_orig.tolist()
            )
            x_wgs84 = np.array(x_wgs84_list)
            y_wgs84 = np.array(y_wgs84_list)
        else:
            x_wgs84 = valid_x_orig
            y_wgs84 = valid_y_orig
        
        # 步骤4: 提取有效像元的值
        print("步骤4: 提取有效像元值...")
        
        # 提取所有有效像元的值
        for i, flat_data in enumerate(flat_data_list):
            valid_values = flat_data[valid_mask]
            all_values[i] = valid_values.tolist()
        
        # 将坐标转换为列表格式
        coordinates_wgs84 = list(zip(x_wgs84.tolist(), y_wgs84.tolist()))
        
        # 步骤5: 创建DataFrame
        print("步骤5: 创建DataFrame...")
        
        df_data = {
            'Longitude_WGS84': x_wgs84.tolist(),
            'Latitude_WGS84': y_wgs84.tolist()
        }
        
        # 添加每个栅格的值列
        for i, raster_name in enumerate(raster_names):
            df_data[f'{raster_name}_Value'] = all_values[i]
        
        df = pd.DataFrame(df_data)
        
        # 确保输出目录存在
        os.makedirs(os.path.dirname(output_csv_path), exist_ok=True)
        
        # 步骤6: 保存CSV文件
        print("步骤6: 保存CSV文件...")
        df.to_csv(output_csv_path, index=False, encoding='utf-8')
        
        end_time = time.time()
        processing_time = end_time - start_time
        total_pixels = rows * cols
        
        print(f"\n=== 优化处理完成 ===")
        print(f"成功导出 {len(df)} 个有效数据点到: {output_csv_path}")
        print(f"总处理时间: {processing_time:.2f} 秒")
        print(f"处理速度: {total_pixels/processing_time:.0f} 像元/秒")
        print(f"有效数据比例: {len(df)/total_pixels*100:.1f}%")
        column_names = ', '.join(['Longitude_WGS84', 'Latitude_WGS84'] + [f'{name}_Value' for name in raster_names])
        print(f"CSV文件包含列: {column_names}")
        print(f"坐标系统一转换为: WGS84 (EPSG:4326)")
        print(f"\n优化特性:")
        print(f"- 向量化坐标计算")
        print(f"- 批量坐标转换")
        print(f"- 优化的无效值检查")
        print(f"- 内存高效的数据处理")
        
        return len(df)
        
    except Exception as e:
        print(f"导出CSV时发生错误: {str(e)}")
        raise

def export_dual_raster_to_csv(raster1_path, raster2_path, output_csv_path, align_method='nearest'):
    """
    将两幅栅格数据按坐标导出为CSV文件（兼容性函数）
    
    参数:
    raster1_path: 第一幅栅格文件路径
    raster2_path: 第二幅栅格文件路径
    output_csv_path: 输出CSV文件路径
    align_method: 栅格对齐方法 ('nearest', 'bilinear', 'cubic')
    
    返回:
    导出的数据点数量
    """
    return export_multi_raster_to_csv(
        raster_paths=[raster1_path, raster2_path],
        output_csv_path=output_csv_path,
        raster_names=["Raster1", "Raster2"],
        align_method=align_method
    )

def export_dual_raster_to_csv_with_names(raster1_path, raster2_path, output_csv_path, 
                                        raster1_name="Raster1", raster2_name="Raster2", 
                                        align_method='nearest'):
    """
    将两幅栅格数据按坐标导出为CSV文件（可自定义栅格名称，兼容性函数）
    
    参数:
    raster1_path: 第一幅栅格文件路径
    raster2_path: 第二幅栅格文件路径
    output_csv_path: 输出CSV文件路径
    raster1_name: 第一幅栅格的名称（用于CSV列名）
    raster2_name: 第二幅栅格的名称（用于CSV列名）
    align_method: 栅格对齐方法 ('nearest', 'bilinear', 'cubic')
    
    返回:
    导出的数据点数量
    """
    return export_multi_raster_to_csv(
        raster_paths=[raster1_path, raster2_path],
        output_csv_path=output_csv_path,
        raster_names=[raster1_name, raster2_name],
        align_method=align_method
    )

# 示例使用方法
if __name__ == "__main__":
    # 示例1: 多栅格导出（推荐使用）
    raster_files = [
        r"D:\WebGIS\洪涝灾害影响评估\webgis-project\backend\data\compare_data\test.tif",
        r"D:\WebGIS\洪涝灾害影响评估\webgis-project\backend\data\金堂县DEM.tif",
        r"D:\WebGIS\洪涝灾害影响评估\webgis-project\backend\data\people.tif"
    ]
    
    raster_names = ["FloodDepth", "DEM", "Population"]
    
    export_multi_raster_to_csv(
        raster_paths=raster_files,
        output_csv_path="./multi_raster_data_wgs84.csv",
        raster_names=raster_names
    )
    
    # 示例2: 双栅格导出（兼容性函数）
    # export_dual_raster_to_csv(
    #     r"D:\WebGIS\洪涝灾害影响评估\webgis-project\backend\data\flood_results\g_IDF_20250621_131901_f727c592_IDFi.tif",
    #     r"D:\WebGIS\洪涝灾害影响评估\webgis-project\backend\data\金堂县DEM.tif",
    #     "./dual_raster_data_wgs84.csv"
    # )
    
    # 示例3: 自定义栅格名称（兼容性函数）
    # export_dual_raster_to_csv_with_names(
    #     "path/to/hazard.tif",
    #     "path/to/vulnerability.tif",
    #     "output/hazard_vulnerability_data_wgs84.csv",
    #     raster1_name="Hazard",
    #     raster2_name="Vulnerability"
    # )
    
    print("多栅格CSV导出工具已准备就绪")
    print("主要功能:")
    print("- 支持多个栅格文件同时导出")
    print("- 自动对齐不同坐标系和分辨率的栅格")
    print("- 坐标统一转换为WGS84 (EPSG:4326)")
    print("- 输出格式: Longitude_WGS84, Latitude_WGS84, [RasterName]_Value...")
    print("\n推荐使用 export_multi_raster_to_csv() 函数")