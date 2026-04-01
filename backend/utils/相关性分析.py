import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from osgeo import gdal
import warnings
from scipy.stats import pearsonr, spearmanr
from sklearn.metrics import r2_score
import matplotlib.font_manager as fm
import os

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

warnings.filterwarnings('ignore')

class RasterCorrelationAnalysis:
    """栅格数据相关性分析类"""
    
    def __init__(self, output_dir=None):
        """
        初始化相关性分析器
        
        Args:
            output_dir (str): 输出目录路径，默认为当前目录下的correlation_analysis_results
        """
        if output_dir is None:
            self.output_dir = os.path.join(os.getcwd(), 'correlation_analysis_results')
        else:
            self.output_dir = output_dir
        
        # 确保输出目录存在
        os.makedirs(self.output_dir, exist_ok=True)
        
        # 存储栅格数据
        self.raster_data = {}
        self.data_names = []
        
    def load_raster(self, file_path, name):
        """
        加载栅格数据
        
        Args:
            file_path (str): 栅格文件路径
            name (str): 数据名称（如H、E、V、S、M、R、IDF、IPI）
        
        Returns:
            bool: 加载是否成功
        """
        try:
            # 打开栅格文件
            dataset = gdal.Open(file_path)
            if dataset is None:
                print(f"无法打开文件: {file_path}")
                return False
            
            # 读取数据
            band = dataset.GetRasterBand(1)
            data = band.ReadAsArray()
            
            # 获取无效值
            nodata = band.GetNoDataValue()
            
            # 处理无效值
            if nodata is not None:
                data = np.where(data == nodata, np.nan, data)
            
            # 存储数据
            self.raster_data[name] = data.flatten()  # 展平为一维数组
            self.data_names.append(name)
            
            print(f"成功加载 {name} 数据: {file_path}")
            print(f"数据形状: {data.shape}, 有效值数量: {np.sum(~np.isnan(data.flatten()))}")
            
            return True
            
        except Exception as e:
            print(f"加载 {name} 数据时出错: {str(e)}")
            return False
    
    def load_multiple_rasters(self, raster_paths):
        """
        批量加载栅格数据
        
        Args:
            raster_paths (dict): 栅格文件路径字典，格式为 {name: file_path}
        
        Returns:
            int: 成功加载的文件数量
        """
        success_count = 0
        for name, file_path in raster_paths.items():
            if self.load_raster(file_path, name):
                success_count += 1
        
        print(f"\n总共加载了 {success_count}/{len(raster_paths)} 个栅格文件")
        return success_count
    
    def prepare_data_for_analysis(self):
        """
        准备用于分析的数据，移除所有数据中都为NaN的像素
        
        Returns:
            pd.DataFrame: 清理后的数据框
        """
        if not self.raster_data:
            raise ValueError("没有加载任何栅格数据")
        
        # 创建数据框
        df = pd.DataFrame(self.raster_data)
        
        # 移除任何变量为NaN的行
        df_clean = df.dropna()
        
        print(f"\n数据清理结果:")
        print(f"原始数据点数: {len(df)}")
        print(f"有效数据点数: {len(df_clean)}")
        print(f"数据完整率: {len(df_clean)/len(df)*100:.2f}%")
        
        return df_clean
    
    def calculate_correlation_matrix(self, method='pearson'):
        """
        计算相关性矩阵
        
        Args:
            method (str): 相关性计算方法，'pearson' 或 'spearman'
        
        Returns:
            pd.DataFrame: 相关性矩阵
        """
        df_clean = self.prepare_data_for_analysis()
        
        if method == 'pearson':
            corr_matrix = df_clean.corr(method='pearson')
        elif method == 'spearman':
            corr_matrix = df_clean.corr(method='spearman')
        else:
            raise ValueError("method 必须是 'pearson' 或 'spearman'")
        
        return corr_matrix, df_clean
    
    def plot_correlation_heatmap(self, method='pearson', figsize=(12, 10), save_plot=True, file_prefix=None):
        """
        绘制相关性热力图
        
        Args:
            method (str): 相关性计算方法
            figsize (tuple): 图形大小
            save_plot (bool): 是否保存图片
        
        Returns:
            tuple: (fig, ax, corr_matrix)
        """
        corr_matrix, df_clean = self.calculate_correlation_matrix(method)
        
        # 创建图形
        fig, ax = plt.subplots(figsize=figsize)
        
        # 绘制热力图（使用matplotlib替代seaborn）
        # 创建热力图，显示完整的相关性矩阵
        im = ax.imshow(corr_matrix.values, cmap='RdBu_r', aspect='equal', vmin=-1, vmax=1)
        
        # 添加颜色条
        cbar = plt.colorbar(im, ax=ax, shrink=0.8)
        cbar.set_label('相关系数', rotation=270, labelpad=15)
        
        # 添加数值标注
        for i in range(len(corr_matrix)):
            for j in range(len(corr_matrix)):
                text = ax.text(j, i, f'{corr_matrix.iloc[i, j]:.3f}',
                             ha="center", va="center", 
                             color="black" if abs(corr_matrix.iloc[i, j]) < 0.5 else "white",
                             fontsize=10, fontweight='bold')
        
        # 设置坐标轴
        ax.set_xticks(range(len(corr_matrix.columns)))
        ax.set_yticks(range(len(corr_matrix.columns)))
        ax.set_xticklabels(corr_matrix.columns)
        ax.set_yticklabels(corr_matrix.columns)
        
        # 将X轴标签移到顶部
        ax.xaxis.tick_top()
        ax.xaxis.set_label_position('top')
        
        # 设置标题和标签
        method_name = '皮尔逊' if method == 'pearson' else '斯皮尔曼'
        ax.set_title(f'洪涝灾害评估指标{method_name}相关性分析热力图\n(样本数: {len(df_clean)})', 
                    fontsize=16, fontweight='bold', pad=40)
        
        # 调整标签
        ax.set_xlabel('评估指标', fontsize=12, fontweight='bold')
        ax.set_ylabel('评估指标', fontsize=12, fontweight='bold')
        
        # 旋转标签
        plt.xticks(rotation=45, ha='left')
        plt.yticks(rotation=0)
        
        # 调整布局
        plt.tight_layout()
        
        # 保存图片
        if save_plot:
            if file_prefix:
                plot_path = os.path.join(self.output_dir, f'{file_prefix}_correlation_heatmap_{method}.png')
            else:
                plot_path = os.path.join(self.output_dir, f'correlation_heatmap_{method}.png')
            plt.savefig(plot_path, dpi=300, bbox_inches='tight')
            print(f"相关性热力图已保存: {plot_path}")
        
        return fig, ax, corr_matrix
    
    def generate_correlation_report(self, methods=['pearson', 'spearman'], file_prefix=None):
        """
        生成详细的相关性分析报告
        
        Args:
            methods (list): 要使用的相关性分析方法列表
        
        Returns:
            dict: 包含所有分析结果的字典
        """
        results = {}
        
        for method in methods:
            print(f"\n正在进行{method}相关性分析...")
            
            # 计算相关性矩阵
            corr_matrix, df_clean = self.calculate_correlation_matrix(method)
            
            # 绘制热力图
            fig, ax, _ = self.plot_correlation_heatmap(method, save_plot=True)
            
            # 存储结果
            results[method] = {
                'correlation_matrix': corr_matrix,
                'data': df_clean,
                'figure': fig
            }
            
            # 保存相关性矩阵到CSV
            csv_path = os.path.join(self.output_dir, f'correlation_matrix_{method}.csv')
            corr_matrix.to_csv(csv_path, encoding='utf-8-sig')
            print(f"相关性矩阵已保存: {csv_path}")
        
        # 生成文本报告
        self._generate_text_report(results, method, file_prefix)
        
        return results
    
    def _generate_text_report(self, results, method, file_prefix=None):
        """
        生成文本格式的分析报告
        
        Args:
            results (dict): 分析结果字典
        """
        if file_prefix:
            report_path = os.path.join(self.output_dir, f'{file_prefix}_correlation_report_{method}.txt')
        else:
            report_path = os.path.join(self.output_dir, 'correlation_report.txt')
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("洪涝灾害评估指标相关性分析报告\n")
            f.write("=" * 50 + "\n\n")
            
            # 数据概况
            if results:
                first_method = list(results.keys())[0]
                df_clean = results[first_method]['data']
                
                f.write("数据概况:\n")
                f.write(f"分析指标: {', '.join(df_clean.columns)}\n")
                f.write(f"有效数据点数: {len(df_clean)}\n")
                f.write(f"分析时间: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                
                # 描述性统计
                f.write("描述性统计:\n")
                f.write("-" * 30 + "\n")
                desc_stats = df_clean.describe()
                f.write(desc_stats.to_string())
                f.write("\n\n")
            
            # 各方法的相关性分析结果
            for method, result in results.items():
                method_name = '皮尔逊' if method == 'pearson' else '斯皮尔曼'
                f.write(f"{method_name}相关性分析结果:\n")
                f.write("-" * 30 + "\n")
                
                corr_matrix = result['correlation_matrix']
                
                # 找出强相关性（|r| > 0.7）
                strong_corr = []
                for i in range(len(corr_matrix.columns)):
                    for j in range(i+1, len(corr_matrix.columns)):
                        corr_val = corr_matrix.iloc[i, j]
                        if abs(corr_val) > 0.7:
                            strong_corr.append((
                                corr_matrix.columns[i],
                                corr_matrix.columns[j],
                                corr_val
                            ))
                
                if strong_corr:
                    f.write("强相关性 (|r| > 0.7):\n")
                    for var1, var2, corr_val in strong_corr:
                        f.write(f"  {var1} - {var2}: {corr_val:.3f}\n")
                else:
                    f.write("未发现强相关性 (|r| > 0.7)\n")
                
                f.write("\n完整相关性矩阵:\n")
                f.write(corr_matrix.to_string(float_format='%.3f'))
                f.write("\n\n")
        
        print(f"分析报告已保存: {report_path}")
    
    def plot_scatter_matrix(self, variables=None, figsize=(15, 15), save_plot=True, file_prefix=None):
        """
        绘制散点图矩阵
        
        Args:
            variables (list): 要分析的变量列表，None表示使用所有变量
            figsize (tuple): 图形大小
            save_plot (bool): 是否保存图片
        
        Returns:
            matplotlib.figure.Figure: 图形对象
        """
        df_clean = self.prepare_data_for_analysis()
        
        if variables is None:
            variables = df_clean.columns.tolist()
        
        # 如果变量太多，进行采样以提高绘图速度
        if len(df_clean) > 10000:
            df_sample = df_clean.sample(n=10000, random_state=42)
            print(f"数据量较大，随机采样10000个点进行绘图")
        else:
            df_sample = df_clean
        
        # 创建散点图矩阵
        fig = plt.figure(figsize=figsize)
        
        n_vars = len(variables)
        for i, var1 in enumerate(variables):
            for j, var2 in enumerate(variables):
                ax = plt.subplot(n_vars, n_vars, i * n_vars + j + 1)
                
                if i == j:
                    # 对角线绘制直方图
                    ax.hist(df_sample[var1], bins=30, alpha=0.7, color='skyblue')
                    if j == 0:
                        ax.set_ylabel('频数', fontsize=8)
                else:
                    # 非对角线绘制散点图
                    ax.scatter(df_sample[var2], df_sample[var1], alpha=0.5, s=1)
                
                # 设置标签
                if i == n_vars - 1:
                    ax.set_xlabel(var2, fontsize=8, rotation=45, ha='right')
                if j == 0:
                    ax.set_ylabel(var1, fontsize=8, rotation=0, ha='right')
                
                # 调整刻度标签大小和旋转
                ax.tick_params(labelsize=6)
                # 对所有子图设置标签旋转
                ax.tick_params(axis='x', rotation=45)
                ax.tick_params(axis='y', rotation=0)
        
        plt.suptitle('洪涝灾害评估指标散点图矩阵', fontsize=14, fontweight='bold', y=0.98)
        # 调整子图间距以避免标签重叠
        plt.subplots_adjust(left=0.1, bottom=0.1, right=0.95, top=0.92, wspace=0.3, hspace=0.3)
        
        if save_plot:
            if file_prefix:
                plot_path = os.path.join(self.output_dir, f'{file_prefix}_scatter_matrix.png')
            else:
                plot_path = os.path.join(self.output_dir, 'scatter_matrix.png')
            plt.savefig(plot_path, dpi=300, bbox_inches='tight')
            print(f"散点图矩阵已保存: {plot_path}")
        
        return fig


def main():
    """
    主函数示例
    """
    # 创建分析器实例
    analyzer = RasterCorrelationAnalysis()
    
    # 示例：定义栅格文件路径
    # 用户需要根据实际情况修改这些路径
    raster_paths = {
        'H': r"D:\WebGIS\洪涝灾害影响评估\webgis-project\backend\data\flood_results\a_hazard_20250623_172401_a3749754.tif",
        'E': r"D:\WebGIS\洪涝灾害影响评估\webgis-project\backend\data\flood_results\b_exposure_20250623_172416_8af55b60.tif", 
        'V': r"D:\WebGIS\洪涝灾害影响评估\webgis-project\backend\data\flood_results\c_value_20250623_172444_805555db_normalized.tif",
        'S': r"D:\WebGIS\洪涝灾害影响评估\webgis-project\backend\data\flood_results\d_sensitivity_20250623_172518_3b953d1e.tif",
        'M': r"D:\WebGIS\洪涝灾害影响评估\webgis-project\backend\data\flood_results\e_resistance_20250623_173147_173b411b.tif",
        'R': r"D:\WebGIS\洪涝灾害影响评估\webgis-project\backend\data\flood_results\f_mitigation_20250623_173211_997a9181.tif",
        'IDF': r"D:\WebGIS\洪涝灾害影响评估\webgis-project\backend\data\flood_results\g_IDF_20250623_173422_1853533a_IDFi.tif",
        'IPI': r"D:\WebGIS\洪涝灾害影响评估\webgis-project\backend\data\flood_results\g_IDF_20250623_173422_1853533a_IPIi.tif"
    }
    
    print("开始加载栅格数据...")
    
    # 加载数据（这里需要用户提供实际的文件路径）
    success_count = analyzer.load_multiple_rasters(raster_paths)
    
    if success_count == 0:
        print("没有成功加载任何数据，请检查文件路径")
        return
    
    # 进行相关性分析
    print("\n开始相关性分析...")
    results = analyzer.generate_correlation_report(['pearson', 'spearman'])
    
    # 绘制散点图矩阵
    print("\n绘制散点图矩阵...")
    analyzer.plot_scatter_matrix()
    
    print("\n相关性分析完成！请查看输出目录中的结果文件。")


if __name__ == "__main__":
    main()