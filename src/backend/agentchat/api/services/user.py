"""
用户服务模块

该模块提供用户管理相关的核心业务逻辑，包括：
- 用户认证和授权
- 密码加密和验证
- 用户信息管理
- JWT 令牌处理
- 权限验证和角色管理
"""

import json
import random

import rsa
import hashlib
from fastapi_jwt_auth import AuthJWT

from agentchat.services.aliyun_oss import aliyun_oss
from agentchat.services.redis import redis_client
from agentchat.database.dao.user_role import UserRoleDao
from agentchat.database.models.role import AdminRole
from agentchat.api.errcode.user import UserNameAlreadyExistError
from agentchat.settings import app_settings
from agentchat.utils.hash import md5_hash
from base64 import b64decode
from fastapi import Request, Depends, HTTPException
from agentchat.database.models.user import UserTable
from agentchat.database.dao.user import UserDao
from agentchat.utils.constants import RSA_KEY
from agentchat.schema.schemas import CreateUserReq
from agentchat.utils.JWT import ACCESS_TOKEN_EXPIRE_TIME


class UserPayload:
    """
    用户载荷类
    
    用于封装当前登录用户的基本信息和权限数据。
    包含用户ID、角色信息和用户名等关键信息。
    
    Attributes:
        user_id (str): 用户唯一标识
        user_role (str or list): 用户角色，管理员为'string'，普通用户为角色ID列表
        user_name (str): 用户名
    """

    def __init__(self, **kwargs):
        """
        初始化用户载荷对象
        
        Args:
            **kwargs: 包含用户信息的字典参数
                - user_id: 用户ID
                - role: 用户角色
                - user_name: 用户名
        """
        self.user_id = kwargs.get('user_id')
        self.user_role = kwargs.get('role')
        if self.user_role != 'admin':  # 非管理员用户，需要获取他的角色列表
            roles = UserRoleDao.get_user_roles(self.user_id)
            self.user_role = [one.role_id for one in roles]
        self.user_name = kwargs.get('user_name')

    def is_admin(self):
        """
        检查用户是否为管理员
        
        Returns:
            bool: 如果用户是管理员返回True，否则返回False
        """
        if self.user_role == 'admin':
            return True
        if isinstance(self.user_role, list):
            for one in self.user_role:
                if one == AdminRole:
                    return True
        return False


class UserService:
    """
    用户服务类
    
    提供用户管理的核心业务逻辑，包括用户创建、认证、密码处理等功能。
    所有方法都是类方法，可以直接通过类名调用。
    """

    @classmethod
    def decrypt_md5_password(cls, password: str):
        """
        解密并MD5加密密码
        
        首先尝试使用RSA私钥解密密码，然后进行MD5哈希处理。
        如果Redis中没有RSA密钥，则直接对密码进行MD5哈希。
        
        Args:
            password (str): 待处理的密码（可能是RSA加密的）
            
        Returns:
            str: MD5哈希后的密码
        """
        if value := redis_client.get(RSA_KEY):
            private_key = value[1]
            password = md5_hash(rsa.decrypt(b64decode(password), private_key).decode('utf-8'))
        else:
            password = md5_hash(password)
        return password

    @classmethod
    def encrypt_sha256_password(cls, password: str):
        """
        使用SHA-256算法加密密码
        
        Args:
            password (str): 原始密码
            
        Returns:
            str: SHA-256哈希后的密码
        """
        sha256 = hashlib.sha256()
        sha256.update(password.encode('utf-8'))
        encrypted_password = sha256.hexdigest()
        return encrypted_password

    @classmethod
    def verify_password(cls, password: str, encrypted_password: str):
        """
        验证密码是否匹配
        
        将输入的密码进行SHA-256加密后与存储的加密密码进行比较。
        
        Args:
            password (str): 用户输入的原始密码
            encrypted_password (str): 存储的加密密码
            
        Returns:
            bool: 密码匹配返回True，否则返回False
        """
        return cls.encrypt_sha256_password(password) == encrypted_password

    @classmethod
    def create_user(cls, request: Request, login_user: UserPayload, req_data: CreateUserReq):
        """
        创建新用户
        
        检查用户名是否已存在，如果不存在则创建新用户并分配默认角色。
        
        Args:
            request (Request): HTTP请求对象
            login_user (UserPayload): 当前登录用户信息
            req_data (CreateUserReq): 创建用户的请求数据
            
        Returns:
            UserTable: 创建的用户对象
            
        Raises:
            UserNameAlreadyExistError: 当用户名已存在时抛出
        """
        exists_user = UserDao.get_user_by_username(req_data.user_name)
        if exists_user:
            # 抛出异常
            raise UserNameAlreadyExistError.http_exception()
        user = UserTable(
            user_name=req_data.user_name,
            user_password=cls.decrypt_md5_password(req_data.password),
        )
        user = UserDao.add_user_and_default_role(user_name=user.user_name,
                                                 user_password=user.user_password)
        return user

    @classmethod
    def get_random_user_avatar(cls):
        """
        随机获取用户头像
        
        从阿里云OSS的用户头像文件夹中随机选择一个头像。
        
        Returns:
            str: 头像URL，如果没有可用头像则返回空字符串
        """
        files_url = aliyun_oss.list_files_in_folder("icons/user")
        avatars_url = []
        for file_url in files_url:
            avatars_url.append(f"{app_settings.aliyun_oss['base_url']}/{file_url}")
        return random.choice(avatars_url) if avatars_url else ""

    @classmethod
    def get_available_avatars(cls):
        """
        获取所有可用的用户头像
        
        从阿里云OSS获取用户头像文件夹中的所有头像列表。
        
        Returns:
            list: 头像URL列表
        """
        files_url = aliyun_oss.list_files_in_folder("icons/user")
        avatars_url = []
        for file_url in files_url:
            avatars_url.append(f"{app_settings.aliyun_oss['base_url']}/{file_url}")
        return avatars_url

    @classmethod
    def get_user_info_by_id(cls, user_id):
        """
        根据用户ID获取用户信息
        
        Args:
            user_id (str): 用户ID
            
        Returns:
            dict: 用户信息的字典形式
        """
        user_info = UserDao.get_user(user_id)
        return user_info.to_dict()

    @classmethod
    def update_user_info(cls, user_id, user_avatar, user_description):
        """
        更新用户信息
        
        Args:
            user_id (str): 用户ID
            user_avatar (str): 用户头像URL
            user_description (str): 用户描述
        """
        UserDao.update_user_info(user_id, user_avatar, user_description)

    @classmethod
    def get_user_id_by_name(cls, user_name):
        """
        根据用户名获取用户ID
        
        Args:
            user_name (str): 用户名
            
        Returns:
            str: 用户ID
        """
        user = UserDao.get_user_by_username(user_name)
        return user.user_id


