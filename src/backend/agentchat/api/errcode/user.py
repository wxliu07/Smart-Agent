"""
用户模块错误码定义

该模块定义了用户管理相关的所有错误码，包括：
- 用户认证和验证错误
- 密码管理错误
- 用户注册和登录错误
- 用户组管理错误

功能模块代码：106
错误码范围：10600-10699
"""

from agentchat.api.errcode.base import BaseErrorCode


# 用户模块相关的返回错误码，功能模块代码：106
class UserValidateError(BaseErrorCode):
    """
    用户验证错误
    
    当用户登录时账号或密码验证失败时抛出此错误。
    """
    Code: int = 10600
    Msg: str = '账号或密码错误'


class UserPasswordExpireError(BaseErrorCode):
    """
    用户密码过期错误
    
    当用户密码已超过有效期需要修改时抛出此错误。
    """
    Code: int = 10601
    Msg: str = '您的密码已过期，请及时修改'


class UserNotPasswordError(BaseErrorCode):
    """
    用户未设置密码错误
    
    当用户账户尚未设置初始密码时抛出此错误。
    """
    Code: int = 10602
    Msg: str = '用户尚未设置密码，请先联系管理员重置密码'


class UserPasswordError(BaseErrorCode):
    """
    用户密码错误
    
    当用户输入的当前密码不正确时抛出此错误。
    """
    Code: int = 10603
    Msg: str = '当前密码错误'


class UserLoginOfflineError(BaseErrorCode):
    """
    用户登录被挤下线错误
    
    当同一账户在另一设备登录时，当前设备的会话会被强制下线。
    """
    Code: int = 10604
    Msg: str = '您的账户已在另一设备上登录，此设备上的会话已被注销。\n如果这不是您本人的操作，请尽快修改您的账户密码。'


class UserNameAlreadyExistError(BaseErrorCode):
    """
    用户名已存在错误
    
    当创建新用户时用户名已被占用时抛出此错误。
    """
    Code: int = 10605
    Msg: str = '用户名已存在'


class UserNeedGroupAndRoleError(BaseErrorCode):
    """
    用户组和角色缺失错误
    
    当创建或更新用户时未指定必要的用户组和角色信息时抛出此错误。
    """
    Code: int = 10606
    Msg: str = '用户组和角色不能为空'


class UserGroupNotDeleteError(BaseErrorCode):
    """
    用户组删除限制错误
    
    当尝试删除仍有用户归属的用户组时抛出此错误。
    """
    Code: int = 10610
    Msg: str = '用户组内还有用户，不能删除'
