import http.client as client
import json
from urllib.parse import urlparse
from loguru import logger as _logger
from typing import List, Generator, Optional, override

from laffyhand.agent.models import Message, StreamEvent, StreamFinish, ToolDefinition
from laffyhand.agent.providers.base import BaseProvider
from laffyhand.agent.providers.openai_compat import (
    message_to_openai, tool_definitions_to_openai_tools, OpenAIStreamParser,
)
from laffyhand.agent.providers.sse import parse_sse

CHAT_COMPLETIONS_PATH = "/v1/chat/completions"


class DeepseekProvider(BaseProvider):
    @override
    def chat_completions_stream(
        self, model: str, messages: List[Message], tools: Optional[List[ToolDefinition]] = None
    ) -> Generator[StreamEvent, None, None]:
        full_url = self.config.base_url.rstrip('/') + CHAT_COMPLETIONS_PATH
        parsed = urlparse(full_url)
        url_path = parsed.path
        ConnectionClass = client.HTTPSConnection if parsed.scheme == 'https' else client.HTTPConnection
        connection = ConnectionClass(host=parsed.netloc, timeout=30)

        openai_messages = [message_to_openai(m) for m in messages]
        body_dict: dict = {
            "model": model,
            "messages": openai_messages,
            "stream": True,
            "stream_options": {"include_usage": True},
            "thinking": {"type": "enabled"},
            "reasoning_effort": "high",
        }
        if tools:
            body_dict["tools"] = tool_definitions_to_openai_tools(tools)
        body = json.dumps(body_dict).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

        _logger.debug(f"DeepSeek Chat Completions Request: {body_dict}")
        connection.request("POST", url=url_path, body=body, headers=headers)
        response = connection.getresponse()
        try:
            parser = OpenAIStreamParser()
            for raw_data in parse_sse(response):
                events = parser.feed(raw_data)
                for event in events:
                    yield event
                if any(isinstance(e, StreamFinish) for e in events):
                    break
        finally:
            connection.close()
