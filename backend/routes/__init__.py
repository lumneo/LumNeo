# backend/routes/__init__.py
import importlib
import pkgutil
from fastapi import FastAPI

def register_all_routers(app: FastAPI, package_path: str = __path__[0], prefix: str = ""):
    """自动扫描当前包下所有模块，注册其中名为 router 的对象"""
    for module_info in pkgutil.iter_modules([package_path]):
        if module_info.name.startswith("_"):
            continue  # 跳过 __init__.py 等私有模块
        module = importlib.import_module(f".{module_info.name}", package=__name__)
        router = getattr(module, "router", None)
        if router is not None:
            app.include_router(router)