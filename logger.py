# -*- coding: utf-8 -*-
"""日志模块 - 按日期记录运行日志"""
import json
import os
import logging
from datetime import datetime

# 日志级别名称映射（避免使用已弃用的 getLevelName）
LEVEL_NAME_MAP = {
    logging.DEBUG: 'DEBUG',
    logging.INFO: 'INFO',
    logging.WARNING: 'WARNING',
    logging.ERROR: 'ERROR',
    logging.CRITICAL: 'CRITICAL',
}

_NAME_TO_LEVEL = {
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO,
    'WARNING': logging.WARNING,
    'ERROR': logging.ERROR,
}


def log_level_from_name(level_name: str) -> int:
    """将级别名称转为 logging 常量"""
    return _NAME_TO_LEVEL.get(str(level_name).upper(), logging.WARNING)


class DailyFileHandler(logging.FileHandler):
    """按日期创建日志文件的处理器"""

    def __init__(self, log_dir="log", filename_prefix="app"):
        self.log_dir = log_dir
        self.filename_prefix = filename_prefix
        self.current_date = None
        self.current_file = None

        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)

        self._update_file()
        super().__init__(self.current_file, encoding='utf-8', mode='a')

    def _update_file(self):
        """更新日志文件路径（按日期）"""
        today = datetime.now().strftime("%Y-%m-%d")

        if today != self.current_date:
            self.current_date = today
            filename = f"{self.filename_prefix}_{today}.log"
            self.current_file = os.path.join(self.log_dir, filename)
            return True
        return False

    def emit(self, record):
        """发送日志记录"""
        date_changed = self._update_file()

        if date_changed or self.baseFilename != self.current_file:
            if self.stream:
                self.stream.close()
            self.baseFilename = self.current_file
            self.stream = self._open()

        super().emit(record)


def _resolve_initial_log_level_name() -> str:
    """解析初始日志级别：环境变量优先，否则读 global_settings.json"""
    env = os.environ.get('TL_MACRO_LOG_LEVEL', '').strip().upper()
    if env in _NAME_TO_LEVEL:
        return env
    try:
        from utils import get_app_base_dir
        path = os.path.join(get_app_base_dir(), "config", "global_settings.json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            level = str(data.get("log_level", "WARNING")).upper()
            if level in _NAME_TO_LEVEL:
                return level
    except Exception:
        pass
    return "WARNING"


def setup_logger(log_dir="log", log_level=logging.WARNING):
    """设置日志系统"""
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    else:
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            today_filename = f"app_{today}.log"
            for filename in os.listdir(log_dir):
                if filename.startswith("app_") and filename.endswith(".log"):
                    if filename != today_filename:
                        file_path = os.path.join(log_dir, filename)
                        try:
                            os.remove(file_path)
                        except Exception:
                            pass
        except Exception:
            pass

    logger = logging.getLogger("TL_Macro")
    logger.setLevel(log_level)

    if logger.handlers:
        return logger

    log_format = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] [%(filename)s:%(lineno)d] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )

    file_handler = DailyFileHandler(log_dir, "app")
    file_handler.setLevel(log_level)
    file_handler.setFormatter(log_format)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(log_format)
    logger.addHandler(console_handler)

    return logger


_logger = None


def get_logger():
    """获取全局日志记录器（单例模式）"""
    global _logger
    if _logger is None:
        from utils import get_app_base_dir
        log_dir = os.path.join(get_app_base_dir(), "log")
        level_name = _resolve_initial_log_level_name()
        _logger = setup_logger(
            log_dir=log_dir,
            log_level=log_level_from_name(level_name),
        )
    return _logger


def set_log_level(log_level):
    """动态设置日志级别"""
    logger = get_logger()
    logger.setLevel(log_level)
    for handler in logger.handlers:
        handler.setLevel(log_level)
    level_name = LEVEL_NAME_MAP.get(log_level, f'Level {log_level}')
    logger.info(f"日志级别已更改为: {level_name}")


def get_current_log_level():
    """获取当前日志级别名称"""
    logger = get_logger()
    return LEVEL_NAME_MAP.get(logger.level, f'Level {logger.level}')
