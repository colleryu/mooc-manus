

from typing import Protocol,Optional, Any, Dict,Union,List

class JSONParser(Protocol):
    """JSON解释器，用于解析JSON字符串并修复"""

    async def invoke(self, text:str, default_value: Optional[Any] = None)->Union[Dict,List,Any]:
        """调用函数，用于将传递进来的文本进行解析并返回"""