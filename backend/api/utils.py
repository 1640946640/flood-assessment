import os
import json
import numpy as np
from datetime import datetime
import geopandas as gpd
import matplotlib.pyplot as plt

def ensure_directory_exists(directory):
    """
    确保目录存在，如果不存在则创建
    
    参数:
        directory (str): 目录路径
    """
    if not os.path.exists(directory):
        os.makedirs(directory)

def json_serial(obj):
    """
    JSON序列化函数，处理不可序列化的对象
    
    参数:
        obj: 需要序列化的对象
    
    返回:
        可序列化的对象
    """
    if isinstance(obj, (np.ndarray, np.number)):
        return obj.tolist()
    elif isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")

def save_json(data, file_path):
    """
    保存数据为JSON文件
    
    参数:
        data: 要保存的数据
        file_path (str): 文件路径
    """
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, default=json_serial, ensure_ascii=False, indent=2)

def load_json(file_path):
    """
    从JSON文件加载数据
    
    参数:
        file_path (str): 文件路径
    
    返回:
        加载的数据
    """
    if not os.path.exists(file_path):
        return None
    
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def get_dataset_path(dataset_id):
    """
    获取数据集文件路径
    
    参数:
        dataset_id (str): 数据集ID
    
    返回:
        str: 数据集文件路径，如果不存在返回None
    """
    # 数据集元数据文件路径
    metadata_file = os.path.join('data', 'datasets', f'{dataset_id}.json')
    
    # 读取元数据
    metadata = load_json(metadata_file)
    if not metadata:
        return None
    
    # 获取数据文件路径
    file_path = os.path.join('data', 'datasets', metadata.get('file_name', ''))
    
    return file_path if os.path.exists(file_path) else None

def save_vector_dataset(gdf, filename):
    """
    保存矢量数据集
    
    参数:
        gdf (GeoDataFrame): 要保存的GeoDataFrame
        filename (str): 文件名
    
    返回:
        str: 保存的文件路径
    """
    # 确保结果目录存在
    results_dir = os.path.join('data', 'analysis_results')
    ensure_directory_exists(results_dir)
    
    # 构建文件路径
    file_path = os.path.join(results_dir, filename)
    
    # 保存为GeoJSON
    gdf.to_file(file_path, driver='GeoJSON')
    
    return file_path

