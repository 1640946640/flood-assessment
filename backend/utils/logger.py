import os
import datetime
from functools import wraps

class SimpleLogger:
    """简单的日志记录器，将所有输出记录到txt文件"""
    
    def __init__(self, log_dir="logs"):
        """初始化日志记录器
        
        Args:
            log_dir (str): 日志文件夹路径
        """
        self.log_dir = log_dir
        self.ensure_log_dir()
        
        # 创建当前会话的日志文件
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = os.path.join(self.log_dir, f"app_log_{timestamp}.txt")
        
        # 写入会话开始标记
        self.write_log(f"=== 会话开始: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
    
    def ensure_log_dir(self):
        """确保日志目录存在"""
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)
    
    def write_log(self, message):
        """写入日志消息到文件
        
        Args:
            message (str): 要记录的消息
        """
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(log_entry)
        except Exception as e:
            print(f"日志写入失败: {e}")
    
    def log_and_print(self, message):
        """同时输出到控制台和日志文件
        
        Args:
            message (str): 要记录的消息
        """
        print(message)
        self.write_log(message)

# 全局日志实例
logger = SimpleLogger()

def log_function_call(func):
    """装饰器：记录函数调用
    
    Args:
        func: 被装饰的函数
        
    Returns:
        装饰后的函数
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        logger.write_log(f"调用函数: {func.__name__}")
        try:
            result = func(*args, **kwargs)
            logger.write_log(f"函数 {func.__name__} 执行完成")
            return result
        except Exception as e:
            logger.write_log(f"函数 {func.__name__} 执行出错: {str(e)}")
            raise
    return wrapper

def log_message(message):
    """记录消息到日志文件
    
    Args:
        message (str): 要记录的消息
    """
    logger.write_log(message)

def log_and_print(message):
    """同时输出到控制台和日志文件
    
    Args:
        message (str): 要记录的消息
    """
    logger.log_and_print(message)