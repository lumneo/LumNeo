# backend/routes/chat.py
import re
import json
import socket
import traceback
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Optional, Any
from backend.services.llm_service import LLMService
from backend.services.tools import get_local_tools, get_mcp_tools
from backend.database import get_db
from backend.utils.base import resource_path, get_current_time
from config_loader import config
import backend


router = APIRouter(prefix="/api", tags=["chat"])

BASE_SYSTEM_PROMPT = ""

full_path = resource_path("system_prompt.md")
with open(full_path, 'r', encoding="utf-8") as f:
    BASE_SYSTEM_PROMPT = f.read()

BASE_SYSTEM_PROMPT = BASE_SYSTEM_PROMPT.replace("{{uploads_dir}}", str(config.uploads_dir))


disabled_tools = ['system_write_file', 'system_patch_file', 'system_create_project_tree', 'system_read_file_list']
default_tools = ['system_get_weather', 'system_read_file']

class ModelConfig(BaseModel):
    type: str
    model_name: str
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    thinking: str = 'enabled'


class ChatRequest(BaseModel):
    messages: List[Dict[str, Any]]
    enable_tools: bool = False
    llm_config: Optional[ModelConfig] = None
    profile_id: Optional[int] = None


async def get_mcp_manager(request: Request):
    return request.app.state.mcp_manager


@router.post("/chat")
async def chat(
    request: ChatRequest,
    fastapi_request: Request,
    mcp_manager=Depends(get_mcp_manager)
):
    try:
        # 1. 创建 LLM 服务实例
        if request.llm_config:
            config = request.llm_config
            if config.type == "local":
                service = LLMService(
                    model_type="local",
                    model_name=config.model_name,
                    base_url=config.base_url,
                    api_key=config.api_key,
                    thinking=config.thinking
                )
            else:
                if not config.api_key:
                    raise HTTPException(status_code=400, detail="线上模型必须提供 API Key")
                service = LLMService(
                    model_type="online",
                    model_name=config.model_name,
                    base_url=config.base_url,
                    api_key=config.api_key,
                    thinking=config.thinking
                )
        else:
            service = LLMService.instance
            if not service:
                raise HTTPException(status_code=400, detail="请先选择或配置模型")

        # 2. 处理消息和角色
        messages = request.messages.copy()
        local_tools = get_local_tools()
        tools = [t for t in local_tools if t["function"]["name"] in default_tools]
        profile_prompt = ""

        # 如果携带了 profile_id，获取角色信息
        if request.enable_tools and request.profile_id is not None:
            db = await get_db()
            cursor = await db.execute(
                "SELECT tools, profile_prompt FROM profiles WHERE id = ?",
                (request.profile_id,)
            )
            row = await cursor.fetchone()
            await db.close()

            if row:
                allowed_tools = json.loads(row[0] or "[]")
                profile_prompt = row[1] or ""

                # 筛选工具
                mcp_tools = await get_mcp_tools(mcp_manager) if request.enable_tools else []
                enable_tools = [t for t in local_tools if t["function"]["name"] in disabled_tools]
                enable_tools.extend(mcp_tools)
                use_tools = [t for t in enable_tools if t["function"]["name"] in allowed_tools]
                tools.extend(use_tools)

        messages = [m for m in messages if m["role"] != "system"]

        system_prompt = BASE_SYSTEM_PROMPT.replace("{{workspace_path}}", backend.workspace_path)
        system_prompt = system_prompt.replace("{{time_now}}", get_current_time())
        # profile_prompt 加入到 system_prompt 中
        if profile_prompt:
            system_prompt = f"{system_prompt}\n\n ### 角色扮演 \n\n{profile_prompt}"

        messages.insert(0, {"role": "system", "content": f"{system_prompt}\n\n{backend.workspace_path}"})

        REASONING_BLOCK = re.compile(
            r'<!--reasoning:start-->.*?<!--reasoning:end:\d+\.?\d*-->',
            re.DOTALL
        )
        MISC_MARKERS = re.compile(
            r'<!--(?:token_usage|reasoning):[^>]*-->'
        )

        for msg in messages:
            content = msg.get("content")
            if isinstance(content, str):
                content = REASONING_BLOCK.sub('', content)
                content = MISC_MARKERS.sub('', content)
                msg["content"] = content
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        text = part["text"]
                        text = REASONING_BLOCK.sub('', text)
                        text = MISC_MARKERS.sub('', text)
                        part["text"] = text

        # 3. 流式响应（使用关键字参数，避免顺序错误）
        return StreamingResponse(
            service.generate_response(
                messages=messages,
                enable_tools=request.enable_tools,
                tools=tools,
                request=fastapi_request,
                mcp_manager=mcp_manager,
            ),
            media_type="text/event-stream"
        )
    except Exception as e:
        error_trace = traceback.format_exc()
        raise HTTPException(
            status_code=500, 
            detail=f"打包环境运行崩溃，详细堆栈如下:\n{error_trace}"
        )


@router.get("/tools")
async def get_tools(mcp_manager=Depends(get_mcp_manager)):
    local_tools = get_local_tools()
    enable_tools = [t for t in local_tools if t["function"]["name"] in disabled_tools]
    mcp_tools = await get_mcp_tools(mcp_manager)
    enable_tools.extend(mcp_tools)
    return {"tools": enable_tools}

@router.get('/local-ip')
async def get_local_ip():
    """获取本机IP地址"""
    try:
        # 创建一个UDP套接字，连接到一个外部地址（不发送数据）
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"