import rasterio
import numpy as np
import os
from rasterio.warp import reproject, Resampling
from rasterio.transform import from_bounds

def calculate_masked_ratio(mask_raster_path, target_raster_path, output_stats=True):
    """
    使用第一个栅格的非0非nodata区域作为掩膜，计算第二个栅格掩膜后的有效像元比例
    
    参数:
    mask_raster_path: 用作掩膜的栅格文件路径（第一个栅格）
    target_raster_path: 目标栅格文件路径（第二个栅格）
    output_stats: 是否输出详细统计信息
    
    返回:
    dict: 包含统计结果的字典
    """
    
    try:
        print(f"开始处理掩膜栅格: {mask_raster_path}")
        print(f"目标栅格: {target_raster_path}")
        
        # 读取掩膜栅格
        with rasterio.open(mask_raster_path) as mask_src:
            mask_data = mask_src.read(1)
            mask_transform = mask_src.transform
            mask_crs = mask_src.crs
            mask_nodata = mask_src.nodata
            mask_bounds = mask_src.bounds
            mask_shape = mask_data.shape
            
        print(f"掩膜栅格信息:")
        print(f"  尺寸: {mask_shape}")
        print(f"  坐标系: {mask_crs}")
        print(f"  nodata值: {mask_nodata}")
        print(f"  数据范围: [{np.nanmin(mask_data):.3f}, {np.nanmax(mask_data):.3f}]")
        
        # 读取目标栅格
        with rasterio.open(target_raster_path) as target_src:
            target_data = target_src.read(1)
            target_transform = target_src.transform
            target_crs = target_src.crs
            target_nodata = target_src.nodata
            target_bounds = target_src.bounds
            target_shape = target_data.shape
            
        print(f"\n目标栅格信息:")
        print(f"  尺寸: {target_shape}")
        print(f"  坐标系: {target_crs}")
        print(f"  nodata值: {target_nodata}")
        print(f"  数据范围: [{np.nanmin(target_data):.3f}, {np.nanmax(target_data):.3f}]")
        
        # 检查坐标系是否一致
        if mask_crs != target_crs:
            print(f"\n警告: 两个栅格的坐标系不一致")
            print(f"掩膜栅格坐标系: {mask_crs}")
            print(f"目标栅格坐标系: {target_crs}")
            print("将目标栅格重投影到掩膜栅格的坐标系")
            
            # 重投影目标栅格到掩膜栅格的坐标系
            height, width = mask_shape
            
            # 创建目标数组
            target_reprojected = np.empty((height, width), dtype=target_data.dtype)
            
            # 重投影
            reproject(
                source=target_data,
                destination=target_reprojected,
                src_transform=target_transform,
                src_crs=target_crs,
                dst_transform=mask_transform,
                dst_crs=mask_crs,
                resampling=Resampling.nearest
            )
            
            target_data = target_reprojected
            target_transform = mask_transform
            target_crs = mask_crs
            
        # 如果栅格尺寸不一致，需要对齐
        elif mask_shape != target_shape:
            print(f"\n警告: 两个栅格尺寸不一致")
            print(f"掩膜栅格尺寸: {mask_shape}")
            print(f"目标栅格尺寸: {target_shape}")
            print("将目标栅格重采样到掩膜栅格的尺寸")
            
            height, width = mask_shape
            
            # 创建目标数组
            target_resampled = np.empty((height, width), dtype=target_data.dtype)
            
            # 重采样
            reproject(
                source=target_data,
                destination=target_resampled,
                src_transform=target_transform,
                src_crs=target_crs,
                dst_transform=mask_transform,
                dst_crs=mask_crs,
                resampling=Resampling.nearest
            )
            
            target_data = target_resampled
            
        print(f"\n--- 开始掩膜分析 ---")
        
        # 创建掩膜：第一个栅格的非0非nodata区域
        mask_valid = np.ones_like(mask_data, dtype=bool)
        
        # 排除nodata值
        if mask_nodata is not None:
            try:
                if isinstance(mask_nodata, (int, float)):
                    mask_valid &= ~np.isclose(mask_data, mask_nodata)
            except (TypeError, ValueError):
                pass
                
        # 排除NaN值
        mask_valid &= ~np.isnan(mask_data)
        
        # 排除0值
        mask_valid &= (mask_data != 0)
        
        print(f"掩膜区域统计:")
        total_pixels = mask_data.size
        mask_pixels = np.sum(mask_valid)
        mask_ratio = mask_pixels / total_pixels
        print(f"  总像元数: {total_pixels}")
        print(f"  掩膜区域像元数: {mask_pixels}")
        print(f"  掩膜区域比例: {mask_ratio:.4f} ({mask_ratio*100:.2f}%)")
        
        # 应用掩膜到目标栅格
        # 确保目标数组是浮点类型以支持NaN值
        if target_data.dtype.kind in ['i', 'u']:  # 整数类型
            target_masked = target_data.astype(np.float64)
        else:
            target_masked = target_data.copy()
        target_masked[~mask_valid] = np.nan
        
        # 计算目标栅格在掩膜区域内的有效像元
        target_valid_in_mask = np.ones_like(target_data, dtype=bool)
        
        # 排除目标栅格的nodata值
        if target_nodata is not None:
            try:
                if isinstance(target_nodata, (int, float)):
                    target_valid_in_mask &= ~np.isclose(target_data, target_nodata)
            except (TypeError, ValueError):
                pass
                
        # 排除目标栅格的NaN值
        target_valid_in_mask &= ~np.isnan(target_data)
        
        # 只考虑掩膜区域内的像元
        target_valid_in_mask &= mask_valid
        
        print(f"\n目标栅格在掩膜区域内的统计:")
        valid_pixels_in_mask = np.sum(target_valid_in_mask)
        valid_ratio_in_mask = valid_pixels_in_mask / mask_pixels if mask_pixels > 0 else 0
        valid_ratio_total = valid_pixels_in_mask / total_pixels
        
        print(f"  掩膜区域内有效像元数: {valid_pixels_in_mask}")
        print(f"  掩膜区域内有效像元比例: {valid_ratio_in_mask:.4f} ({valid_ratio_in_mask*100:.2f}%)")
        print(f"  相对于总像元的比例: {valid_ratio_total:.4f} ({valid_ratio_total*100:.2f}%)")
        
        # 计算掩膜后目标栅格的统计信息
        if valid_pixels_in_mask > 0:
            valid_values = target_data[target_valid_in_mask]
            print(f"\n掩膜后目标栅格数值统计:")
            print(f"  最小值: {np.min(valid_values):.6f}")
            print(f"  最大值: {np.max(valid_values):.6f}")
            print(f"  均值: {np.mean(valid_values):.6f}")
            print(f"  中位数: {np.median(valid_values):.6f}")
            print(f"  标准差: {np.std(valid_values):.6f}")
        else:
            print(f"\n掩膜后目标栅格无有效数据")
            
        # 返回统计结果
        result = {
            'total_pixels': int(total_pixels),
            'mask_pixels': int(mask_pixels),
            'mask_ratio': float(mask_ratio),
            'valid_pixels_in_mask': int(valid_pixels_in_mask),
            'valid_ratio_in_mask': float(valid_ratio_in_mask),
            'valid_ratio_total': float(valid_ratio_total),
            'mask_raster_path': mask_raster_path,
            'target_raster_path': target_raster_path
        }
        
        if valid_pixels_in_mask > 0:
            valid_values = target_data[target_valid_in_mask]
            result.update({
                'min_value': float(np.min(valid_values)),
                'max_value': float(np.max(valid_values)),
                'mean_value': float(np.mean(valid_values)),
                'median_value': float(np.median(valid_values)),
                'std_value': float(np.std(valid_values))
            })
        
        return result
        
    except Exception as e:
        print(f"处理过程中发生错误: {str(e)}")
        raise

