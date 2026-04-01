import os
import rasterio
from rasterio.warp import reproject, Resampling
import matplotlib.pyplot as plt
import os

# 模板栅格文件路径
template_file = r"data\raster_results\new_template_30m.tif"
input_root = r"webgis-project\data_1"
output_root = r"webgis-project\data_reproject"

with rasterio.open(template_file) as template_ds:
    template_meta = template_ds.meta.copy()
    template_transform = template_ds.transform
    template_crs = template_ds.crs
    template_width = template_ds.width
    template_height = template_ds.height
# 遍历每一年的文件夹
for file in os.listdir(input_root):
    if not file.endswith('.tif'):
        continue
    input_file = os.path.join(input_root, file)
    output_file = os.path.join(output_root, file)
    with rasterio.open(input_file) as src:
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

        with rasterio.open(output_file, 'w', **dst_meta) as dst:
            for i in range(1, src.count + 1):
                reproject(
                    source=rasterio.band(src, i),
                    destination=rasterio.band(dst, i),
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=template_transform,
                    dst_crs=template_crs,
                    resampling=Resampling.bilinear,
                    dst_nodata=dst_nodata
                )
    print(f"{file} 已对齐到模板栅格。")