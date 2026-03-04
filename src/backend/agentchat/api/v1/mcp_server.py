"""
MCP服务器管理API路由模块
提供MCP服务器的创建、查询、更新、删除等RESTful接口
支持MCP工具集成和配置管理
"""
import json
from typing import Optional

from fastapi import APIRouter, Body, Depends

from agentchat.api.services.mcp_server import MCPService
from agentchat.api.services.user import UserPayload, get_login_user
from agentchat.prompts.mcp import McpAsToolPrompt
from agentchat.schema.mcp import MCPResponseFormat
from agentchat.schema.schemas import resp_500, resp_200
from agentchat.core.agents.structured_response_agent import StructuredResponseAgent
from agentchat.services.mcp.manager import MCPManager
from loguru import logger

from agentchat.utils.convert import convert_mcp_config

# 创建MCP服务器相关的API路由器，标签为"MCP-Server"
router = APIRouter(tags=["MCP-Server"])


@router.post("/mcp_server")
async def create_mcp_server(server_name: str = Body(..., description="MCP Server的名称"),
                            url: str = Body(..., description="MCP Server 的URL"),
                            type: str = Body(..., description="MCP Server 的连接方式，SSE、Websocket"),
                            config: dict = Body(None, description="MCP Server 的配置信息"),
                            logo_url: Optional[str] = Body("xxxx", description="MCP Server 的LOGO"),
                            login_user: UserPayload = Depends(get_login_user)):
    """创建新的MCP服务器"""
    try:
        # 构建服务器信息字典
        server_info = {
            "server_name": server_name,
            "type": type,
            "url": url
        }
        # 创建MCP管理器并获取可用工具
        mcp_manager = MCPManager(
            [convert_mcp_config(server_info)]
        )
        tools_params = await mcp_manager.show_mcp_tools()
        # 提取工具名称列表
        tools_name_str = []
        for key, tools in tools_params.items():
            for tool in tools:
                tools_name_str.append(tool["name"])
        config_enabled = True if config else False  # 检查是否启用配置

        # 使用结构化智能体生成工具描述
        structured_agent = StructuredResponseAgent(MCPResponseFormat)
        structured_response = structured_agent.get_structured_response(
            McpAsToolPrompt.format(tools_info=json.dumps(tools_params, indent=4)))

        # 调用服务层创建MCP服务器
        await MCPService.create_mcp_server(server_name, login_user.user_id, login_user.user_name, url, type, config,
                                           tools_name_str, tools_params.get(server_name), config_enabled, logo_url,
                                           structured_response.mcp_as_tool_name, structured_response.description)
        return resp_200()
    except Exception as err:
        logger.error(f"create mcp server error: {err}")
        return resp_500(message=str(err))


@router.get("/mcp_server")
async def get_mcp_servers(login_user: UserPayload = Depends(get_login_user)):
    """获取当前用户的所有MCP服务器列表"""
    try:
        # 调用服务层获取用户的所有MCP服务器
        mcp_servers = await MCPService.get_all_servers(login_user.user_id)
        return resp_200(data=mcp_servers)
    except Exception as err:
        logger.error(err)
        return resp_500(message=str(err))


@router.delete("/mcp_server")
async def delete_mcp_server(server_id: str = Body(..., description="MCP Server 的ID", embed=True),
                            login_user: UserPayload = Depends(get_login_user)):
    """删除指定的MCP服务器"""
    try:
        # 验证用户是否有权限删除该服务器
        await MCPService.verify_user_permission(server_id, login_user.user_id)

        # 调用服务层删除服务器
        await MCPService.delete_server_from_id(server_id)
        return resp_200()
    except Exception as err:
        logger.error(err)
        return resp_500(message=str(err))


@router.get("/mcp_tools")
async def get_mcp_tools(server_id: str = Body(..., description="MCP Server 的ID", embed=True),
                        login_user: UserPayload = Depends(get_login_user)):
    """获取指定MCP服务器的可用工具列表"""
    try:
        # 验证用户是否有权限访问该服务器
        await MCPService.verify_user_permission(server_id, login_user.user_id)

        # 调用服务层获取MCP工具信息
        results = await MCPService.get_mcp_tools_info(server_id)
        return resp_200(results)
    except Exception as err:
        logger.error(err)
        return resp_500(message=str(err))


@router.put("/mcp_server")
async def update_mcp_server(server_id: str = Body(..., description="MCP Server 的ID"),
                            server_name: str = Body(None, description="MCP Server的名称"),
                            url: str = Body(None, description="MCP Server 的URL"),
                            type: str = Body(None, description="MCP Server 的连接方式，SSE、Websocket"),
                            login_user: UserPayload = Depends(get_login_user)):
    """更新指定的MCP服务器信息"""
    try:
        # 验证用户是否有权限更新该服务器
        await MCPService.verify_user_permission(server_id, login_user.user_id)
        mcp_server = await MCPService.get_mcp_server_from_id(server_id)

        # 如果URL发生变化，需要重新获取工具信息
        if url != mcp_server["url"]:
            server_info = {
                "server_name": server_name,
                "type": type,
                "url": url
            }
            # 创建MCP管理器并获取新的工具参数
            mcp_manager = MCPManager([convert_mcp_config(server_info)])
            tools_params = await mcp_manager.show_mcp_tools()
            # 提取工具名称列表
            tools_str = []
            for key, tools in tools_params:
                for tool in tools:
                    tools_str.append(tool["name"])

            # 使用结构化智能体生成新的工具描述
            structured_agent = StructuredResponseAgent(MCPResponseFormat)
            structured_response = structured_agent.get_structured_response(
                McpAsToolPrompt.format(tools_info=json.dumps(tools_params, indent=4)))

            # 调用服务层更新服务器信息（包含新的工具信息）
            await MCPService.update_mcp_server(server_id, server_name, url, type,
                                               mcp_as_tool_name=structured_response.mcp_as_tool_name,
                                               description=structured_response.description, tools=tools_str,
                                               params=tools_params.get(server_name))
        else:
            # URL未变化，只更新基本信息
            await MCPService.update_mcp_server(server_id, server_name)
        return resp_200()
    except Exception as err:
        logger.error(err)
        return resp_500()
