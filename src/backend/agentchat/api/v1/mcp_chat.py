"""
MCP聊天API路由模块
提供MCP智能体的对话接口，支持流式响应和对话历史记录
"""
import json
from fastapi import APIRouter, Body, UploadFile, File
from agentchat.api.services.history import HistoryService
from agentchat.api.services.dialog import DialogService
from agentchat.api.services.mcp_chat import MCPChatAgent
from fastapi.responses import StreamingResponse

# 创建MCP聊天相关的API路由器，标签为"MCP-Chat"
router = APIRouter(tags=["MCP-Chat"])

# 前端根据Dialog.agent_type判断走/mcp_chat 还是/chat
@router.post("/mcp_chat", description="对话接口")
async def chat(user_input: str = Body(description='用户问题'),
               dialog_id: str = Body(description='对话的ID')):
    """与MCP助手进行对话，支持流式响应"""

    # 根据对话ID获取智能体信息
    agent = await DialogService.get_agent_by_dialog_id(dialog_id)
    mcp_chat_agent = MCPChatAgent(**agent)
    await mcp_chat_agent.init_MCP_Server()  # 初始化MCP服务器

    # 流式输出LLM生成结果
    async def general_generate():
        assistant_result = ""
        # 调用MCP智能体进行流式对话
        async for text in await mcp_chat_agent.ainvoke(user_input, dialog_id, True):
            assistant_result += text
            yield f"{text}\n\n"
        yield "[DONE]"  # 标记流式响应结束
        # 保存助手回复到历史记录
        await HistoryService.save_chat_history("assistant", assistant_result, dialog_id)

    # 保存用户输入到历史记录
    await HistoryService.save_chat_history("user", user_input, dialog_id)
    # 更新对话窗口的最近使用时间
    DialogService.update_dialog_time(dialog_id)
    return StreamingResponse(general_generate(), media_type="text/event-stream")
