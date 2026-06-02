from pydantic import BaseModel, Field
from typing import NewType, Any, Dict, List, Literal, Union, Optional

from laffyhand.agent.schemas import ToolCallContent, ToolDefinition, Usage

ModelID = NewType("ModelID", str)
ProviderID = NewType("ProviderID", str)

class Frame(BaseModel):
    data: Dict[str, Any]

class Header(BaseModel):
    key: str = Field(description="Header key name")
    value: str = Field(description="Header value")

class ProviderRequest(BaseModel):
    pass

class SystemMessage(BaseModel):
    role: Literal["system"] = "system"
    content: str


class UserMessage(BaseModel):
    role: Literal["user"] = "user"
    content: str


class AssistantMessage(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: Optional[str] = None
    reasoning: Optional[str] = None
    tool_calls: Optional[List[ToolCallContent]] = None
    tokens: Optional["Usage"] = None


class ToolMessage(BaseModel):
    role: Literal["tool"] = "tool"
    tool_call_id: str
    content: str
    is_error: bool = False


Message = Union[SystemMessage, UserMessage, AssistantMessage, ToolMessage]

class LLMRequest(BaseModel):
    model: ModelID
    provider: ProviderID
    messages: list[Message]
    tools: Optional[list[ToolDefinition]] = None


class ToolCallAccumulator(BaseModel):
    tool_call_id: str
    tool_name: str
    args: str