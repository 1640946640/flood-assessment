#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DEM数据分析工具
用于分析金堂县DEM数据的基本信息、数据范围、坐标系统等
"""

import os
import numpy as np
import matplotlib.pyplot as plt
from osgeo import gdal, osr
import geopandas as gpd
from matplotlib.colors import LinearSegmentedColormap
import seaborn as sns

# 设置matplotlib中文字体
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False

def analyze_dem_data(dem_path):
    """
    分析DEM数据的基本信息
    """
    print("="*80)
    print("🗺️  DEM数据分析报告")
    print("="*80)
    
    # 检查文件是否存在
    if not os.path.exists(dem_path):
        print(f"❌ 文件不存在: {dem_path}")
        return None
    
    print(f"📁 文件路径: {dem_path}")
    print(f"📏 文件大小: {os.path.getsize(dem_path) / (1024*1024):.2f} MB")
    
    # 打开DEM数据集
    dataset = gdal.Open(dem_path)
    if dataset is None:
        print("❌ 无法打开DEM文件")
        return None
    
    # 获取基本信息
    band = dataset.GetRasterBand(1)
    data = band.ReadAsArray()
    nodata = band.GetNoDataValue()
    geotransform = dataset.GetGeoTransform()
    projection = dataset.GetProjection()
    
    print(f"\n📊 基本信息:")
    print(f"   数据维度: {data.shape[0]} x {data.shape[1]} 像素")
    print(f"   数据类型: {data.dtype}")
    print(f"   NoData值: {nodata}")
    
    # 分析坐标系统
    print(f"\n🗺️  坐标系统信息:")
    print(f"   投影信息: {projection[:100]}...")
    
    srs = osr.SpatialReference()
    srs.ImportFromWkt(projection)
    
    if srs.IsGeographic():
        print(f"   ✅ 地理坐标系")
        coord_type = "地理坐标系"
    elif srs.IsProjected():
        print(f"   ✅ 投影坐标系")
        coord_type = "投影坐标系"
    else:
        print(f"   ❓ 未知坐标系")
        coord_type = "未知坐标系"
    
    # 获取坐标范围
    rows, cols = data.shape
    x_min = geotransform[0]
    y_max = geotransform[3]
    x_max = geotransform[0] + cols * geotransform[1]
    y_min = geotransform[3] + rows * geotransform[5]
    
    print(f"\n📍 地理范围:")
    print(f"   左上角: ({x_min:.6f}, {y_max:.6f})")
    print(f"   右下角: ({x_max:.6f}, {y_min:.6f})")
    print(f"   像素大小: ({geotransform[1]:.6f}, {geotransform[5]:.6f})")
    
    # 分析数据统计
    valid_mask = data != nodata if nodata is not None else np.ones_like(data, dtype=bool)
    valid_data = data[valid_mask]
    
    print(f"\n📈 数据统计:")
    print(f"   有效像素数: {np.sum(valid_mask)}")
    print(f"   无效像素数: {np.sum(~valid_mask)}")
    print(f"   数据范围: [{np.min(valid_data):.2f}, {np.max(valid_data):.2f}]")
    print(f"   平均值: {np.mean(valid_data):.2f}")
    print(f"   标准差: {np.std(valid_data):.2f}")
    print(f"   中位数: {np.median(valid_data):.2f}")
    
    # 分位数分析
    percentiles = [1, 5, 10, 25, 50, 75, 90, 95, 99]
    print(f"\n📊 分位数分析:")
    for p in percentiles:
        value = np.percentile(valid_data, p)
        print(f"   {p}%分位数: {value:.2f}")
    
    # 高程分布分析
    print(f"\n🏔️  高程分布分析:")
    elevation_ranges = [
        (0, 100, "平原"),
        (100, 300, "丘陵"),
        (300, 500, "低山"),
        (500, 1000, "中山"),
        (1000, float('inf'), "高山")
    ]
    
    for min_elev, max_elev, terrain_type in elevation_ranges:
        if max_elev == float('inf'):
            count = np.sum((valid_data >= min_elev))
        else:
            count = np.sum((valid_data >= min_elev) & (valid_data < max_elev))
        percentage = count / len(valid_data) * 100
        print(f"   {terrain_type} ({min_elev}-{max_elev if max_elev != float('inf') else '∞'}m): {count} 像素 ({percentage:.1f}%)")
    
    # 创建可视化图表
    create_dem_visualizations(data, valid_mask, nodata, dem_path)
    
    return {
        'data': data,
        'valid_mask': valid_mask,
        'nodata': nodata,
        'geotransform': geotransform,
        'projection': projection,
        'coord_type': coord_type,
        'stats': {
            'min': float(np.min(valid_data)),
            'max': float(np.max(valid_data)),
            'mean': float(np.mean(valid_data)),
            'std': float(np.std(valid_data)),
            'median': float(np.median(valid_data))
        }
    }

def create_dem_visualizations(data, valid_mask, nodata, dem_path):
    """
    创建DEM数据的可视化图表
    """
    print(f"\n🎨 生成可视化图表...")
    
    # 创建输出目录
    output_dir = os.path.join(os.path.dirname(dem_path), "dem_analysis")
    os.makedirs(output_dir, exist_ok=True)
    
    # 1. 高程分布直方图
    valid_data = data[valid_mask]
    
    plt.figure(figsize=(15, 10))
    
    # 子图1: 高程分布直方图
    plt.subplot(2, 3, 1)
    plt.hist(valid_data, bins=50, alpha=0.7, color='skyblue', edgecolor='black')
    plt.title('高程分布直方图')
    plt.xlabel('高程 (m)')
    plt.ylabel('像素数量')
    plt.grid(True, alpha=0.3)
    
    # 子图2: 高程分布箱线图
    plt.subplot(2, 3, 2)
    plt.boxplot(valid_data, vert=True)
    plt.title('高程分布箱线图')
    plt.ylabel('高程 (m)')
    plt.grid(True, alpha=0.3)
    
    # 子图3: 高程热力图（采样显示）
    plt.subplot(2, 3, 3)
    # 采样显示，避免图像过大
    sample_size = min(1000, len(valid_data))
    sample_indices = np.random.choice(len(valid_data), sample_size, replace=False)
    sample_data = valid_data[sample_indices]
    
    plt.scatter(range(len(sample_data)), sample_data, c=sample_data, cmap='terrain', alpha=0.6)
    plt.colorbar(label='高程 (m)')
    plt.title('高程采样散点图')
    plt.xlabel('采样点')
    plt.ylabel('高程 (m)')
    plt.grid(True, alpha=0.3)
    
    # 子图4: 高程密度图
    plt.subplot(2, 3, 4)
    sns.kdeplot(valid_data, fill=True, color='green', alpha=0.6)
    plt.title('高程密度分布')
    plt.xlabel('高程 (m)')
    plt.ylabel('密度')
    plt.grid(True, alpha=0.3)
    
    # 子图5: 高程累积分布
    plt.subplot(2, 3, 5)
    sorted_data = np.sort(valid_data)
    cumulative = np.arange(1, len(sorted_data) + 1) / len(sorted_data)
    plt.plot(sorted_data, cumulative, color='red', linewidth=2)
    plt.title('高程累积分布')
    plt.xlabel('高程 (m)')
    plt.ylabel('累积概率')
    plt.grid(True, alpha=0.3)
    
    # 子图6: 统计信息表格
    plt.subplot(2, 3, 6)
    plt.axis('off')
    
    stats_text = f"""
