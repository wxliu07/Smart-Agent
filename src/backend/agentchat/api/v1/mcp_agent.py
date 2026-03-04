"""
该文件已废弃!!!
MCP Agent管理API路由模块
提供已废弃的MCP智能体创建、查询、更新、删除等RESTful接口
"""
from typing import List
from loguru import logger
from uuid import uuid4
from fastapi import APIRouter, Form, UploadFile, File, Depends

from agentchat.api.services.mcp_agent import MCPAgentService
from agentchat.schema.schemas import resp_200, resp_500, UnifiedResponseModel
from agentchat.settings import app_settings
from agentchat.api.services.user import UserPayload, get_login_user

# 创建MCP Agent相关的API路由器，标签为"MCP-Agent"
router = APIRouter(tags=["MCP-Agent"])


@router.post("/mcp_agent", response_model=UnifiedResponseModel)
async def create_mcp_agent(name: str = Form(...),
                           description: str = Form(...),
                           mcp_servers_id: List[str] = Form(default=[], description="绑定的工具id"),
                           llm_id: str = Form(None),
                           knowledges_id: List[str] = Form(default=[], description="绑定的知识库ID"),
                           enable_memory: bool = Form(True),
                           logoFile: UploadFile = File(None),
                           login_user: UserPayload = Depends(get_login_user)):
    try:
        # 判断Agent名字是否重复
        if MCPAgentService.check_repeat_name(name=name, user_id=login_user.user_id):
            return resp_500(message="The Agent name is repeated, please change it")

        # 保存头像文件到本地
        uid = uuid4().hex
        if logoFile is not None:
            ext = logoFile.content_type.split('/')[-1]  # 获取文件扩展名
            logo = f"img/mcp_agent/{uid}.{ext}"  # 生成唯一文件名
            with open(logo, 'wb') as file:
                file.write(await logoFile.read())
        else:
            logo = app_settings.logo.get('mcp_agent')

        # 调用服务层创建MCP Agent
        MCPAgentService.create_mcp_agent(name=name,
                                         description=description,
                                         logo=logo,
                                         mcp_servers_id=mcp_servers_id,
                                         llm_id=llm_id,
                                         user_id=login_user.user_id,
                                         knowledges_id=knowledges_id,
                                         enable_memory=enable_memory)
        return resp_200()
    except Exception as err:
        logger.error(f"create agent API error: {err}")
        return resp_500(message=str(err))


@router.get("/mcp_agent", response_model=UnifiedResponseModel)
async def get_mcp_agent(login_user: UserPayload = Depends(get_login_user)):
    """获取当前用户的所有MCP Agent列表"""
    try:
        # 调用服务层获取用户的所有MCP Agent
        data = MCPAgentService.get_all_mcp_agent_by_user(user_id=login_user.user_id)
        result = []
        # 构建返回数据，包含头像完整URL
        for item in data:
            result.append({"id": item.id,
                           "name": item.name,
                           "description": item.description,
                           "logo": app_settings.logo.get('prefix') + item.logo,  # 拼接头像完整URL
                           "mcp_servers_id": item.mcp_servers_id,
                           "llm_id": item.llm_id,
                           "is_custom": item.is_custom,
                           "enable_memory": item.enable_memory,
                           "create_time": item.create_time})

        return resp_200(data=result)
    except Exception as err:
        logger.error(f"get agent API error: {err}")
        return resp_500(message=str(err))


@router.delete("/mcp_agent", response_model=UnifiedResponseModel)
async def delete_mcp_agent(agent_id: str = Form(...),
                           login_user: UserPayload = Depends(get_login_user)):
    """删除指定的MCP Agent"""
    try:
        # 调用服务层删除指定ID的MCP Agent
        return MCPAgentService.delete_mcp_agent_by_id(id=agent_id, user_id=login_user.user_id)
    except Exception as err:
        logger.error(f"delete agent API error: {err}")
        return resp_500(message=str(err))


@router.put("/mcp_agent", response_model=UnifiedResponseModel)
async def update_mcp_agent(agent_id: str = Form(...),
                           name: str = Form(None),
                           description: str = Form(None),
                           mcp_servers_id: List[str] = Form(None),
                           knowledges_id: List[str] = Form(None),
                           llm_id: str = Form(None),
                           enable_memory: bool = Form(True),
                           logoFile: UploadFile = File(None),
                           login_user: UserPayload = Depends(get_login_user)):
    """更新指定的MCP Agent信息"""
    try:
        # 检查名称是否重复
        if name and MCPAgentService.check_repeat_name(name, login_user.user_id):
            return resp_500(message='agent name repeated')

        # 处理头像文件上传
        uid = uuid4().hex
        if logoFile is not None:
            logo = f"img/mcp_agent/{uid}.{logoFile.content_type.split('/')[-1]}"  # 生成唯一文件名
            with open(logo, 'wb') as file:
                file.write(await logoFile.read())
        else:
            logo = None

        # 调用服务层更新MCP Agent
        return MCPAgentService.update_mcp_agent_by_id(id=agent_id,
                                                      name=name,
                                                      description=description,
                                                      logo=logo,
                                                      knowledges_id=knowledges_id,
                                                      user_id=login_user.user_id,
                                                      mcp_servers_id=mcp_servers_id,
                                                      llm_id=llm_id,
                                                      enable_memory=enable_memory)

    except Exception as err:
        logger.error(f"update agent API error: {err}")
        return resp_500(message=str(err))


@router.post("/mcp_agent/search", response_model=UnifiedResponseModel)
async def search_mcp_agent(name: str = Form(...),
                           login_user: UserPayload = Depends(get_login_user)):
    """根据名称搜索MCP Agent"""
    try:
        # 调用服务层按名称搜索MCP Agent
        data = MCPAgentService.search_mcp_agent_name(name=name, user_id=login_user.user_id)
        result = []
        # 构建返回数据，包含头像完整URL
        for item in data:
            result.append({"id": item.id,
                           "name": item.name,
                           "description": item.description,
                           "logo": app_settings.logo.get('prefix') + item.logo,  # 拼接头像完整URL
                           "mcp_servers_id": item.mcp_servers_id,
                           "llm_id": item.llm_id,
                           "enable_memory": item.enable_memory,
                           "is_custom": item.is_custom,
                           "create_time": item.create_time})

        return resp_200(data=result)
    except Exception as err:
        logger.error(f"search agent API error: {err}")
        return resp_500(message=str(err))
