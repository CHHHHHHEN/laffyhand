from __future__ import annotations

import re
from typing import Any

import httpx
from loguru import logger

from laffyhand.core.tools.base import BaseTool


class WebFetchTool(BaseTool):
    name = "web_fetch"
    description = "Fetch and read content from a URL, returning it as markdown or plain text."

    def _input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to fetch content from (must be a fully-formed valid URL)",
                },
                "format": {
                    "type": "string",
                    "enum": ["markdown", "text"],
                    "description": "Output format: markdown (default) or plain text",
                    "default": "markdown",
                },
            },
            "required": ["url"],
        }

    async def run(self, params: dict[str, Any]) -> str:
        url: str = params["url"]
        output_format: str = params.get("format", "markdown")

        if url.startswith("http://"):
            url = "https://" + url[7:]
        elif not url.startswith("https://"):
            url = "https://" + url

        timeout = httpx.Timeout(30.0, connect=10.0, read=20.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            try:
                logger.info(f"WebFetch: fetching {url}")
                response = await client.get(url, headers={
                    "User-Agent": "Mozilla/5.0 (compatible; LaffyHand/1.0)",
                    "Accept": "text/html,text/plain,application/json,*/*",
                })
                response.raise_for_status()
            except httpx.TimeoutException:
                return f"Request timed out: {url}"
            except httpx.HTTPStatusError as e:
                return f"HTTP error {e.response.status_code}: {url}"
            except httpx.RequestError as e:
                return f"Request failed: {e}"

        text = response.text[:100_000]
        truncated = len(response.text) > 100_000

        if output_format == "markdown":
            text = self._html_to_markdown(text)

        if truncated:
            text += "\n\n[Content truncated at 100KB. Use more specific URLs to retrieve targeted content.]"

        logger.info(f"WebFetch: fetched {url} ({len(text)} chars)")
        return text

    @staticmethod
    def _html_to_markdown(html: str) -> str:
        text = html
        # Remove scripts and styles
        text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
        # Replace common block tags with newlines
        text = re.sub(r'</?(?:p|div|h[1-6]|blockquote|pre|tr|li|ol|ul|section|article|nav|header|footer)[^>]*>', '\n', text, flags=re.IGNORECASE)
        # Replace br with newline
        text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
        # Replace remaining tags with spaces
        text = re.sub(r'<[^>]+>', ' ', text)
        # Decode common HTML entities
        text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
        text = text.replace('&quot;', '"').replace('&#39;', "'").replace('&nbsp;', ' ')
        # Collapse blank lines
        text = re.sub(r'\n\s*\n', '\n\n', text)
        # Strip leading/trailing whitespace per line
        lines = [line.strip() for line in text.splitlines()]
        text = '\n'.join(line for line in lines if line)
        return text.strip()