数据统计信息:

最小值: {np.min(valid_data):.2f} m
最大值: {np.max(valid_data):.2f} m
平均值: {np.mean(valid_data):.2f} m
中位数: {np.median(valid_data):.2f} m
标准差: {np.std(valid_data):.2f} m

数据范围: {np.max(valid_data) - np.min(valid_data):.2f} m
有效像素: {np.sum(valid_mask):,}
总像素: {data.size:,}
有效率: {np.sum(valid_mask)/data.size*100:.1f}%
    """
    
    plt.text(0.05, 0.95, stats_text, transform=plt.gca().transAxes, 
             fontsize=11, verticalalignment='top', fontfamily='monospace',
             bbox=dict(boxstyle="round,pad=0.5", facecolor="lightgray", alpha=0.9, edgecolor='black'))
    
    plt.tight_layout()
    stats_plot_path = os.path.join(output_dir, "dem_statistics.png")
    plt.savefig(stats_plot_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"   ✅ 统计图表已保存: {stats_plot_path}")
    
    # 2. DEM高程图
    plt.figure(figsize=(12, 8))
    
    # 创建显示数据
    display_data = np.full_like(data, np.nan, dtype=float)
    display_data[valid_mask] = data[valid_mask]
    
    # 创建高程色彩映射
    elevation_cmap = LinearSegmentedColormap.from_list('elevation', [
        '#000080', '#0000FF', '#0080FF', '#00FFFF', '#00FF80', 
        '#80FF00', '#FFFF00', '#FF8000', '#FF0000', '#800000'
    ], N=256)
    
    im = plt.imshow(display_data, cmap=elevation_cmap, alpha=0.8)
    plt.colorbar(im, label='高程 (m)')
    plt.title('DEM高程分布图')
    plt.axis('off')
    
    # 添加统计信息
    stats_text = f"高程范围: {np.min(valid_data):.0f} - {np.max(valid_data):.0f} m"
    plt.text(0.02, 0.98, stats_text, transform=plt.gca().transAxes, 
             fontsize=12, verticalalignment='top',
             bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8))
    
    plt.tight_layout()
    elevation_plot_path = os.path.join(output_dir, "dem_elevation.png")
    plt.savefig(elevation_plot_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"   ✅ 高程图已保存: {elevation_plot_path}")
    
    # 3. 高程分类图
    plt.figure(figsize=(12, 8))
    
    # 定义高程分类
    elevation_classes = [
        (0, 100, "平原", '#90EE90'),
        (100, 300, "丘陵", '#32CD32'),
        (300, 500, "低山", '#FFD700'),
        (500, 1000, "中山", '#FF8C00'),
        (1000, float('inf'), "高山", '#8B0000')
    ]
    
    classified_data = np.full_like(data, np.nan, dtype=float)
    colors = []
    
    for i, (min_elev, max_elev, terrain_type, color) in enumerate(elevation_classes):
        if max_elev == float('inf'):
            mask = (data >= min_elev) & valid_mask
        else:
            mask = (data >= min_elev) & (data < max_elev) & valid_mask
        
        classified_data[mask] = i
        colors.append(color)
    
    # 创建分类色彩映射
    classified_cmap = LinearSegmentedColormap.from_list('classified', colors, N=len(colors))
    
    im = plt.imshow(classified_data, cmap=classified_cmap, alpha=0.8)
    
    # 创建自定义颜色条标签
    terrain_labels = [terrain_type for _, _, terrain_type, _ in elevation_classes]
    cbar = plt.colorbar(im, ticks=range(len(terrain_labels)))
    cbar.set_ticklabels(terrain_labels)
    cbar.set_label('地形类型')
    
    plt.title('DEM地形分类图')
    plt.axis('off')
    
    plt.tight_layout()
    classified_plot_path = os.path.join(output_dir, "dem_classified.png")
    plt.savefig(classified_plot_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"   ✅ 分类图已保存: {classified_plot_path}")

def analyze_with_water_level(dem_path, water_level=446.55):
    """
    分析DEM与指定水位的关系
    """
    print(f"\n" + "="*80)
    print(f"💧  DEM与水位关系分析 (水位: {water_level}m)")
    print("="*80)
    
    # 读取DEM数据
    dataset = gdal.Open(dem_path)
    if dataset is None:
        print("❌ 无法打开DEM文件")
        return
    
    band = dataset.GetRasterBand(1)
    data = band.ReadAsArray()
    nodata = band.GetNoDataValue()
    valid_mask = data != nodata if nodata is not None else np.ones_like(data, dtype=bool)
    valid_data = data[valid_mask]
    
    # 计算水深
    water_depth = water_level - valid_data
    
    print(f"📊 水位分析:")
    print(f"   指定水位: {water_level:.2f}m")
    print(f"   DEM范围: [{np.min(valid_data):.2f}, {np.max(valid_data):.2f}]m")
    print(f"   水深范围: [{np.min(water_depth):.2f}, {np.max(water_depth):.2f}]m")
    
    # 淹没分析
    flooded_mask = water_depth > 0
    flooded_data = water_depth[flooded_mask]
    non_flooded_data = water_depth[~flooded_mask]
    
    print(f"\n🌊 淹没分析:")
    print(f"   淹没像素数: {np.sum(flooded_mask)}")
    print(f"   非淹没像素数: {np.sum(~flooded_mask)}")
    print(f"   淹没比例: {np.sum(flooded_mask)/len(water_depth)*100:.2f}%")
    
    if len(flooded_data) > 0:
        print(f"   淹没区域水深范围: [{np.min(flooded_data):.2f}, {np.max(flooded_data):.2f}]m")
        print(f"   平均淹没水深: {np.mean(flooded_data):.2f}m")
        print(f"   最大淹没水深: {np.max(flooded_data):.2f}m")
    
    # 创建水位分析图
    plt.figure(figsize=(15, 10))
    
    # 子图1: 水深分布
    plt.subplot(2, 3, 1)
    plt.hist(water_depth, bins=50, alpha=0.7, color='lightblue', edgecolor='black')
    plt.axvline(x=0, color='red', linestyle='--', label='水位线')
    plt.title('水深分布直方图')
    plt.xlabel('水深 (m)')
    plt.ylabel('像素数量')
    plt.legend()
    plt.grid(True, alpha=0.3)
    
    # 子图2: 淹没/非淹没比例
    plt.subplot(2, 3, 2)
    labels = ['淹没区域', '非淹没区域']
    sizes = [np.sum(flooded_mask), np.sum(~flooded_mask)]
    colors = ['lightcoral', 'lightgreen']
    plt.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', startangle=90)
    plt.title('淹没区域比例')
    
    # 子图3: 淹没水深分布
    if len(flooded_data) > 0:
        plt.subplot(2, 3, 3)
        plt.hist(flooded_data, bins=30, alpha=0.7, color='coral', edgecolor='black')
        plt.title('淹没区域水深分布')
        plt.xlabel('水深 (m)')
        plt.ylabel('像素数量')
        plt.grid(True, alpha=0.3)
    
    # 子图4: 高程vs水深散点图
    plt.subplot(2, 3, 4)
    sample_size = min(5000, len(valid_data))
    sample_indices = np.random.choice(len(valid_data), sample_size, replace=False)
    sample_elevation = valid_data[sample_indices]
    sample_depth = water_depth[sample_indices]
    
    plt.scatter(sample_elevation, sample_depth, alpha=0.6, s=1)
    plt.axhline(y=0, color='red', linestyle='--', label='水位线')
    plt.title('高程 vs 水深')
    plt.xlabel('高程 (m)')
    plt.ylabel('水深 (m)')
    plt.legend()
    plt.grid(True, alpha=0.3)
    
    # 子图5: 淹没区域统计
    plt.subplot(2, 3, 5)
    plt.axis('off')
    
    # 创建更清晰的统计信息显示
    stats_text = f"""