async def get_login_user(request: Request, authorize: AuthJWT = Depends()) -> UserPayload:
    """
    获取当前登录的用户信息
    
    这是一个FastAPI依赖注入函数，用于在需要认证的API端点中获取当前用户信息。
    支持白名单路径的免认证访问。
    
    Args:
        request (Request): HTTP请求对象
        authorize (AuthJWT): JWT认证对象，由FastAPI依赖注入提供
        
    Returns:
        UserPayload: 当前登录用户的载荷对象
        
    Raises:
        HTTPException: 当JWT认证失败时抛出401异常
    """
    if request.state.is_whitelisted:
        # 白名单路径：直接返回Admin
        return UserPayload(user_id="1", user_name="Admin")

    # 非白名单路径：执行 JWT 验证
    try:
        authorize.jwt_required()
        current_user = json.loads(authorize.get_jwt_subject())
        return UserPayload(**current_user)
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")


def get_user_role(db_user: UserTable):
    """
    获取用户的角色信息
    
    查询数据库获取用户的角色列表，如果是管理员则返回'admin'，
    否则返回角色ID列表。
    
    Args:
        db_user (UserTable): 用户数据库对象
        
    Returns:
        str or list: 管理员返回'admin'字符串，普通用户返回角色ID列表
    """
    # 查询用户的角色列表
    db_user_role = UserRoleDao.get_user_roles(db_user.user_id)
    role = ""
    role_ids = []
    for user_role in db_user_role:
        if user_role.role_id == '1':
            # 是管理员，忽略其他的角色
            role = 'admin'
        else:
            role_ids.append(user_role.role_id)
    if role != "admin":
        role = role_ids

    return role


def get_user_jwt(db_user: UserTable):
    """
    为用户生成JWT令牌
    
    根据用户信息生成访问令牌和刷新令牌，用于后续的API认证。
    
    Args:
        db_user (UserTable): 用户数据库对象
        
    Returns:
        tuple: 包含三个元素的元组
            - access_token (str): JWT访问令牌
            - refresh_token (str): JWT刷新令牌
            - role (str or list): 用户角色信息
    """
    # 查询角色
    role = get_user_role(db_user)
    # 生成JWT令牌
    payload = {'user_name': db_user.user_name, 'user_id': db_user.user_id, 'role': role}

    access_token = AuthJWT().create_access_token(subject=json.dumps(payload), expires_time=ACCESS_TOKEN_EXPIRE_TIME)

    refresh_token = AuthJWT().create_refresh_token(subject=db_user.user_name)

    # Set the JWT cookies in the response
    return access_token, refresh_token, role
