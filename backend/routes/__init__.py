from fastapi import FastAPI

from . import chat, chats, files, model, models, profiles, workspace

def register_all_routers(app: FastAPI):
    modules = [chat, chats, files, model, models, profiles, workspace]  # 列出所有模块
    for mod in modules:
        router = getattr(mod, "router", None)
        if router is not None:
            app.include_router(router)