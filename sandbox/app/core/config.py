from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
class Settings(BaseSettings):
    """沙箱api访问基础配置信息"""
    log_level: str = "INFO" #日志等级
    server_timeout_minutes: int = 60 #访问超时时间 单位是分钟

    #使用pydantic v2提供的写法完成环境变量信息的声明
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings()->Settings:
    return Settings()