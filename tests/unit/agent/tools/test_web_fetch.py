from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from laffyhand.agent.tools.web_fetch import WebFetchTool


def _fake_response(text: str, content_type: str = "text/plain") -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.text = text
    resp.headers = {"content-type": content_type}
    resp.raise_for_status = MagicMock()
    return resp


@pytest.fixture
def tool() -> WebFetchTool:
    return WebFetchTool()


@pytest.mark.anyio
async def test_url_auto_https(tool: WebFetchTool) -> None:
    """http:// URLs are upgraded to https://"""
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get = AsyncMock(return_value=_fake_response("ok"))

    with patch("httpx.AsyncClient", return_value=mock_client):
        await tool.run({"url": "http://example.com"})

    called_url = mock_client.get.call_args[0][0]
    assert called_url == "https://example.com"


@pytest.mark.anyio
async def test_bare_url_gets_https_prefix(tool: WebFetchTool) -> None:
    """URL without scheme gets https:// prepended"""
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get = AsyncMock(return_value=_fake_response("ok"))

    with patch("httpx.AsyncClient", return_value=mock_client):
        await tool.run({"url": "example.com"})

    called_url = mock_client.get.call_args[0][0]
    assert called_url == "https://example.com"


@pytest.mark.anyio
async def test_input_schema_has_required_fields(tool: WebFetchTool) -> None:
    schema = tool._input_schema()
    assert "url" in schema["required"]


@pytest.mark.anyio
async def test_format_default_is_markdown(tool: WebFetchTool) -> None:
    schema = tool._input_schema()
    fmt = schema["properties"]["format"]
    assert fmt["default"] == "markdown"


@pytest.mark.anyio
async def test_http_timeout(tool: WebFetchTool) -> None:
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await tool.run({"url": "https://example.com"})

    assert "timed out" in result


@pytest.mark.anyio
async def test_http_error_status(tool: WebFetchTool) -> None:
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 404
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "404", request=MagicMock(), response=mock_response
    )

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await tool.run({"url": "https://example.com/404"})

    assert "HTTP error 404" in result


@pytest.mark.anyio
async def test_request_error(tool: WebFetchTool) -> None:
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get = AsyncMock(side_effect=httpx.RequestError("connection refused"))

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await tool.run({"url": "https://example.com"})

    assert "Request failed" in result


@pytest.mark.anyio
async def test_successful_fetch_text_format(tool: WebFetchTool) -> None:
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.text = "Hello World"
    mock_response.headers = {"content-type": "text/plain"}
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await tool.run({"url": "https://example.com", "format": "text"})

    assert "Hello World" in result


@pytest.mark.anyio
async def test_successful_fetch_markdown_strips_html(tool: WebFetchTool) -> None:
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.text = "<html><body><h1>Title</h1><p>Content</p></body></html>"
    mock_response.headers = {"content-type": "text/html"}
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await tool.run({"url": "https://example.com"})

    assert "Title" in result
    assert "Content" in result
    assert "<html>" not in result
    assert "<h1>" not in result


@pytest.mark.anyio
async def test_content_truncated_at_100k(tool: WebFetchTool) -> None:
    large_text = "x" * 150_000
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.text = large_text
    mock_response.headers = {"content-type": "text/plain"}
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await tool.run({"url": "https://example.com", "format": "text"})

    assert len(result) < 110_000
    assert "Content truncated" in result


@pytest.mark.anyio
async def test_html_to_markdown_removes_scripts(tool: WebFetchTool) -> None:
    html = "<script>alert(1)</script><p>text</p>"
    result = tool._html_to_markdown(html)
    assert "alert" not in result
    assert "text" in result


@pytest.mark.anyio
async def test_html_to_markdown_decodes_entities(tool: WebFetchTool) -> None:
    html = "<p>foo &amp; bar &lt; baz</p>"
    result = tool._html_to_markdown(html)
    assert "foo & bar < baz" in result
