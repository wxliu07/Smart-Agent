"""
基础错误码定义模块

该模块定义了系统中所有错误码的基础类和通用错误类型。
提供了统一的错误响应格式和 HTTP 异常处理机制。
"""

from fastapi.exceptions import HTTPException

from agentchat.schema.schemas import UnifiedResponseModel


class BaseErrorCode:
    """
    基础错误码类
    
    所有业务错误码的基类，定义了错误码的标准格式和处理方法。
    
    错误码规则：
    - 前三位数字代表具体功能模块
    - 后两位数字表示模块内部的具体错误
    - 例如：10001 表示第 100 模块的第 01 号错误
    
    Attributes:
        Code (int): 错误状态码
        Msg (str): 错误消息描述
    """
    # 错误状态码
    Code: int
    # 错误消息描述
    Msg: str

    @classmethod
    def return_resp(cls, msg: str = None, data: any = None) -> UnifiedResponseModel:
        """
        返回统一格式的错误响应
        
        Args:
            msg (str, optional): 自定义错误消息，如果不提供则使用默认消息
            data (any, optional): 响应数据，通常为 None
            
        Returns:
            UnifiedResponseModel: 统一格式的响应模型
        """
        return UnifiedResponseModel(status_code=cls.Code, status_message=msg or cls.Msg, data=data)

    @classmethod
    def http_exception(cls, msg: str = None) -> HTTPException:
        """
        返回 HTTP 异常对象
        
        Args:
            msg (str, optional): 自定义错误消息，如果不提供则使用默认消息
            
        Returns:
            HTTPException: FastAPI HTTP 异常对象
        """
        return HTTPException(status_code=cls.Code, detail=msg or cls.Msg)


class UnAuthorizedError(BaseErrorCode):
    """
    未授权访问错误
    
    当用户尝试访问需要权限的资源但未通过认证时抛出此错误。
    """
    Code: int = 403
    Msg: str = '暂无操作权限'


class NotFoundError(BaseErrorCode):
    """
    资源不存在错误
    
    当请求的资源在系统中不存在时抛出此错误。
    """
    Code: int = 404
    Msg: str = '资源不存在'
