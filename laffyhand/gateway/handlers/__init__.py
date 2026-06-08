from __future__ import annotations

from typing import TYPE_CHECKING, Any

from laffyhand.gateway.protocol import (
    AGENT_LIST,
    CHAT,
    CHAT_CANCEL,
    CHAT_STEER,
    CHAT_STREAM,
    CONFIG_PROVIDERS,
    INITIALIZE,
    MCP_ADD_SERVER,
    MCP_REMOVE_SERVER,
    MCP_STATUS,
    PERMISSION_RESPOND,
    SESSION_ARCHIVE,
    SESSION_COMPACT,
    SESSION_CREATE,
    SESSION_DELETE,
    SESSION_FORK,
    SESSION_GENERATE_TITLE,
    SESSION_LIST,
    SESSION_LOAD,
    SESSION_SEARCH,
    SESSION_SET_CONFIG,
    SESSION_SET_TITLE,
    SESSION_SUBSCRIBE,
    SHUTDOWN,
    SUBAGENT_LIST_ACTIVE,
    TODO_LIST,
    TODO_UPDATE,
    TOOLS_LIST,
    TOOLS_SET_DISABLED,
    USAGE_GET,
    WORKSPACE_SET,
)
# ── Initialize / Shutdown ────────────────────────────────────────

if TYPE_CHECKING:
    from laffyhand.gateway.dispatcher import Dispatcher
    from laffyhand.gateway.transport import Transport


async def handle_initialize(
    runtime: Any,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> dict[str, Any]:
    return {
        "protocol_version": "2.0",
        "server_info": {
            "name": "laffyhand",
            "version": "0.1.0",
        },
        "session_id": None,
    }


async def handle_shutdown(
    runtime: Any,
    params: dict[str, Any],
    transport: Transport,
    _request_id: str | int | None,
    conn_id: str,
) -> None:
    await runtime.shutdown()


# ── Import handlers from submodules ──────────────────────────────

from laffyhand.gateway.handlers.agent import (
    handle_agent_list,
    handle_subagent_list_active,
)
from laffyhand.gateway.handlers.chat import (
    handle_chat,
    handle_chat_cancel,
    handle_chat_steer,
    handle_chat_stream,
)
from laffyhand.gateway.handlers.config import handle_config_providers
from laffyhand.gateway.handlers.mcp import (
    handle_mcp_add_server,
    handle_mcp_remove_server,
    handle_mcp_status,
)
from laffyhand.gateway.handlers.permission import handle_permission_respond
from laffyhand.gateway.handlers.session import (
    handle_session_archive,
    handle_session_compact,
    handle_session_create,
    handle_session_delete,
    handle_session_fork,
    handle_session_generate_title,
    handle_session_list,
    handle_session_load,
    handle_session_search,
    handle_session_set_config,
    handle_session_set_title,
    handle_session_subscribe,
)
from laffyhand.gateway.handlers.todo import handle_todo_list, handle_todo_update
from laffyhand.gateway.handlers.tools import (
    handle_tools_list,
    handle_tools_set_disabled,
    handle_workspace_set,
)
from laffyhand.gateway.handlers.usage import handle_usage_get

# ── Registry ─────────────────────────────────────────────────────


def register_all_handlers(dispatcher: Dispatcher) -> None:
    dispatcher.register(INITIALIZE, handle_initialize)
    dispatcher.register(SHUTDOWN, handle_shutdown)
    dispatcher.register(SESSION_CREATE, handle_session_create)
    dispatcher.register(SESSION_LIST, handle_session_list)
    dispatcher.register(SESSION_LOAD, handle_session_load)
    dispatcher.register(SESSION_DELETE, handle_session_delete)
    dispatcher.register(SESSION_FORK, handle_session_fork)
    dispatcher.register(SESSION_SEARCH, handle_session_search)
    dispatcher.register(SESSION_SET_TITLE, handle_session_set_title)
    dispatcher.register(SESSION_GENERATE_TITLE, handle_session_generate_title)
    dispatcher.register(SESSION_ARCHIVE, handle_session_archive)
    dispatcher.register(AGENT_LIST, handle_agent_list)
    dispatcher.register(SUBAGENT_LIST_ACTIVE, handle_subagent_list_active)
    dispatcher.register(USAGE_GET, handle_usage_get)
    dispatcher.register(CONFIG_PROVIDERS, handle_config_providers)
    dispatcher.register(MCP_STATUS, handle_mcp_status)
    dispatcher.register(MCP_ADD_SERVER, handle_mcp_add_server)
    dispatcher.register(MCP_REMOVE_SERVER, handle_mcp_remove_server)
    dispatcher.register(SESSION_SET_CONFIG, handle_session_set_config)
    dispatcher.register(WORKSPACE_SET, handle_workspace_set)
    dispatcher.register(CHAT, handle_chat)
    dispatcher.register(CHAT_STREAM, handle_chat_stream, streaming=True)
    dispatcher.register(CHAT_CANCEL, handle_chat_cancel)
    dispatcher.register(CHAT_STEER, handle_chat_steer)
    dispatcher.register(TOOLS_LIST, handle_tools_list)
    dispatcher.register(TOOLS_SET_DISABLED, handle_tools_set_disabled)
    dispatcher.register(PERMISSION_RESPOND, handle_permission_respond)
    dispatcher.register(TODO_LIST, handle_todo_list)
    dispatcher.register(TODO_UPDATE, handle_todo_update)
    dispatcher.register(SESSION_COMPACT, handle_session_compact)
    dispatcher.register(SESSION_SUBSCRIBE, handle_session_subscribe, streaming=True)


__all__ = [
    "handle_agent_list",
    "handle_chat",
    "handle_chat_cancel",
    "handle_chat_steer",
    "handle_chat_stream",
    "handle_config_providers",
    "handle_initialize",
    "handle_mcp_add_server",
    "handle_mcp_remove_server",
    "handle_mcp_status",
    "handle_permission_respond",
    "handle_session_archive",
    "handle_session_compact",
    "handle_session_create",
    "handle_session_delete",
    "handle_session_fork",
    "handle_session_generate_title",
    "handle_session_list",
    "handle_session_load",
    "handle_session_search",
    "handle_session_set_config",
    "handle_session_set_title",
    "handle_session_subscribe",
    "handle_shutdown",
    "handle_subagent_list_active",
    "handle_todo_list",
    "handle_todo_update",
    "handle_tools_list",
    "handle_tools_set_disabled",
    "handle_usage_get",
    "handle_workspace_set",
    "register_all_handlers",
]