# 添加常用函数
def add_admin_boundary_to_plot(ax, data_dir, projection, boundary_path='行政边界/金堂县_行政边界.shp', 
                               color='red', linewidth=3.0, zorder=100, data_extent=None, data_convex_hull=None):
    """
    在matplotlib图形上添加行政边界（智能选择主体区域）
    
    参数:
        ax: matplotlib轴对象，用于绘制行政边界
        data_dir: 数据目录路径
        projection: 目标坐标系
        boundary_path: 行政边界文件路径（相对于data_dir）
        color: 边界线颜色
        linewidth: 边界线宽度
        zorder: 边界线的叠放顺序（越大越靠上）
        data_extent: 有效数据范围 [minx, maxx, miny, maxy]，用于智能选择边界区域
        data_convex_hull: 数据点的凸包几何对象（如果提供，优先使用此几何形状进行边界匹配）
        
    返回:
        bool: 添加边界是否成功
    """
    try:
        import rasterio.crs
        
        # 读取行政边界shapefile
        admin_boundary_path = os.path.join(data_dir, boundary_path)
        if not os.path.exists(admin_boundary_path):
            print(f"行政边界文件不存在: {admin_boundary_path}")
            # 尝试其他可能的边界文件
            alternative_paths = [
                '行政边界/01金堂县_行政边界.shp',
                '行政边界SHP/金堂县_行政边界.shp',
                '行政边界/金堂县5乡镇.shp'
            ]
            for alt_path in alternative_paths:
                alt_full_path = os.path.join(data_dir, alt_path)
                if os.path.exists(alt_full_path):
                    admin_boundary_path = alt_full_path
                    boundary_path = alt_path
                    print(f"找到替代边界文件: {admin_boundary_path}")
                    break
            else:
                print("未找到任何可用的行政边界文件")
            return False
            
        print(f"正在加载行政边界: {admin_boundary_path}")
        admin_boundary = gpd.read_file(admin_boundary_path)
        print(f"边界数据加载成功，包含 {len(admin_boundary)} 个要素")
        print(f"边界数据坐标系: {admin_boundary.crs}")
        print(f"边界数据范围: {admin_boundary.total_bounds}")
        
        # 检查几何类型并处理多边形
        total_polygons = 0
        all_polygons = []  # 存储所有独立的polygon
        
        for idx, row in admin_boundary.iterrows():
            geom = row.geometry
            if geom.geom_type == 'Polygon':
                # 检查Polygon是否有多个环（可能包含内环/洞）
                exterior_ring = geom.exterior
                interior_rings = list(geom.interiors)
                
                print(f"发现Polygon - 面积: {geom.area:.2f}")
                print(f"  外环坐标点数: {len(exterior_ring.coords)}")
                print(f"  内环数量: {len(interior_rings)}")
                
                # 检查是否为复杂几何（可能实际包含分离区域）
                if len(interior_rings) > 0:
                    print(f"  警告：Polygon包含 {len(interior_rings)} 个内环，可能有复杂结构")
                
                total_polygons += 1
                all_polygons.append(geom)
                
            elif geom.geom_type == 'MultiPolygon':
                polygon_count = len(geom.geoms)
                total_polygons += polygon_count
                for i, poly in enumerate(geom.geoms):
                    all_polygons.append(poly)
                    print(f"发现MultiPolygon中的第{i+1}个子polygon，面积: {poly.area:.2f}")
                print(f"MultiPolygon包含 {polygon_count} 个子区域")
        
        print(f"总计发现 {total_polygons} 个独立多边形区域")
        
        # 暂时保存原始边界，稍后在坐标转换后进行智能过滤
        if len(all_polygons) > 0:
            # 先使用原始边界，稍后在坐标转换后进行处理
            print("暂时保存原始边界，将在坐标转换后进行智能过滤...")
        
        # 将GDAL投影字符串转换为rasterio CRS对象
        try:
            target_crs = rasterio.crs.CRS.from_wkt(projection)
            print(f"目标坐标系解析成功: {target_crs}")
        except Exception as parse_error:
            print(f"目标坐标系解析失败: {str(parse_error)}")
            print("尝试直接使用边界数据的原始坐标系")
            target_crs = admin_boundary.crs
        
        # 确保与栅格数据坐标系一致
        if admin_boundary.crs != target_crs:
            print(f"需要进行坐标系转换: {admin_boundary.crs} -> {target_crs}")
            try:
                admin_boundary_transformed = admin_boundary.to_crs(target_crs)
                print(f"坐标系转换成功")
                print(f"转换后边界范围: {admin_boundary_transformed.total_bounds}")
                admin_boundary = admin_boundary_transformed
            except Exception as crs_error:
                print(f"坐标系转换失败: {str(crs_error)}")
                print("使用原始坐标系绘制边界")
        else:
            print("坐标系匹配，无需转换")
        
        # 在坐标转换后进行智能边界过滤
        if (data_extent is not None or data_convex_hull is not None) and total_polygons >= 1:
            print("开始坐标转换后的智能边界过滤...")
            from shapely.geometry import box
            # 优先使用数据凸包，如果可用
            if data_convex_hull is not None:
                data_box = data_convex_hull
                print(f"✅ 使用数据凸包进行边界匹配")
                print(f"凸包范围: {data_box.bounds}")
            elif data_extent is not None:
                # data_extent格式: [minx, maxx, miny, maxy]  
                # box参数顺序: (minx, miny, maxx, maxy)
                data_box = box(data_extent[0], data_extent[2], data_extent[1], data_extent[3])
                print(f"使用矩形数据框进行边界匹配")
                print(f"数据范围: [minx={data_extent[0]:.1f}, maxx={data_extent[1]:.1f}, miny={data_extent[2]:.1f}, maxy={data_extent[3]:.1f}]")
            else:
                print("❌ 错误：既没有数据范围也没有凸包数据")
                return False
            
            print(f"用于匹配的数据几何体: {data_box.bounds}")
            
            # 重新提取转换后的所有polygon
            converted_polygons = []
            for idx, row in admin_boundary.iterrows():
                geom = row.geometry
                if geom.geom_type == 'Polygon':
                    converted_polygons.append(geom)
                elif geom.geom_type == 'MultiPolygon':
                    converted_polygons.extend(list(geom.geoms))
            
            print(f"转换后发现 {len(converted_polygons)} 个polygon区域")
            
            # 进行智能过滤
            best_geometry = None
            best_score = 0
            
            # 对于单一复杂Polygon，检查是否需要裁剪到数据区域
            if len(converted_polygons) == 1:
                single_poly = converted_polygons[0]
                print(f"单一复杂Polygon处理，面积: {single_poly.area:.2f}")
                try:
                    if single_poly.intersects(data_box):
                        print("✅ 边界与数据有重叠，进行裁剪...")
                        # 尝试不同的缓冲区大小，找到最佳匹配
                        best_intersection = None
                        best_buffer = None
                        
                        # 尝试更小的缓冲区大小: 100m, 200m, 300m
                        for buffer_size in [100, 200, 300]:
                            test_intersection = single_poly.intersection(data_box.buffer(buffer_size))
                            if test_intersection.is_valid and not test_intersection.is_empty:
                                # 计算数据覆盖率 (相交面积 / 数据区域面积)
                                coverage_ratio = test_intersection.intersection(data_box).area / data_box.area
                                print(f"缓冲区{buffer_size}m: 数据覆盖率={coverage_ratio:.3f}")
                                
                                # 选择覆盖率最高且合理的缓冲区
                                if coverage_ratio > 0.92:  # 至少覆盖92%的数据区域（实际可达标准）
                                    best_intersection = test_intersection
                                    best_buffer = buffer_size
                                    break
                        
                        # 如果没有找到合适的缓冲区，尝试更紧密的匹配
                        if best_intersection is None:
                            print("尝试紧密匹配策略...")
                            
                            # 策略1: 无缓冲区直接相交
                            tight_intersection = single_poly.intersection(data_box)
                            if tight_intersection.is_valid and not tight_intersection.is_empty:
                                coverage_tight = tight_intersection.intersection(data_box).area / data_box.area
                                print(f"无缓冲区匹配: 数据覆盖率={coverage_tight:.3f}")
                                
                                if coverage_tight > 0.92:  # 92%以上覆盖率（实际可达）
                                    best_intersection = tight_intersection
                                    best_buffer = 0
                                    print("✅ 使用高精度紧密匹配（无缓冲区）")
                                else:
                                    # 策略2: 创建数据点凸包并缓冲
                                    print("尝试基于数据点凸包的边界...")
                                    try:
                                        from shapely.geometry import MultiPoint
                                        # 创建数据框的角点
                                        corners = [
                                            (data_box.bounds[0], data_box.bounds[1]),  # min_x, min_y
                                            (data_box.bounds[2], data_box.bounds[1]),  # max_x, min_y
                                            (data_box.bounds[2], data_box.bounds[3]),  # max_x, max_y
                                            (data_box.bounds[0], data_box.bounds[3])   # min_x, max_y
                                        ]
                                        # 创建凸包并小幅缓冲
                                        data_convex = MultiPoint(corners).convex_hull.buffer(100)  # 100m缓冲，更精确
                                        convex_intersection = single_poly.intersection(data_convex)
                                        
                                        if convex_intersection.is_valid and not convex_intersection.is_empty:
                                            coverage_convex = convex_intersection.intersection(data_box).area / data_box.area
                                            print(f"凸包匹配: 数据覆盖率={coverage_convex:.3f}")
                                            
                                            if coverage_convex > 0.90:
                                                best_intersection = convex_intersection
                                                best_buffer = "凸包+100m"
                                                print("✅ 使用数据凸包匹配")
                                            else:
                                                # 最后回退
                                                best_intersection = tight_intersection
                                                best_buffer = 0
                                                print("⚠️ 回退到无缓冲区匹配")
                                        else:
                                            best_intersection = tight_intersection
                                            best_buffer = 0
                                            print("⚠️ 凸包计算失败，回退到无缓冲区")
                                    except Exception as convex_error:
                                        print(f"凸包计算出错: {str(convex_error)}")
                                        best_intersection = tight_intersection
                                        best_buffer = 0
                                        print("⚠️ 回退到无缓冲区匹配")
                            else:
                                # 最后回退到小缓冲区
                                best_intersection = single_poly.intersection(data_box.buffer(100))
                                best_buffer = 100
                                print(f"使用最小缓冲区: {best_buffer}m")
                        else:
                            print(f"✅ 选择最佳缓冲区: {best_buffer}m")
                        
                        intersection = best_intersection
                        if intersection.is_valid and not intersection.is_empty:
                            if intersection.geom_type == 'Polygon':
                                best_geometry = intersection
                                print(f"✅ 单一Polygon裁剪成功，面积从 {single_poly.area:.2f} 减少到 {intersection.area:.2f}")
                            elif intersection.geom_type == 'MultiPolygon':
                                # 选择最大的相交部分
                                largest_part = max(intersection.geoms, key=lambda x: x.area)
                                best_geometry = largest_part
                                print(f"✅ 选择最大相交部分，面积: {largest_part.area:.2f}")
                        else:
                            best_geometry = single_poly
                            print("⚠️ 裁剪结果无效，使用原始边界")
                    else:
                        best_geometry = single_poly
                        print("⚠️ 边界与数据无重叠，使用原始边界")
                except Exception as e:
                    print(f"⚠️ 边界裁剪失败: {str(e)}，使用原始边界")
                    best_geometry = single_poly
            
            # 对于多个polygon，选择最佳匹配
            elif len(converted_polygons) > 1:
                print("检测到多个polygon区域，智能选择主体区域...")
                
                for i, poly in enumerate(converted_polygons):
                    try:
                        # 计算与数据范围的重叠面积
                        if poly.intersects(data_box):
                            overlap_area = poly.intersection(data_box).area
                            # 综合考虑重叠面积和polygon本身的面积
                            score = overlap_area * 0.7 + poly.area * 0.3
                            if score > best_score:
                                best_score = score
                                best_geometry = poly
                                print(f"第{i+1}个区域: 重叠面积={overlap_area:.2f}, 总面积={poly.area:.2f}, 得分={score:.2f} ⭐")
                            else:
                                print(f"第{i+1}个区域: 重叠面积={overlap_area:.2f}, 总面积={poly.area:.2f}, 得分={score:.2f}")
                        else:
                            print(f"第{i+1}个区域: 与数据无重叠, 总面积={poly.area:.2f}")
                    except Exception as e:
                        print(f"计算第{i+1}个区域重叠时出错: {str(e)}")
                
                # 如果没有找到重叠区域，选择最大的
                if best_geometry is None:
                    print("未找到与数据重叠的区域，选择最大的区域...")
                    largest_area = 0
                    for i, poly in enumerate(converted_polygons):
                        if poly.area > largest_area:
                            largest_area = poly.area
                            best_geometry = poly
                    print(f"选择最大区域，面积: {largest_area:.2f}")
            
            # 更新admin_boundary为选定的几何体
            if best_geometry:
                import pandas as pd
                admin_boundary = gpd.GeoDataFrame([{'geometry': best_geometry}], crs=admin_boundary.crs)
                print("✅ 已设置最终绘制边界（坐标转换后过滤）")
            else:
                print("⚠️ 未找到合适的边界，使用原始边界")
        else:
            print("跳过智能过滤（无数据范围或无polygon）")
        
        # 在图像上绘制行政边界
        print(f"开始绘制边界，颜色: {color}, 线宽: {linewidth}, z-order: {zorder}")
        print(f"边界数据几何类型: {admin_boundary.geom_type.iloc[0] if len(admin_boundary) > 0 else 'None'}")
        
        # 使用单一最佳绘制方法，避免重复绘制
        drawing_success = False
        
        # 优先使用方法3：精确控制绘制
        try:
            print("尝试方法3: 智能手动绘制...")
            for idx, row in admin_boundary.iterrows():
                geom = row.geometry
                if geom.geom_type == 'Polygon':
                    # 只绘制外环，避免内环导致的复杂显示
                    x, y = geom.exterior.xy
                    ax.plot(x, y, color=color, linewidth=linewidth, zorder=zorder, alpha=1.0)
                    print(f"✅ 绘制Polygon外环，坐标点数: {len(x)}")
                elif geom.geom_type == 'MultiPolygon':
                    for i, poly in enumerate(geom.geoms):
                        x, y = poly.exterior.xy
                        ax.plot(x, y, color=color, linewidth=linewidth, zorder=zorder, alpha=1.0)
                        print(f"✅ 绘制MultiPolygon第{i+1}个子区域外环")
            drawing_success = True
            print("✅ 方法3绘制成功")
        except Exception as e3:
            print(f"❌ 方法3失败: {str(e3)}")
        
        # 如果方法3失败，尝试方法2
        if not drawing_success:
            try:
                print("尝试方法2: geopandas plot...")
                admin_boundary.plot(ax=ax, facecolor='none', edgecolor=color, linewidth=linewidth, zorder=zorder, alpha=1.0)
                drawing_success = True
                print("✅ 方法2绘制成功")
            except Exception as e2:
                print(f"❌ 方法2失败: {str(e2)}")
        
        # 如果前两种方法都失败，使用方法1
        if not drawing_success:
            try:
                print("尝试方法1: boundary plot...")
                admin_boundary.boundary.plot(ax=ax, color=color, linewidth=linewidth, zorder=zorder, alpha=1.0)
                drawing_success = True
                print("✅ 方法1绘制成功")
            except Exception as e1:
                print(f"❌ 方法1失败: {str(e1)}")
        
        if not drawing_success:
            print("❌ 所有绘制方法都失败了")
            return False
        
        # 强制刷新图像
        try:
            ax.figure.canvas.draw_idle()
            print("✅ 图像刷新成功")
        except:
            pass
        
        print("行政边界绘制完成")
        return True
        
    except Exception as e:
        print(f"绘制行政边界失败: {str(e)}")
        import traceback
        print(f"详细错误信息: {traceback.format_exc()}")
        return False