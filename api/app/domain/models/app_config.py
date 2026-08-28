

from typing import List, Dict, Any,Optional
import uuid
from pydantic import BaseModel,ConfigDict,HttpUrl,Field,model_validator
from enum import Enum
class LLMConfig(BaseModel):
    """语言模型配置"""
    base_url :HttpUrl = "https://api.deepseek.com"#基础url
    api_key : str = ""
    model_name : str = "deepseek-v4-flash" #推理模型，支持工具调用的模型
    temperature : float = Field(default=0.7)#温度
    max_tokens: int = Field(8192,ge=0) #最大输出token数

class AgentConfig(BaseModel):
    """Agent 通用配置"""
    max_iterations: int = Field(
        default=100,
        gt=0,
        lt= 1000,
    )#最大迭代次数

    max_retries:int = Field(
        default=3,
        gt=1,
        lt=10,
    )
    max_search_results: int = Field(
        default=10, 
        gt=1,
        lt=30,
    )

class MCPTransport(str,Enum):
    """MCP传输类型枚举"""
    STDIO = "stdio"
    SSE = "sse"
    STREAMABLE_HTTP = "streamable_http"

class MCPServerConfig(BaseModel):
    """MCP单条服务配置"""
    #通用字段配置
    transport: MCPTransport = MCPTransport.STREAMABLE_HTTP #传输协议
    enabled:bool = True #是否开启服务
    description: Optional[str] = None #MCP服务的描述
    env: Optional[Dict[str, Any]] = None #环境变量


    #stdio配置
    command: Optional[str] = None #启动命令
    args: Optional[List[str]] = None #命令参数

    #streamable_http与sse配置
    url: Optional[str] = None
    headers: Optional[Dict[str, Any]] = None #headers请求头
    # 是否读取 HTTP_PROXY、HTTPS_PROXY、ALL_PROXY 等环境变量
    trust_env: bool = False

    model_config = ConfigDict(extra="allow")

  
    @model_validator(mode="after")
    def validate_mcp_server_config(self):
        """校验mcp_server_config的相关消息，包含url + command"""
        #1.判断transport 是否为 sse/streamable_http
        if self.transport in [MCPTransport.SSE, MCPTransport.STREAMABLE_HTTP]:
            #2.这两种传输方式需要判断url是否传递
            if not self.url:
                raise ValueError(f"在sse或streamable_http传输协议中必须传递url")
        #3.判断transport 是否为stdio类型
        if self.transport == MCPTransport.STDIO:
            #4.判断command也就是启动命令是否传递
            if not self.command:
                raise ValueError("在stdio模式下必须传递command")
        return self

    
class MCPConfig(BaseModel):
    """应用MCP配置"""
    mcpServers: Dict[str, MCPServerConfig] = Field(
        default_factory=dict #mcp服务
    )

class A2AServerConfig(BaseModel):
    """A2A服务配置"""
    id : str = Field(
        default_factory=lambda:str(uuid.uuid4())
    )
    base_url:str  #服务基础url
    enabled:bool = True #服务是否开启

class A2AConfig(BaseModel):
    """A2A配置"""
    a2a_servers: List[A2AServerConfig] = Field(default_factory=list)


class AppConfig(BaseModel):
    """应用配置信息，包含agent配置、llm提供商、a2a网络、mcp服务配置"""
    llm_config:LLMConfig  #语言模型配置

    agent_config: AgentConfig #Agent通用配置
    #Pydantic 配置，允许传递额外的字段
    mcp_config: MCPConfig = Field(default_factory=MCPConfig) #MCP服务配置
    a2a_config:A2AConfig #A2A服务配置
    model_config = ConfigDict(extra="allow") 



