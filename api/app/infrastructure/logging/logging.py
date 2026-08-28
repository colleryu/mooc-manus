
import logging
import os
import re
import sys

from core.config import get_settings

# 需要在运行级别之上保持安静的第三方库，避免输出完整 SQL、HTTP 请求体和 MCP Schema
_NOISY_LOGGERS = [
    "sqlalchemy.engine",
    "sqlalchemy.pool",
    "httpcore",
    "httpx",
    "httpx2",
    "mcp.client",
    "mcp.server",
    "qcloud_cos",
    "qcloud_cos.cos_client",
]

_SENSITIVE_KEY_RE = re.compile(
    r"(?i)\b(api[_-]?key|apikey|access[_-]?key|secret[_-]?key|"
    r"token|authorization|secret|password|cookie|key)\b"
    r"(\s*[:=]\s*)"
    r"(\"(?:[^\"\\]|\\.)*\"|'[^']*'|[^\s,;&]+)"
)


class SensitiveDataFilter(logging.Filter):
    """日志脱敏过滤器，隐藏 API Key、token、cookie 等敏感信息。"""

    @classmethod
    def _redact(cls, text: str) -> str:
        return _SENSITIVE_KEY_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}***", text)

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        if isinstance(msg, str):
            redacted = self._redact(msg)
            if redacted != msg:
                record.msg = redacted
                record.args = None
        return True


def setup_logging():
    """配置MoocManus项目的日志系统，涵盖日志等级、输出与脱敏。"""
    settings = get_settings()

    root_logger = logging.getLogger()

    # 默认运行级别 INFO，避免 DEBUG 输出完整 SQL、HTTP Core 和工具结果
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    root_logger.setLevel(log_level)

    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)
    console_handler.addFilter(SensitiveDataFilter())

    root_logger.addHandler(console_handler)

    # 文件日志：便于追溯 SSE 断连等需要事后排查的问题。同样应用脱敏过滤器，
    # 避免密钥等敏感信息落盘。
    log_file = settings.log_file
    if log_file:
        log_dir = os.path.dirname(os.path.abspath(log_file))
        os.makedirs(log_dir, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler.setLevel(log_level)
        file_handler.addFilter(SensitiveDataFilter())
        root_logger.addHandler(file_handler)

    # 降低第三方库日志量，避免泄露完整 SQL、HTTP 请求体和 MCP 工具 Schema
    for logger_name in _NOISY_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    root_logger.info("日志系统初始化完成")
