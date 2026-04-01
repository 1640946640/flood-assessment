import rasterio
import numpy as np
import pandas as pd
from rasterio.warp import transform_bounds, reproject, Resampling, transform
from rasterio.transform import from_bounds
from rasterio.crs import CRS
import os
from numba import jit, prange
import time

@jit(nopython=True, parallel=True)
def fast_coordinate_calculation(rows, cols, transform_params):
    """
    使用Numba JIT编译的快速坐标计算函数
    
    参数:
    rows, cols: 栅格行列数
    transform_params: [a, b, c, d, e, f] Affine变换参数
    
    返回:
    x_coords, y_coords: 坐标数组
    """
    x_coords = np.empty(rows * cols, dtype=np.float64)
    y_coords = np.empty(rows * cols, dtype=np.float64)
    
    a, b, c, d, e, f = transform_params
    
    idx = 0
    for row in prange(rows):
        for col in range(cols):
            # 计算像元中心点坐标
            x_coords[idx] = c + (col + 0.5) * a + (row + 0.5) * b
            y_coords[idx] = f + (col + 0.5) * d + (row + 0.5) * e
            idx += 1
    
    return x_coords, y_coords

@jit(nopython=True, parallel=True)
def fast_nodata_check(data_arrays, nodata_values, rows, cols):
    """
    使用Numba JIT编译的快速无效值检查函数
    
    参数:
    data_arrays: 栅格数据数组列表
    nodata_values: 无效值列表
    rows, cols: 栅格行列数
    
    返回:
    valid_mask: 有效像元掩码
    """
    valid_mask = np.ones(rows * cols, dtype=np.bool_)
    
    for i in prange(len(data_arrays)):
        data = data_arrays[i]
        nodata = nodata_values[i]
        
        idx = 0
        for row in range(rows):
            for col in range(cols):
                value = data[row, col]
                
                # 检查NaN
                if np.isnan(value):
                    valid_mask[idx] = False
                # 检查NoData值
                elif not np.isnan(nodata) and abs(value - nodata) < 1e-10:
                    valid_mask[idx] = False
                    
                idx += 1
    
    return valid_mask

