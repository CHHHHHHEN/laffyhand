from pydantic import BaseModel


class LLMProviderConfig(BaseModel):
    name: str
    base_url: str
    api_key: str
