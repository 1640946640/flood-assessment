from flask import Flask, jsonify, request
from flask_cors import CORS
import os
import json
from dotenv import load_dotenv

# 导入日志工具
from utils.logger import log_message, log_and_print

# 导入模块
from api.datasets import datasets_bp
from api.grid import raster_bp
from api.flood import flood_bp
from api.flood_points import flood_points_bp
from api.export import export_bp
from api.correlation import correlation_bp
from api.raster_compare import raster_compare_bp
from api.alignment import alignment_bp
from api.raster_statistics import raster_statistics_bp

# 加载环境变量
load_dotenv()

# 移除静态文件配置，只创建纯API应用
app = Flask(__name__)

CORS(app)

# 记录应用启动
log_message("Flask API应用开始初始化")

# 注册蓝图
app.register_blueprint(datasets_bp, url_prefix='/api/datasets')
app.register_blueprint(raster_bp, url_prefix='/api/raster')
app.register_blueprint(flood_bp, url_prefix='/api/flood')
app.register_blueprint(flood_points_bp, url_prefix='/api/flood-points')
app.register_blueprint(export_bp, url_prefix='/api/export')
app.register_blueprint(correlation_bp, url_prefix='/api/correlation')
app.register_blueprint(raster_compare_bp, url_prefix='/api/raster_compare')
app.register_blueprint(alignment_bp, url_prefix='/api/alignment')
app.register_blueprint(raster_statistics_bp, url_prefix='/api/raster-statistics')

log_message("所有API蓝图注册完成")

@app.route('/api/health')
def health_check():
    """API健康检查接口"""
    log_message("健康检查请求")
    return jsonify({"status": "ok", "message": "API服务正常运行"})

@app.route('/')
def api_info():
    """API信息接口，替代原来的静态首页"""
    return jsonify({
        "name": "洪涝灾害评估系统API",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "health": "/api/health",
            "datasets": "/api/datasets",
            "raster": "/api/raster",
            "flood": "/api/flood",
            "flood-points": "/api/flood-points",
            "export": "/api/export",
            "correlation": "/api/correlation",
            "raster_compare": "/api/raster_compare",
            "alignment": "/api/alignment",
            "raster-statistics": "/api/raster-statistics"
        }
    })

if __name__ == '__main__':
    host = os.getenv('HOST', '0.0.0.0')
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('DEBUG', 'true').lower() == 'true'
    
    log_and_print(f"启动Flask API应用 - Host: {host}, Port: {port}, Debug: {debug}")
    log_and_print("注意：此应用仅提供API接口，不包含前端页面")
    app.run(host=host, port=port, debug=debug)