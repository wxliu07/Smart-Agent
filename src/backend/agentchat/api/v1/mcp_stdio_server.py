"""
MCP Stdio服务器管理API路由模块
提供基于标准输入输出的MCP服务器创建、查询、更新、删除等RESTful接口
支持本地MCP服务器的命令行管理和环境配置
"""
from fastapi import APIRouter, Body, Depends
from loguru import logger

from agentchat.api.services.mcp_stdio_server import MCPServerService
from agentchat.api.services.user import UserPayload, get_login_user
from agentchat.schema.schemas import resp_200, resp_500

# 创建MCP Stdio服务器相关的API路由器，标签为"MCP-Stdio-Server"
router = APIRouter(tags=["MCP-Stdio-Server"])


@router.post("/mcp_stdio_server")
async def create_mcp_server(
        name: str = Body(),
        mcp_server_env: str = Body(None),
        mcp_server_path: str = Body(),
        mcp_server_command: str = Body(),
        login_user: UserPayload = Depends(get_login_user)):
    """创建新的MCP Stdio服务器"""
    try:
        # 调用服务层创建MCP Stdio服务器
        MCPServerService.create_mcp_server(name, mcp_server_path,
                                           login_user.user_id, mcp_server_command, mcp_server_env)
        return resp_200()
    except Exception as err:
        logger.error(f"Create MCP Server Error: {err}")
        return resp_500(data=str(err))


@router.get("/mcp_stdio_server")
async def get_mcp_servers(login_user: UserPayload = Depends(get_login_user)):
    """获取当前用户的所有MCP Stdio服务器列表"""
    try:
        # 调用服务层获取用户的所有MCP Stdio服务器
        mcp_servers = MCPServerService.get_mcp_servers(login_user.user_id)
        results = []
        # 构建返回数据
        for server in mcp_servers:
            results.append({
                "user_id": server.user_id,
                "name": server.name,
                "mcp_server_env": server.mcp_server_env,
                "mcp_server_id": server.mcp_server_id,
                "mcp_server_path": server.mcp_server_path,
                "mcp_server_command": server.mcp_server_command,
                "create_time": server.create_time
            })
        return resp_200(data=results)
    except Exception as err:
        logger.error(f"Get MCP Server Error: {err}")
        return resp_500(data=str(err))


@router.delete("/mcp_stdio_server")
async def delete_mcp_server(mcp_server_id: str = Body(embed=True),
                            login_user: UserPayload = Depends(get_login_user)):
    """删除指定的MCP Stdio服务器"""
    try:
        # 调用服务层删除MCP Stdio服务器
        MCPServerService.delete_mcp_server(login_user.user_id, mcp_server_id)
        return resp_200()
    except Exception as err:
        logger.error(f"Delete MCP Server Error: {err}")
        return resp_500(data=str(err))


@router.put("/mcp_stdio_server")
async def update_mcp_server(
        mcp_server_id: str = Body(...),
        name: str = Body(None),
        mcp_server_command: str = Body(None),
        mcp_server_path: str = Body(None),
        mcp_server_env: str = Body(None),
        login_user: UserPayload = Depends(get_login_user)):
    try:
        MCPServerService.update_mcp_server(mcp_server_id, mcp_server_path, name,
                                           login_user.user_id, mcp_server_command, mcp_server_env)
        return resp_200()
    except Exception as err:
        logger.error(f"Update MCP Server Error: {err}")
        return resp_500(data=str(err))
