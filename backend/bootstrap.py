# backend/bootstrap.py
"""
应用启动引导模块
Stdio 安全重定向、全局日志配置
此模块必须在 main.py 的最顶部第一个导入，确保在任何第三方库加载前完成初始化
"""
import os
import sys
import logging
from config_loader import config


def _ensure_stdio():
    """确保 stdio 不为 None，防止 GUI/无控制台模式下第三方库写入崩溃"""
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    if sys.stdin is None:
        sys.stdin = open(os.devnull, "r", encoding="utf-8")


def setup_logging() -> logging.Logger:
    """配置全局日志，返回根 Logger 实例"""
    logger = logging.getLogger("LumNeo")
    logger.setLevel(logging.INFO)

    logger.propagate = False    # 防止重复输出日志

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    original_stderr = getattr(sys, "__stderr__", sys.stderr)
    console_handler = logging.StreamHandler(original_stderr)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    is_frozen = getattr(sys, "frozen", False)
    is_gui_mode = sys.stdout is not sys.__stdout__

    if is_frozen or is_gui_mode:
        log_dir = config.logs_dir
        os.makedirs(log_dir, exist_ok=True)
        file_handler = logging.FileHandler(
            os.path.join(log_dir, "lumneo.log"), encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


# ⚡ 模块级自动执行：只要被 import，stdio 防护立即生效
_ensure_stdio()

# 导出全局 logger，其他模块直接 from backend.bootstrap import logger
logger = setup_logging()