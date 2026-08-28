



from typing import TypeVar, Generic,Optional
from pydantic import BaseModel,Field

T = TypeVar("T")

class Response(BaseModel,Generic[T]):
    """基础api响应结构，继承BaseModel,并定义泛型"""
    code : int = 200
    msg :str = "success"
    data : Optional[T] = Field(
        default_factory=dict
    )

    @staticmethod
    def success(
        data:Optional[T] = None,
        msg: str = "success"
    )->"Response[T]":
        """成功消息，传递data+msg,code固定为200"""
        return Response(code=200,msg=msg,data=data if data is not None else {})

    @staticmethod
    def fail(
        code:int,
        msg:str, 
        data:Optional[T] = None
    )->"Response[T]":
        """失败消息提示，携带code+msg+data"""
        return Response(code=code,msg=msg,data=data if data is not None else {}) 