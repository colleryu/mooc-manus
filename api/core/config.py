

from typing import Optional

from pydantic_settings import BaseSettings,SettingsConfigDict

from functools import lru_cache

class Settings(BaseSettings):
    """MoocManus后端中控配置信息，从.env或环境变量中获取"""

    #项目配置
    env : str = "development"
    log_level : str = "INFO"
    log_file : str = "logs/api.log"  # 文件日志路径；置空字符串则仅输出到控制台
    app_config_filepath:str = "config.yaml"

    #数据库相关配置
    sqlalchemy_database_url : str = "postgresql+asyncpg://postgres:postgres@localhost:5432/manus"

    #Redis相关配置
    redis_host : str = "localhost"
    redis_port : int = 6379
    redis_db : int = 0
    redis_password:str |None = None

    #Cos腾讯云对象存储配置
    cos_secret_id: str = ""
    cos_secret_key: str =""
    cos_region:str=""
    cos_scheme:str="https"
    cos_bucket:str = ""
    cos_domain:str = ""

    #Sandbox配置
    sandbox_address: Optional[str] = None
    sandbox_image: Optional[str] = None
    sandbox_name_prefix:Optional[str] = None
    sandbox_ttl_minutes: Optional[int] = 60 #分钟
    sandbox_network: Optional[str] = None
    sandbox_chrome_args:Optional[str] = ""
    sandbox_https_proxy: Optional[str] = None
    sandbox_http_proxy: Optional[str] = None
    sandbox_no_proxy: Optional[str] = None

    #使用pydantic v2的写法来完成环境变量信息的告知
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings()->Settings:
    """读取项目配置信息，并缓存，不会重复读取"""
    settings = Settings()
    return settings