水位分析统计:

指定水位: {water_level:.2f} m
DEM范围: {np.min(valid_data):.2f} - {np.max(valid_data):.2f} m
水深范围: {np.min(water_depth):.2f} - {np.max(water_depth):.2f} m

淹没区域:
- 像素数: {np.sum(flooded_mask):,}
- 比例: {np.sum(flooded_mask)/len(water_depth)*100:.1f}%
- 平均水深: {np.mean(flooded_data) if len(flooded_data) > 0 else 0:.2f} m
- 最大水深: {np.max(flooded_data) if len(flooded_data) > 0 else 0:.2f} m

非淹没区域:
- 像素数: {np.sum(~flooded_mask):,}
- 比例: {np.sum(~flooded_mask)/len(water_depth)*100:.1f}%
    """
    
    # 使用更大的字体和更好的布局
    plt.text(0.05, 0.95, stats_text, transform=plt.gca().transAxes, 
             fontsize=11, verticalalignment='top', fontfamily='monospace',
             bbox=dict(boxstyle="round,pad=0.5", facecolor="lightblue", alpha=0.9, edgecolor='black'))
    
    # 子图6: 水深分类
    plt.subplot(2, 3, 6)
    
    depth_classes = [
        (float('-inf'), 0, "非淹没", 'lightgreen'),
        (0, 1, "浅水", 'lightblue'),
        (1, 3, "中水", 'blue'),
        (3, 5, "深水", 'darkblue'),
        (5, float('inf'), "极深水", 'navy')
    ]
    
    depth_counts = []
    depth_labels = []
    depth_colors = []
    
    for min_depth, max_depth, label, color in depth_classes:
        if max_depth == float('inf'):
            count = np.sum((water_depth >= min_depth))
        else:
            count = np.sum((water_depth >= min_depth) & (water_depth < max_depth))
        depth_counts.append(count)
        depth_labels.append(label)
        depth_colors.append(color)
    
    plt.bar(depth_labels, depth_counts, color=depth_colors, alpha=0.7)
    plt.title('水深分类统计')
    plt.ylabel('像素数量')
    plt.xticks(rotation=45)
    
    plt.tight_layout()
    
    # 保存水位分析图
    output_dir = os.path.join(os.path.dirname(dem_path), "dem_analysis")
    os.makedirs(output_dir, exist_ok=True)
    water_analysis_path = os.path.join(output_dir, f"water_level_analysis_{water_level}m.png")
    plt.savefig(water_analysis_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"   ✅ 水位分析图已保存: {water_analysis_path}")

def main():
    """
    主函数
    """
    # DEM文件路径
    dem_path = r"C:\Users\16409\Desktop\接单\洪涝灾害评估软件\backend\data\new_data\输入数据集TIF2020\20X20zhaozhen_template_20m.tif"
    
    print("🚀 开始DEM数据分析...")
    
    # 分析DEM数据
    dem_info = analyze_dem_data(dem_path)
    
    if dem_info is not None:
        # 分析不同水位的情况
        water_levels = [446.55, 449.14, 450.0, 460.0, 500.0]
        
        for water_level in water_levels:
            analyze_with_water_level(dem_path, water_level)
        
        print(f"\n✅ DEM数据分析完成！")
        print(f"📁 分析结果保存在: {os.path.join(os.path.dirname(dem_path), 'dem_analysis')}")
        
        # 输出关键信息
        print(f"\n🔍 关键发现:")
        print(f"   DEM高程范围: {dem_info['stats']['min']:.2f} - {dem_info['stats']['max']:.2f} m")
        print(f"   DEM平均值: {dem_info['stats']['mean']:.2f} m")
        print(f"   坐标系统: {dem_info['coord_type']}")
        
        # 针对你的水位446.55m的分析
        water_level = 446.55
        valid_data = dem_info['data'][dem_info['valid_mask']]
        water_depth = water_level - valid_data
        
        flooded_pixels = np.sum(water_depth > 0)
        total_pixels = len(water_depth)
        flood_ratio = flooded_pixels / total_pixels * 100
        
        print(f"\n💧 针对水位 {water_level}m 的分析:")
        print(f"   淹没像素数: {flooded_pixels:,}")
        print(f"   总像素数: {total_pixels:,}")
        print(f"   淹没比例: {flood_ratio:.2f}%")
        
        if flooded_pixels > 0:
            flooded_depth = water_depth[water_depth > 0]
            print(f"   淹没区域水深范围: {np.min(flooded_depth):.2f} - {np.max(flooded_depth):.2f} m")
            print(f"   平均淹没水深: {np.mean(flooded_depth):.2f} m")
        else:
            print(f"   ⚠️  当前水位下无淹没区域！")

if __name__ == "__main__":
    main() 