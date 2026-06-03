# backend/services/llm_service.py
import uuid
import json
import time
import base64
from fastapi import Request
from openai import AsyncOpenAI, APIError
from typing import List, Dict, AsyncGenerator, Optional
from backend.services.tools import get_all_tools, execute_tool


class LLMService:
    instance: Optional["LLMService"] = None

    def __init__(self,
                 model_type: str,
                 model_name: str,
                 api_key: str = "",
                 base_url: str = None,
                 thinking: str = 'enabled'):
        self.model_type = model_type
        self.model_name = model_name
        self.thinking = thinking
        self.client = AsyncOpenAI(api_key=api_key or None, base_url=base_url)

    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        enable_tools: bool = False,
        tools: Optional[List[Dict]] = None,
        request: Optional[Request] = None,
        mcp_manager=None,
        params: Dict = None,
    ) -> AsyncGenerator[str, None]:
        params = params or {}

        # ---------- 图像生成分支 ----------
        if "image" in self.model_name.lower():
            prompt = ""
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    prompt = msg.get("content", "")
                    break

            if not prompt:
                yield "❌ 未找到有效的用户提示词，无法生成图像。"
                return

            size = params.get("size", "1024x768")
            quality = params.get("quality", "standard")
            n = params.get("n", 1)

            try:
                response = await self.client.images.generate(
                    model=self.model_name,
                    prompt=prompt,
                    size=size,
                    quality=quality,
                    n=n,
                )

                if not response.data or len(response.data) == 0:
                    yield "❌ 图像生成服务未返回有效结果。"
                    return

                img_data = response.data[0]

                if hasattr(img_data, 'url') and img_data.url:
                    image_url = img_data.url
                    yield f"![生成的图片]({image_url})"
                else:
                    if hasattr(img_data, 'b64_json') and img_data.b64_json:
                        yield "⚠️ 图像生成服务仅返回 base64 数据，无法提供直接链接。"
                    else:
                        yield "❌ 图像生成服务未返回图片 URL 或 base64 数据。"
                return

            except APIError as e:
                yield f"❌ 图像生成 API 错误：{e.message}"
            except Exception as e:
                yield f"❌ 图像生成失败：{str(e)}"
            return

        # ---------- 原有文本生成 + 工具调用分支 ----------
        current_messages = messages.copy()

        if tools is None and enable_tools:
            tools = await get_all_tools(mcp_manager)

        reasoning_start_time = None

        # 全步骤累计 token（计费总量）
        total_usage_all_steps = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "completion_tokens_details": {}
        }

        # 最后一步的 token 和生成耗时（用于展示最终回答速度）
        last_step_usage = None
        last_step_generation_time = 0.0

        MAX_STEPS = 6

        for step in range(MAX_STEPS):
            if request and await request.is_disconnected():
                break

            tool_calls_by_index = {}
            reasoning_buffer = ""
            in_reasoning = False

            # 当前步骤的 usage 记录（会在收到 usage chunk 时填充）
            step_usage_record = None
            # 当前步骤从第一个 token 开始计时的生成时间
            step_generation_time = 0.0

            kwargs = {
                "model": self.model_name,
                "messages": current_messages,
                "stream": True,
                "temperature": params.get('temperature', 1.0),
                "top_p": params.get('top_p', 0.95),
                "frequency_penalty": params.get('frequency_penalty', 0.0),
                "presence_penalty": params.get('presence_penalty', 0.0),
                "stream_options": {"include_usage": True},
                "extra_body": {
                    "top_k": params.get('top_k', 20),
                    "chat_template_kwargs": {"enable_thinking": self.thinking == "enabled", "preserve_thinking": True},
                    "enable_thinking": self.thinking == "enabled",
                    "preserve_thinking": True
                }
            }

            if step == MAX_STEPS - 1:
                yield "\n⚠️ 工具调用次数已达上限，正在基于已收集信息生成最终总结...\n"
                current_messages.append({
                    "role": "user",
                    "content": "【系统指令】你的工具调用次数已达最大限制。请立即放弃尝试调用工具，根据上面已经收集到的上下文信息，直接回答我的问题并进行最终总结。"
                })
                kwargs["messages"] = current_messages
            elif tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"

            try:
                response = await self.client.chat.completions.create(**kwargs)
            except APIError as e:
                yield f"\n❌ 模型服务错误：{e.message}"
                break

            first_token_time = None
            tool_preview_active = {}

            async for chunk in response:
                if request and await request.is_disconnected():
                    break

                # ---------- usage 收集（无论 choices 是否存在，都处理）----------
                if hasattr(chunk, 'usage') and chunk.usage:
                    step_usage = chunk.usage
                    try:
                        su = step_usage.model_dump()
                    except AttributeError:
                        su = dict(step_usage)

                    # 累加到全步骤总计费 token
                    total_usage_all_steps["prompt_tokens"] += su.get("prompt_tokens", 0) or 0
                    total_usage_all_steps["completion_tokens"] += su.get("completion_tokens", 0) or 0
                    total_usage_all_steps["total_tokens"] += su.get("total_tokens", 0) or 0

                    details = su.get("completion_tokens_details") or {}
                    for k, v in details.items():
                        total_usage_all_steps["completion_tokens_details"][k] = \
                            total_usage_all_steps["completion_tokens_details"].get(k, 0) + (v or 0)

                    # 保存本步 usage（可能会被同一步内多次覆盖，最终保留最后一个）
                    step_usage_record = {
                        "prompt_tokens": su.get("prompt_tokens", 0) or 0,
                        "completion_tokens": su.get("completion_tokens", 0) or 0,
                        "total_tokens": su.get("total_tokens", 0) or 0,
                        "completion_tokens_details": details
                    }

                if chunk.choices:
                    d = chunk.choices[0].delta
                    if first_token_time is None:
                        first_token_time = time.time()
                else:
                    # 无 choices 的 chunk（如仅含 usage）直接跳过后续内容处理
                    continue

                delta = chunk.choices[0].delta
                reasoning = getattr(delta, 'reasoning_content', None)
                tool_calls_data = getattr(delta, 'tool_calls', None)
                delta_content = getattr(delta, 'content', None)

                if reasoning:
                    if not in_reasoning:
                        in_reasoning = True
                        reasoning_start_time = time.time()
                        yield "<!--reasoning:start-->"
                    reasoning_buffer += reasoning
                    yield reasoning
                    continue

                if in_reasoning and (delta_content or tool_calls_data):
                    reasoning_time = time.time() - reasoning_start_time
                    yield f"<!--reasoning:end:{reasoning_time:.2f}-->"
                    in_reasoning = False

                if tool_calls_data:
                    for tc_delta in tool_calls_data:
                        idx = getattr(tc_delta, 'index', None)
                        if idx is None:
                            idx = tc_delta.id if tc_delta.id else str(uuid.uuid4())

                        if idx not in tool_preview_active and tc_delta.function:
                            func_name = tc_delta.function.name or ""
                            tool_preview_active[idx] = func_name
                            yield f"<!--tool_preview:start:{idx}:{func_name}-->"

                        if idx not in tool_calls_by_index:
                            tool_calls_by_index[idx] = {
                                "id": getattr(tc_delta, 'id', None),
                                "type": "function",
                                "function": {"name": "", "arguments": ""}
                            }
                        target = tool_calls_by_index[idx]
                        if tc_delta.id:
                            target["id"] = tc_delta.id
                        if tc_delta.function:
                            # 只在 name 未赋值时赋予，避免重复拼接
                            if tc_delta.function.name and not target["function"]["name"]:
                                target["function"]["name"] = tc_delta.function.name
                            arg_delta = tc_delta.function.arguments or ""
                            target["function"]["arguments"] += arg_delta
                            if arg_delta:
                                yield arg_delta

                elif delta_content:
                    # 关闭所有活跃的 tool_preview
                    for idx in list(tool_preview_active.keys()):
                        tc = tool_calls_by_index.get(idx)
                        if tc:
                            snapshot = {tc["id"]: {"name": tc["function"]["name"], "arguments": tc["function"]["arguments"]}}
                            yield f"<!--tool_preview:end:{idx}:{json.dumps(snapshot)}-->"
                        else:
                            yield f"<!--tool_preview:end:{idx}:{{}}-->"
                        del tool_preview_active[idx]
                    yield delta_content

            # 循环结束后处理可能残留的 tool_preview
            if tool_preview_active:
                for idx in list(tool_preview_active.keys()):
                    tc = tool_calls_by_index.get(idx)
                    if tc:
                        snapshot = {tc["id"]: {"name": tc["function"]["name"], "arguments": tc["function"]["arguments"]}}
                        yield f"<!--tool_preview:end:{idx}:{json.dumps(snapshot)}-->"
                    else:
                        yield f"<!--tool_preview:end:{idx}:{{}}-->"
                    del tool_preview_active[idx]

            # 记录本步骤生成时间
            if first_token_time is not None:
                step_generation_time = time.time() - first_token_time
                # 将步骤时间赋值给最后一步记录变量（下一步的循环会覆盖）
                last_step_generation_time = step_generation_time

            if in_reasoning:
                reasoning_time = time.time() - reasoning_start_time
                yield f"<!--reasoning:end:{reasoning_time:.2f}-->"

            # 将收集到的 usage 记录赋给最后一步
            if step_usage_record:
                last_step_usage = step_usage_record

            # 构建工具调用字典
            tool_calls = {}
            for idx, tc in tool_calls_by_index.items():
                if tc.get("id"):
                    tool_calls[tc["id"]] = tc
                else:
                    temp_id = f"call_{idx}"
                    tc["id"] = temp_id
                    tool_calls[temp_id] = tc

            if tool_calls and request and await request.is_disconnected():
                break

            if not tool_calls:
                break

            # 过滤无效工具调用
            valid_calls = {}
            for tid, tc in tool_calls.items():
                if tc["function"]["name"].strip():
                    valid_calls[tid] = tc
                else:
                    yield "\n⚠️ 检测到无效工具调用（名称空白），已忽略。\n"

            if not valid_calls:
                break

            yield f"\n<!--tool_calls:start-->"

            assistant_msg = {
                "role": "assistant",
                "content": None,
                "tool_calls": list(valid_calls.values())
            }
            current_messages.append(assistant_msg)

            for tc in valid_calls.values():
                func_name = tc["function"]["name"]
                raw_args = tc["function"]["arguments"]
                try:
                    args = json.loads(raw_args)
                except json.JSONDecodeError as e:
                    error_detail = f"JSON 解析失败: {e}\n原始参数: {raw_args[:200]}"
                    yield f"\n❌ 工具 `{func_name}` 参数错误：{error_detail}\n"
                    args = {}

                try:
                    result = await execute_tool(func_name, args, mcp_manager)
                except Exception as e:
                    error_msg = str(e)
                    if len(error_msg) > 1000:
                        error_msg = error_msg[:1000] + "...(错误信息过长已截断)"
                    result = f"工具执行出错: {error_msg}"

                result_str = str(result)
                json_str = json.dumps({'name': func_name, 'arguments': args})
                b64_str = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')
                yield f"<!--tool_call:{b64_str}-->"
                yield f"<!--tool_result:{json.dumps({'name': func_name, 'result': result_str})}-->"

                current_messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result_str
                })
            yield "<!--tool_calls:end-->"

        # ---------- 最终 token 统计输出 ----------
        if last_step_usage and last_step_usage["completion_tokens"] > 0:
            speed = last_step_usage["completion_tokens"] / last_step_generation_time if last_step_generation_time > 0 else 0.0
            token_info = {
                "final_answer_usage": last_step_usage,
                "total_usage_all_steps": total_usage_all_steps,
                "speed": f"{speed:.2f} token/s"
            }
            yield f"\n<!--token_usage:{json.dumps(token_info)}-->"