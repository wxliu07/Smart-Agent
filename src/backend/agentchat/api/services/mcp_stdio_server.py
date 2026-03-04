"""
MCP STDIO 服务器服务模块

该模块提供 MCP STDIO 服务器管理的核心业务逻辑，包括：
- MCP STDIO 服务器的创建、查询、更新和删除
- 服务器路径和命令配置
- 服务器环境变量管理
- 服务器权限验证

所有方法都是类方法，可以直接通过类名调用。
"""

from agentchat.database.dao.mcp_stdio_server import MCPServerStdioDao
from agentchat.database.models.user import AdminUser
from loguru import logger

class MCPServerService:
    """
    MCP STDIO 服务器服务类
    
    提供 MCP STDIO 服务器管理的核心业务逻辑，包括服务器的 CRUD 操作和配置管理。
    所有方法都是类方法，可以直接通过类名调用。
    """

    @classmethod
    def create_mcp_server(cls, name: str, mcp_server_path: str,
                          user_id: str, mcp_server_command: str, mcp_server_env: str):
        return MCPServerStdioDao.create_mcp_server(mcp_server_path, mcp_server_command, user_id, name, mcp_server_env)

    @classmethod
    def get_mcp_servers(cls, user_id):
        mcp_servers = MCPServerStdioDao.get_mcp_servers(user_id)
        results = []
        for server in mcp_servers:
            results.append(server)
        return results

    @classmethod
    def delete_mcp_server(cls, user_id, mcp_server_id):
        mcp_server_user = cls.get_mcp_server_user(mcp_server_id)
        if user_id in (mcp_server_user, AdminUser):
            return MCPServerStdioDao.delete_mcp_server(mcp_server_id)
        else:
            logger.error("No Permission Exec Delete MCP Server")
            raise ValueError("No Permission Exec Delete MCP Server")

    @classmethod
    def update_mcp_server(cls, mcp_server_id, mcp_server_path, name,
                          user_id, mcp_server_command, mcp_server_env):
        mcp_server_user = cls.get_mcp_server_user(mcp_server_id)
        if user_id in (mcp_server_user, AdminUser):
           return MCPServerStdioDao.update_mcp_server(mcp_server_id, mcp_server_path, mcp_server_command, name, mcp_server_env)
        else:
            logger.error("No Permission Exec Update MCP Server")
            raise ValueError("No Permission Exec Update MCP Server")

    @classmethod
    def get_mcp_server_user(cls, mcp_server_id):
        mcp_server = MCPServerStdioDao.get_mcp_server_by_id(mcp_server_id)
        return mcp_server.user_id

    @classmethod
    def get_mcp_server_from_id(cls, server_id):
        mcp_server = MCPServerStdioDao.get_mcp_server_by_id(server_id)
        return mcp_server.to_dict()