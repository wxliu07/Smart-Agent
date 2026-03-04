"""
消息服务模块

该模块提供消息管理的核心业务逻辑，包括：
- 消息点赞功能
- 消息踩踏功能
- 消息统计和分析
- 用户反馈收集

所有方法都是类方法，可以直接通过类名调用。
"""

from agentchat.database.dao.message import MessageDownDao, MessageLikeDao
from loguru import logger


class MessageLikeService:
    """
    消息点赞服务类
    
    提供消息点赞功能的管理，包括点赞记录的创建和查询。
    所有方法都是类方法，可以直接通过类名调用。
    """

    @classmethod
    def create_message_like(cls, user_input: str, agent_output: str):
        try:
            MessageLikeDao.create_message_like(user_input=user_input, agent_output=agent_output)

        except Exception as err:
            logger.error(f"create message like is appear error: {err}")

    @classmethod
    def get_message_like(cls):
        try:
            data = MessageLikeDao.get_message_like()
            result = []
            for item in data:
                result.append(item)
            return result
        except Exception as err:
            logger.error(f"get message like is appear error: {err}")

class MessageDownService:
    """
    消息踩踏服务类
    
    提供消息踩踏功能的管理，包括踩踏记录的创建和查询。
    所有方法都是类方法，可以直接通过类名调用。
    """

    @classmethod
    def create_message_down(cls, user_input: str, agent_output: str):
        try:
            MessageDownDao.create_message_down(user_input=user_input, agent_output=agent_output)

        except Exception as err:
            logger.error(f"create message down is appear error: {err}")

    @classmethod
    def get_message_down(cls):
        try:
            data = MessageDownDao.get_message_down()
            result = []
            for item in data:
                result.append(item)
            return result
        except Exception as err:
            logger.error(f"get message down is appear error: {err}")
