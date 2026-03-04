"""
知识库文件管理 API 端点模块

该模块提供知识库文件管理相关的 REST API 端点，包括：
- 文件上传和下载
- 文件解析和索引
- 文件状态管理
- 文件权限验证

支持的功能：
- 多格式文件上传
- 文件自动解析和向量化
- 文件状态跟踪
- OSS 云存储集成
"""

import os
from urllib.parse import urlparse
from fastapi import FastAPI, APIRouter, Body, Depends, Query

from agentchat.services.aliyun_oss import aliyun_oss
from agentchat.api.services.knowledge_file import KnowledgeFileService
from agentchat.api.services.knowledge import KnowledgeService
from agentchat.api.services.user import get_login_user, UserPayload
from agentchat.schema.schemas import UnifiedResponseModel, resp_200, resp_500
from agentchat.utils.file_utils import get_save_tempfile

router = APIRouter(tags=["Knowledge-File"])


@router.post('/knowledge_file/create', response_model=UnifiedResponseModel)
async def upload_file(knowledge_id: str = Body(..., description="知识库的ID"),
                      file_url: str = Body(..., description="文件上传后返回的URL"),
                      login_user: UserPayload = Depends(get_login_user)):
    try:
        # 获取本地临时文件路径
        file_name = file_url.split("/")[-1]
        local_file_path = get_save_tempfile(file_name)
        # 根据URL解析出对应的object name
        parsed = urlparse(file_url)
        object_key = parsed.path.lstrip('/')
        aliyun_oss.download_file(object_key, local_file_path)
        # 获得文件的字节数
        file_size_bytes = os.path.getsize(local_file_path)

        name_part, ext_part = file_name.rsplit('.', 1) if '.' in file_name else (file_name, '')
        parts = name_part.split("_")
        file_name = "_".join(parts[:-1]) + f".{ext_part}"

        await KnowledgeFileService.create_knowledge_file(file_name, local_file_path, knowledge_id, login_user.user_id, file_url, file_size_bytes)
        return resp_200()
    except Exception as err:
        return resp_500(message=str(err))


@router.get('/knowledge_file/select', response_model=UnifiedResponseModel)
async def select_knowledge_file(knowledge_id: str = Query(...),
                                login_user: UserPayload = Depends(get_login_user)):
    try:
        # 验证用户权限
        await KnowledgeService.verify_user_permission(knowledge_id, login_user.user_id)

        results = await KnowledgeFileService.get_knowledge_file(knowledge_id)
        return resp_200(data=results)
    except Exception as err:
        return resp_500(message=str(err))


@router.delete('/knowledge_file/delete', response_model=UnifiedResponseModel)
async def delete_knowledge_file(knowledge_file_id: str = Body(..., embed=True),
                                login_user: UserPayload = Depends(get_login_user)):
    try:
        # 验证用户权限
        await KnowledgeFileService.verify_user_permission(knowledge_file_id, login_user.user_id)

        await KnowledgeFileService.delete_knowledge_file(knowledge_file_id)
        return resp_200()
    except Exception as err:
        return resp_500(message=str(err))

@router.get("/knowledge_file/status", response_model=UnifiedResponseModel)
async def get_knowledge_file_status(knowledge_file_id: str = Body(..., embed=True),
                                login_user: UserPayload = Depends(get_login_user)):
    try:
        # 验证用户权限
        await KnowledgeFileService.verify_user_permission(knowledge_file_id, login_user.user_id)
        knowledge_file = await KnowledgeFileService.select_knowledge_file_by_id(knowledge_file_id)
        return resp_200(data=knowledge_file.to_dict())
    except Exception as err:
        return resp_500(message=str(err))