def save_masked_raster(mask_raster_path, target_raster_path, output_path):
    """
    保存掩膜后的栅格文件
    
    参数:
    mask_raster_path: 用作掩膜的栅格文件路径
    target_raster_path: 目标栅格文件路径
    output_path: 输出栅格文件路径
    
    返回:
    str: 输出文件路径
    """
    
    try:
        # 读取掩膜栅格
        with rasterio.open(mask_raster_path) as mask_src:
            mask_data = mask_src.read(1)
            mask_transform = mask_src.transform
            mask_crs = mask_src.crs
            mask_nodata = mask_src.nodata
            
        # 读取目标栅格
        with rasterio.open(target_raster_path) as target_src:
            target_data = target_src.read(1)
            target_transform = target_src.transform
            target_crs = target_src.crs
            target_nodata = target_src.nodata
            target_profile = target_src.profile
            
        # 对齐栅格（如果需要）
        if mask_crs != target_crs or mask_data.shape != target_data.shape:
            height, width = mask_data.shape
            target_aligned = np.empty((height, width), dtype=target_data.dtype)
            
            reproject(
                source=target_data,
                destination=target_aligned,
                src_transform=target_transform,
                src_crs=target_crs,
                dst_transform=mask_transform,
                dst_crs=mask_crs,
                resampling=Resampling.nearest
            )
            
            target_data = target_aligned
            target_transform = mask_transform
            target_crs = mask_crs
            
        # 创建掩膜
        mask_valid = np.ones_like(mask_data, dtype=bool)
        
        if mask_nodata is not None:
            try:
                if isinstance(mask_nodata, (int, float)):
                    mask_valid &= ~np.isclose(mask_data, mask_nodata)
            except (TypeError, ValueError):
                pass
                
        mask_valid &= ~np.isnan(mask_data)
        mask_valid &= (mask_data != 0)
        
        # 应用掩膜
        masked_data = target_data.copy()
        if target_nodata is not None:
            masked_data[~mask_valid] = target_nodata
        else:
            masked_data[~mask_valid] = -9999
            target_nodata = -9999
            
        # 更新profile
        target_profile.update({
            'height': masked_data.shape[0],
            'width': masked_data.shape[1],
            'transform': target_transform,
            'crs': target_crs,
            'nodata': target_nodata
        })
        
        # 确保输出目录存在
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # 保存掩膜后的栅格
        with rasterio.open(output_path, 'w', **target_profile) as dst:
            dst.write(masked_data, 1)
            
        print(f"掩膜后的栅格已保存: {output_path}")
        return output_path
        
    except Exception as e:
        print(f"保存掩膜栅格时发生错误: {str(e)}")
        raise

