"""
工作空间会话服务模块

该模块提供工作空间会话管理的核心业务逻辑，包括：
- 会话的创建、查询、更新和删除
- 会话上下文管理
- 会话历史记录
- 用户会话状态维护

所有方法都是类方法，可以直接通过类名调用。
"""

from typing import List

from agentchat.database.dao.workspace_session import WorkSpaceSession, WorkSpaceSessionDao
from agentchat.database.models.workspace_session import WorkSpaceSessionCreate


class WorkSpaceSessionService:
    """
    工作空间会话服务类
    
    提供工作空间会话管理的核心业务逻辑，包括会话的 CRUD 操作和上下文管理。
    所有方法都是类方法，可以直接通过类名调用。
    """

    @classmethod
    async def create_workspace_session(cls, session_create: WorkSpaceSessionCreate):
        workspace_session = WorkSpaceSession(**session_create.model_dump())
        return await WorkSpaceSessionDao.create_workspace_session(workspace_session)

    @classmethod
    async def get_workspace_sessions(cls, user_id):
        results = await WorkSpaceSessionDao.get_workspace_sessions(user_id)
        results.sort(key=lambda x: x.update_time, reverse=True)
        return [result.to_dict() for result in results]

    @classmethod
    async def delete_workspace_session(cls, session_ids, user_id):
        await WorkSpaceSessionDao.delete_workspace_session(session_ids, user_id)

    @classmethod
    async def update_workspace_session_contexts(cls, session_id, session_context):
        return await WorkSpaceSessionDao.update_workspace_session_contexts(session_id, session_context)

    @classmethod
    async def clear_workspace_session_contexts(cls, session_id):
        return await WorkSpaceSessionDao.clear_workspace_session_contexts(session_id)

    @classmethod
    async def get_workspace_session_from_id(cls, session_id, user_id):
        result = await WorkSpaceSessionDao.get_workspace_session_from_id(session_id)
        if result is None:
            return None
        return result.to_dict()

    @classmethod
    async def generate_session_title(cls, user_query):
        pass