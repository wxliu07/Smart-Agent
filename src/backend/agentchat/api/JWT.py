"""
JWT 认证配置模块

该模块定义了 JWT (JSON Web Token) 认证相关的配置参数。
使用 Pydantic 的 BaseSettings 类来管理配置，支持从环境变量读取配置。
"""

from pydantic.v1 import BaseSettings


# JWT 认证配置类
# 继承自 Pydantic 的 BaseSettings，支持从环境变量自动加载配置
class Settings(BaseSettings):
    """
    JWT 认证配置设置类
    
    Attributes:
        authjwt_secret_key (str): JWT 签名密钥，用于验证 token 的真实性
        authjwt_token_location (list): token 存储位置，支持从 cookies 和 headers 中获取
        authjwt_cookie_csrf_protect (bool): 是否启用 cookie CSRF 保护，默认关闭
    """
    # JWT 签名密钥，生产环境中应该从环境变量读取
    authjwt_secret_key: str = 'secret'
    # token 可以从 cookies 和 headers 两个位置获取
    authjwt_token_location: list = ['cookies', 'headers']
    # 禁用 cookie CSRF 保护（简化开发环境配置）
    authjwt_cookie_csrf_protect: bool = False
