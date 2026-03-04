"""
大语言模型管理 API 端点模块

该模块提供大语言模型 (LLM) 相关的 REST API 端点，包括：
- LLM 模型的创建、查询、更新和删除
- 模型配置管理（API密钥、基础URL等）
- 模型类型和提供商管理
- 用户权限验证

支持的模型类型：
- OpenAI GPT 系列
- Claude 系列
- 本地部署模型
- 其他兼容 OpenAI API 的模型
"""

from typing import Optional
from loguru import logger
from fastapi import APIRouter, Depends, Body
from agentchat.api.services.user import get_login_user, UserPayload
from agentchat.schema.common import CreateLLMRequest, UpdateLLMRequest
from agentchat.schema.schemas import UnifiedResponseModel, resp_200, resp_500

from agentchat.api.services.llm import LLMService, LLM_Types

# 创建LLM相关的路由器，设置标签为 "LLM"
router = APIRouter(tags=["LLM"])


@router.post('/llm/create', response_model=UnifiedResponseModel)
async def create_llm(*,
                     llm_request: CreateLLMRequest = Body(),
                     login_user: UserPayload = Depends(get_login_user)):
    """
    创建新的大语言模型配置
    
    根据用户提供的配置信息创建一个新的 LLM 模型配置，
    包括模型名称、API密钥、基础URL、提供商等信息。
    
    Args:
        llm_request (CreateLLMRequest): 创建LLM的请求参数
        login_user (UserPayload): 当前登录用户信息
        
    Returns:
        UnifiedResponseModel: 创建结果，成功返回200状态码
        
    Raises:
        Exception: 当创建过程中出现错误时抛出
    """
    try:
        await LLMService.create_llm(model=llm_request.model, api_key=llm_request.api_key,
                                    base_url=llm_request.base_url,
                                    user_id=login_user.user_id, provider=llm_request.provider,
                                    llm_type=llm_request.llm_type)
        return resp_200()
    except Exception as err:
        logger.error(err)
        return resp_500(message=str(err))


@router.delete('/llm/delete', response_model=UnifiedResponseModel)
async def delete_llm(llm_id: str = Body(embed=True, description='大模型的ID'),
                     login_user: UserPayload = Depends(get_login_user)):
    try:
        # 验证用户权限
        await LLMService.verify_user_permission(llm_id, login_user.user_id)

        await LLMService.delete_llm(llm_id=llm_id)
        return resp_200()
    except Exception as err:
        logger.error(err)
        return resp_500(message=str(err))


@router.put('/llm/update', response_model=UnifiedResponseModel)
async def update_llm(*,
                     llm_request: UpdateLLMRequest = Body(),
                     login_user: UserPayload = Depends(get_login_user)):
    try:
        # 验证用户权限
        await LLMService.verify_user_permission(llm_request.llm_id, login_user.user_id)

        await LLMService.update_llm(model=llm_request.model, api_key=llm_request.api_key,
                                    llm_id=llm_request.llm_id, provider=llm_request.provider,
                                    base_url=llm_request.base_url, llm_type=llm_request.llm_type)

        return resp_200()
    except Exception as err:
        logger.error(err)
        return resp_500(message=str(err))


@router.get('/llm/all', response_model=UnifiedResponseModel)
async def get_all_llm(login_user: UserPayload = Depends(get_login_user)):
    try:
        result = await LLMService.get_all_llm(login_user.user_id)
        return resp_200(data=result)
    except Exception as err:
        logger.error(err)
        return resp_500(message=str(err))


@router.post('/llm/personal', response_model=UnifiedResponseModel)
async def get_personal_llm(login_user: UserPayload = Depends(get_login_user)):
    try:
        result = await LLMService.get_personal_llm(user_id=login_user.user_id)
        return resp_200(data=result)
    except Exception as err:
        logger.error(err)
        return resp_500(message=str(err))


@router.post('/llm/visible', response_model=UnifiedResponseModel)
async def get_visible_llm(login_user: UserPayload = Depends(get_login_user)):
    try:
        result = await LLMService.get_visible_llm(user_id=login_user.user_id)
        return resp_200(data=result)
    except Exception as err:
        logger.error(err)
        return resp_500(message=str(err))

@router.get("/agent/models", response_model=UnifiedResponseModel)
async def get_all_agent_models(login_user: UserPayload = Depends(get_login_user)):
    try:
        result = await LLMService.get_visible_llm(user_id=login_user.user_id)
        return resp_200(data=result["LLM"])
    except Exception as err:
        logger.error(err)
        return resp_500(message=str(err))


@router.get('llm/schema', response_model=UnifiedResponseModel)
async def get_llm_type(login_user: UserPayload = Depends(get_login_user)):
    return resp_200(data=LLM_Types)

# ❌ 2024-630---->2025-630版本（已退休）❌
# @router.post('/llm/create', response_model=UnifiedResponseModel)
# async def create_llm(model: str = Body(description='大模型的名称'),
#                      api_key: str = Body(description='大模型的key'),
#                      base_url: str = Body(description='大模型的url'),
#                      llm_type: str = Body(description='模型的种类，LLM、Embedding？'),
#                      provider: str = Body(description='大模型的提供商'),
#                      login_user: UserPayload = Depends(get_login_user)):
#
#     return LLMService.create_llm(model=model, api_key=api_key, base_url=base_url,
#                                  user_id=login_user.user_id, provider=provider, llm_type=llm_type)
#
# @router.delete('/llm/delete', response_model=UnifiedResponseModel)
# async def delete_llm(llm_id: str = Body(embed=True, description='大模型的ID'),
#                      login_user: UserPayload = Depends(get_login_user)):
#     return LLMService.delete_llm(llm_id=llm_id, user_id=login_user.user_id)
#
# @router.put('/llm/update', response_model=UnifiedResponseModel)
# async def update_llm(model: Optional[str] = Body(description='大模型的名称'),
#                      api_key: Optional[str] = Body(description='大模型的key'),
#                      base_url: Optional[str] = Body(description='大模型的url'),
#                      provider: Optional[str] = Body(description='大模型的提供商'),
#                      llm_type: Optional[str] = Body(description='模型的类型'),
#                      llm_id: str = Body(description='大模型的ID'),
#                      login_user: UserPayload = Depends(get_login_user)):
#
#     return LLMService.update_llm(user_id=login_user.user_id, model=model, api_key=api_key,
#                                  llm_id=llm_id, provider=provider, base_url=base_url, llm_type=llm_type)
#
# @router.get('/llm/all', response_model=UnifiedResponseModel)
# async def get_all_llm(login_user: UserPayload = Depends(get_login_user)):
#     return LLMService.get_all_llm()
#
# @router.post('/llm/personal', response_model=UnifiedResponseModel)
# async def get_personal_llm(login_user: UserPayload = Depends(get_login_user)):
#     return LLMService.get_personal_llm(user_id=login_user.user_id)
#
# @router.post('/llm/visible', response_model=UnifiedResponseModel)
# async def get_visible_llm(login_user: UserPayload = Depends(get_login_user)):
#     return LLMService.get_visible_llm(user_id=login_user.user_id)
#
# # @router.get('/llm/provider', response_model=UnifiedResponseModel)
# # async def get_provider(login_user: UserPayload = Depends(get_login_user)):
# #     return resp_200(data=(Function_Call_provider + React_provider))
#
# @router.get('llm/schema', response_model=UnifiedResponseModel)
# async def get_llm_type(login_user: UserPayload = Depends(get_login_user)):
#     return resp_200(data=LLM_Types)