def export_multi_raster_to_csv_optimized(raster_paths, output_csv_path, raster_names=None, 
                                        align_method='nearest', batch_size=10000):
    """
    优化版本的多栅格CSV导出函数
    
    参数:
    raster_paths: 栅格文件路径列表
    output_csv_path: 输出CSV文件路径
    raster_names: 栅格名称列表（可选，用于CSV列名）
    align_method: 栅格对齐方法 ('nearest', 'bilinear', 'cubic')
    batch_size: 批处理大小，用于坐标转换
    
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
                nodatas.append(src.nodata if src.nodata is not None else np.nan)
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
        total_pixels = rows * cols
        
        print(f"开始优化处理 {rows} x {cols} = {total_pixels} 个像元...")
        
        # 步骤1: 使用向量化操作计算所有坐标
        print("步骤1: 批量计算坐标...")
        transform_params = np.array([
            reference_transform[0],  # a
            reference_transform[1],  # b  
            reference_transform[2],  # c
            reference_transform[3],  # d
            reference_transform[4],  # e
            reference_transform[5]   # f
        ])
        
        x_coords, y_coords = fast_coordinate_calculation(rows, cols, transform_params)
        
        # 步骤2: 使用向量化操作检查无效值
        print("步骤2: 批量检查无效值...")
        
        # 准备数据数组和无效值数组
        data_arrays = [data.astype(np.float64) for data in aligned_data]
        nodata_array = np.array(aligned_nodatas, dtype=np.float64)
        
        valid_mask = fast_nodata_check(data_arrays, nodata_array, rows, cols)
        
        # 步骤3: 批量坐标转换
        print("步骤3: 批量坐标转换到WGS84...")
        
        if reference_crs != target_crs:
            # 只转换有效的坐标点
            valid_x = x_coords[valid_mask]
            valid_y = y_coords[valid_mask]
            
            # 批量转换坐标
            if len(valid_x) > 0:
                x_wgs84_list, y_wgs84_list = transform(
                    reference_crs, target_crs, valid_x.tolist(), valid_y.tolist()
                )
                x_wgs84 = np.array(x_wgs84_list)
                y_wgs84 = np.array(y_wgs84_list)
            else:
                x_wgs84 = np.array([])
                y_wgs84 = np.array([])
        else:
            x_wgs84 = x_coords[valid_mask]
            y_wgs84 = y_coords[valid_mask]
        
        # 步骤4: 提取有效像元的值
        print("步骤4: 提取有效像元值...")
        
        # 将2D数组展平并应用掩码
        all_values = []
        for data in aligned_data:
            flat_data = data.flatten()
            valid_values = flat_data[valid_mask]
            all_values.append(valid_values)
        
        # 步骤5: 创建DataFrame
        print("步骤5: 创建DataFrame...")
        
        df_data = {
            'Longitude_WGS84': x_wgs84,
            'Latitude_WGS84': y_wgs84
        }
        
        # 添加每个栅格的值列
        for i, raster_name in enumerate(raster_names):
            df_data[f'{raster_name}_Value'] = all_values[i]
        
        df = pd.DataFrame(df_data)
        
        # 确保输出目录存在
        os.makedirs(os.path.dirname(output_csv_path), exist_ok=True)
        
        # 保存为CSV
        print("步骤6: 保存CSV文件...")
        df.to_csv(output_csv_path, index=False, encoding='utf-8')
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        print(f"\n=== 优化处理完成 ===")
        print(f"成功导出 {len(df)} 个有效数据点到: {output_csv_path}")
        print(f"总处理时间: {processing_time:.2f} 秒")
        print(f"处理速度: {total_pixels/processing_time:.0f} 像元/秒")
        column_names = ', '.join(['Longitude_WGS84', 'Latitude_WGS84'] + [f'{name}_Value' for name in raster_names])
        print(f"CSV文件包含列: {column_names}")
        print(f"坐标系统一转换为: WGS84 (EPSG:4326)")
        
        return len(df)
        
    except Exception as e:
        print(f"导出CSV时发生错误: {str(e)}")
        raise

# 保持原有函数的兼容性，但使用优化版本
def export_multi_raster_to_csv(raster_paths, output_csv_path, raster_names=None, align_method='nearest'):
    """
    多栅格CSV导出函数（优化版本）
    """
    return export_multi_raster_to_csv_optimized(
        raster_paths, output_csv_path, raster_names, align_method
    )

def export_dual_raster_to_csv(raster1_path, raster2_path, output_csv_path, align_method='nearest'):
    """
    将两幅栅格数据按坐标导出为CSV文件（兼容性函数，优化版本）
    """
    return export_multi_raster_to_csv_optimized(
        raster_paths=[raster1_path, raster2_path],
        output_csv_path=output_csv_path,
        raster_names=["Raster1", "Raster2"],
        align_method=align_method
    )

def export_dual_raster_to_csv_with_names(raster1_path, raster2_path, output_csv_path, 
                                        raster1_name="Raster1", raster2_name="Raster2", 
                                        align_method='nearest'):
    """
    将两幅栅格数据按坐标导出为CSV文件（可自定义栅格名称，兼容性函数，优化版本）
    """
    return export_multi_raster_to_csv_optimized(
        raster_paths=[raster1_path, raster2_path],
        output_csv_path=output_csv_path,
        raster_names=[raster1_name, raster2_name],
        align_method=align_method
    )

# 性能对比函数
def compare_performance(raster_paths, output_dir="./"):
    """
    对比原版本和优化版本的性能
    """
    import sys
    sys.path.append('.')
    
    print("=== 性能对比测试 ===")
    
    # 测试优化版本
    print("\n测试优化版本...")
    start_time = time.time()
    try:
        count_optimized = export_multi_raster_to_csv_optimized(
            raster_paths=raster_paths,
            output_csv_path=os.path.join(output_dir, "test_optimized.csv"),
            raster_names=[f"Raster{i+1}" for i in range(len(raster_paths))]
        )
        time_optimized = time.time() - start_time
        print(f"优化版本完成: {time_optimized:.2f} 秒")
    except Exception as e:
        print(f"优化版本测试失败: {e}")
        return
    
    # 测试原版本
    print("\n测试原版本...")
    try:
        from export_csv import export_multi_raster_to_csv as original_export
        start_time = time.time()
        count_original = original_export(
            raster_paths=raster_paths,
            output_csv_path=os.path.join(output_dir, "test_original.csv"),
            raster_names=[f"Raster{i+1}" for i in range(len(raster_paths))]
        )
        time_original = time.time() - start_time
        print(f"原版本完成: {time_original:.2f} 秒")
        
        # 性能提升计算
        speedup = time_original / time_optimized
        print(f"\n=== 性能对比结果 ===")
        print(f"原版本时间: {time_original:.2f} 秒")
        print(f"优化版本时间: {time_optimized:.2f} 秒")
        print(f"性能提升: {speedup:.1f}x")
        print(f"时间节省: {((time_original - time_optimized) / time_original * 100):.1f}%")
        
    except ImportError:
        print("无法导入原版本进行对比")
    except Exception as e:
        print(f"原版本测试失败: {e}")

# 示例使用方法
if __name__ == "__main__":
    # 示例1: 优化版本多栅格导出
    raster_files = [
        r"D:\WebGIS\洪涝灾害影响评估\webgis-project\backend\data\金堂县DEM.tif",
        r"D:\WebGIS\洪涝灾害影响评估\webgis-project\backend\data\people.tif"
    ]
    
    # 检查文件是否存在
    existing_files = [f for f in raster_files if os.path.exists(f)]
    
    if len(existing_files) >= 2:
        print("开始性能对比测试...")
        compare_performance(existing_files[:2])
    else:
        print("测试文件不足，跳过性能对比")
        print("可用的优化功能:")
        print("- 使用Numba JIT编译加速坐标计算")
        print("- 向量化操作替代逐像素循环")
        print("- 批量坐标转换")
        print("- 优化的内存使用")
        print("- 预期性能提升: 5-20倍")