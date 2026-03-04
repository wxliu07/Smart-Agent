"""
MCP用户配置管理API路由模块
提供MCP服务器的用户个性化配置创建、查询、更新、删除等RESTful接口
支持用户对MCP服务器的自定义配置管理
"""
from typing import Optional
from loguru import logger
from fastapi import APIRouter, Depends, Body

from agentchat.schema.schemas import UnifiedResponseModel, resp_200, resp_500
from agentchat.api.services.user import get_login_user, UserPayload
from agentchat.api.services.mcp_user_config import MCPUserConfigService
from agentchat.schema.mcp_user_config import MCPUserConfigCreateRequest, MCPUserConfigUpdateRequest

# 创建MCP用户配置相关的API路由器，标签为"MCP-User-Config"
router = APIRouter(tags=["MCP-User-Config"])

@router.post('/mcp_user_config/create', response_model=UnifiedResponseModel)
async def create_mcp_user_config(*,
                               config_request: MCPUserConfigCreateRequest,
                               login_user: UserPayload = Depends(get_login_user)):
    """创建MCP服务器用户配置"""
    try:
        # 调用服务层创建用户配置
        results = await MCPUserConfigService.create_mcp_user_config(
            mcp_server_id=config_request.mcp_server_id,
            user_id=login_user.user_id,
            config=config_request.config
        )
        return resp_200(data=results)
    except Exception as err:
        logger.error(err)
        return resp_500(message=str(err))

@router.get('/mcp_user_config/{config_id}', response_model=UnifiedResponseModel)
async def get_mcp_user_config_by_id(config_id: str,
                                   login_user: UserPayload = Depends(get_login_user)):
    """根据配置ID获取MCP用户配置详情"""
    try:
        # 调用服务层根据ID获取用户配置
        results = await MCPUserConfigService.get_mcp_user_config_from_id(config_id=config_id)
        return resp_200(data=results)
    except Exception as err:
        logger.error(err)
        return resp_500(message=str(err))

@router.put('/mcp_user_config/update', response_model=UnifiedResponseModel)
async def update_mcp_user_config(*,
                                config_request: MCPUserConfigUpdateRequest,
                                login_user: UserPayload = Depends(get_login_user)):
    """更新MCP用户配置"""
    try:
        # 调用服务层更新用户配置
        await MCPUserConfigService.update_mcp_user_config(
            mcp_server_id=config_request.server_id,
            user_id=login_user.user_id,
            config=config_request.config
        )
        return resp_200()
    except Exception as err:
        logger.error(err)
        return resp_500(message=str(err))

@router.delete('/mcp_user_config/delete', response_model=UnifiedResponseModel)
async def delete_mcp_user_config(config_id: str = Body(embed=True, description='配置ID'),
                                login_user: UserPayload = Depends(get_login_user)):
    """删除指定的MCP用户配置"""
    try:
        # 调用服务层删除用户配置
        await MCPUserConfigService.delete_mcp_user_config(config_id=config_id)
        return resp_200()
    except Exception as err:
        logger.error(err)
        return resp_500(message=str(err))

@router.get('/mcp_user_config', response_model=UnifiedResponseModel)
async def get_mcp_user_config(*,
                             server_id: str,
                             login_user: UserPayload = Depends(get_login_user)):
    """获取指定MCP服务器的用户配置"""
    try:
        # 调用服务层获取用户在指定服务器的配置
        results = await MCPUserConfigService.show_mcp_user_config(
            user_id=login_user.user_id,
            mcp_server_id=server_id
        )
        return resp_200(data=results)
    except Exception as err:
        logger.error(err)
        return resp_500(message=str(err))
