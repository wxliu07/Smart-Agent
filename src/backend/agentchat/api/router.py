"""
AgentChat API 主路由模块

该模块负责聚合和注册所有 v1 版本的 API 路由，提供统一的 API 入口点。
包含聊天、对话、消息、代理、历史记录、用户、工具、LLM、知识库等多个功能模块的路由。
"""

from fastapi import APIRouter
from agentchat.api.v1 import (chat, dialog, message, agent, history, mcp_stdio_server, mcp_chat, mars,
                              user, llm, tool, knowledge, knowledge_file, mcp_agent, mcp_server, mcp_user_config,
                              workspace, lingseek, usage_stats, upload, wechat)

# 创建主路由器，设置 API 前缀为 /api/v1
router = APIRouter(prefix="/api/v1")

# 注册各个功能模块的子路由器
# 聊天相关路由
router.include_router(chat.router)
# 对话管理路由
router.include_router(dialog.router)
# 消息处理路由
router.include_router(message.router)
# AI 代理管理路由
router.include_router(agent.router)
# 历史记录路由
router.include_router(history.router)
# 用户管理路由
router.include_router(user.router)
# 工具管理路由
router.include_router(tool.router)
# 大语言模型路由
router.include_router(llm.router)
# 知识库管理路由
router.include_router(knowledge.router)
# 知识库文件管理路由
router.include_router(knowledge_file.router)
# MCP 服务器管理路由
router.include_router(mcp_server.router)
# MCP 标准输入输出服务器路由
router.include_router(mcp_stdio_server.router)
# MCP 聊天路由
router.include_router(mcp_chat.router)
# MCP 代理路由
router.include_router(mcp_agent.router)
# MCP 用户配置路由
router.include_router(mcp_user_config.router)
# Mars 功能路由
router.include_router(mars.router)
# 工作空间管理路由
router.include_router(workspace.router)
# Lingseek 功能路由
router.include_router(lingseek.router)
# 使用统计路由
router.include_router(usage_stats.router)
# 微信集成路由
router.include_router(wechat.router)
# 文件上传路由
router.include_router(upload.router)