def batch_calculate_ratios(mask_raster_path, target_raster_dir, output_csv_path=None):
    """
    批量计算多个目标栅格的掩膜比例
    
    参数:
    mask_raster_path: 用作掩膜的栅格文件路径
    target_raster_dir: 目标栅格文件目录
    output_csv_path: 输出CSV文件路径（可选）
    
    返回:
    list: 包含所有结果的列表
    """
    
    import pandas as pd
    
    results = []
    
    # 获取目标目录中的所有tif文件
    tif_files = [f for f in os.listdir(target_raster_dir) if f.lower().endswith('.tif')]
    
    print(f"找到 {len(tif_files)} 个TIF文件")
    
    for tif_file in tif_files:
        target_path = os.path.join(target_raster_dir, tif_file)
        print(f"\n处理文件: {tif_file}")
        
        try:
            result = calculate_masked_ratio(mask_raster_path, target_path, output_stats=False)
            result['target_filename'] = tif_file
            results.append(result)
            
            print(f"  掩膜区域有效像元比例: {result['valid_ratio_in_mask']:.4f} ({result['valid_ratio_in_mask']*100:.2f}%)")
            
        except Exception as e:
            print(f"  处理失败: {str(e)}")
            
    # 保存结果到CSV
    if output_csv_path and results:
        df = pd.DataFrame(results)
        df.to_csv(output_csv_path, index=False, encoding='utf-8')
        print(f"\n批量处理结果已保存到: {output_csv_path}")
        
    return results

# 示例使用方法
if __name__ == "__main__":
    # 示例1: 计算单个栅格的掩膜比例
    # result = calculate_masked_ratio(
    #     r"D:\WebGIS\洪涝灾害影响评估\webgis-project\backend\data\flood_results\b_exposure_20250621_130507_76a0a80a.tif",
    #     # r"D:\WebGIS\洪涝灾害影响评估\webgis-project\backend\data\hec_ras.tif"
    #     r"D:\WebGIS\洪涝灾害影响评估\webgis-project\backend\data\Flood_Classification_20180711.tif"
    # )
    # print(f"掩膜区域有效像元比例: {result['valid_ratio_in_mask']:.4f}")
    
    # 示例2: 保存掩膜后的栅格
    # save_masked_raster(
    #     "path/to/mask_raster.tif",
    #     "path/to/target_raster.tif",
    #     "path/to/output_masked.tif"
    # )
    
    # 示例3: 批量处理
    batch_results = batch_calculate_ratios(
        r"D:\WebGIS\洪涝灾害影响评估\webgis-project\backend\data\flood_results\b_exposure_20250621_130507_76a0a80a.tif",
        r"D:\WebGIS\洪涝灾害影响评估\webgis-project\backend\data\compare_data",
        "./batch_results.csv"
    )
    
    print("栅格掩膜比例计算工具已准备就绪")
    print("使用 calculate_masked_ratio() 计算单个栅格的掩膜比例")
    print("使用 save_masked_raster() 保存掩膜后的栅格")
    print("使用 batch_calculate_ratios() 批量处理多个栅格")