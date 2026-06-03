import { useState, useEffect, useCallback } from "react"
import { rpcClient, type ConfigProvidersResult, type MCPStatusResult } from "@/lib/rpc"
import { useChatStore } from "@/stores/chat-store"
import { useSessionStore } from "@/stores/session-store"

type Tab = "tools" | "mcp" | "config"

interface ToolInfo {
  name: string
  description: string
  enabled: boolean
}

export function ConfigPanel() {
  const [open, setOpen] = useState(false)
  const [tab, setTab] = useState<Tab>("tools")
  const [providers, setProviders] = useState<ConfigProvidersResult | null>(null)
  const [mcp, setMcp] = useState<MCPStatusResult | null>(null)
  const [tools, setTools] = useState<ToolInfo[] | null>(null)
  const [loading, setLoading] = useState(false)

  const activeSessionId = useSessionStore((s) => s.activeSessionId)
  const model = useChatStore((s) => activeSessionId ? s.sessions[activeSessionId]?.model ?? "" : "")

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [p, m, t] = await Promise.all([
        rpcClient.configProviders().catch(() => null),
        rpcClient.mcpStatus().catch(() => null),
        rpcClient.toolsList().catch(() => null),
      ])
      if (p) setProviders(p)
      if (m) setMcp(m)
      if (t) setTools(t.tools)
    } finally {
      setLoading(false)
    }
  }, [])

  const toggleTool = async (name: string) => {
    if (!tools) return
    const current = tools.find((t) => t.name === name)
    if (!current) return
    const nextEnabled = !current.enabled
    const updated = tools.map((t) =>
      t.name === name ? { ...t, enabled: nextEnabled } : t
    )
    setTools(updated)
    const disabled = updated.filter((t) => !t.enabled).map((t) => t.name)
    try {
      await rpcClient.toolsSetDisabled(disabled)
    } catch {
      // revert on error
      setTools(tools)
    }
  }

  useEffect(() => {
    if (open) loadData()
  }, [open, loadData])

  const handleSwitch = async (provider: string, modelName: string) => {
    try {
      await rpcClient.sessionSetConfig({ provider, model: modelName })
      if (activeSessionId) {
        useChatStore.getState().setSessionInfo(activeSessionId, modelName, null)
      }
      setOpen(false)
    } catch {
      // ignore
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="flex items-center gap-1 text-[11px] text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors cursor-pointer shrink-0"
        title="Config & Tools"
      >
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
        </svg>
      </button>
    )
  }

  const tabs: { key: Tab; label: string }[] = [
    { key: "tools", label: "Tools" },
    { key: "mcp", label: "MCP" },
    { key: "config", label: "Config" },
  ]

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/20 backdrop-blur-sm animate-[fade-in_0.15s_ease-out]" onClick={() => setOpen(false)}>
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-xl border border-gray-200 dark:border-gray-700 w-full max-w-lg max-h-[70vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
        {/* 标题栏 */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700 shrink-0">
          <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300">Config & Tools</h3>
          <button
            onClick={() => setOpen(false)}
            className="p-1.5 text-gray-400 hover:text-red-500 dark:hover:text-red-400 cursor-pointer rounded-md hover:bg-red-50 dark:hover:bg-red-900/20 transition-all duration-150"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Tab 切换 */}
        <div className="flex gap-1 px-4 pt-3 shrink-0">
          {tabs.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`relative px-3 py-1.5 text-xs rounded-md transition-all duration-150 cursor-pointer ${
                tab === t.key
                  ? "bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 font-medium shadow-sm"
                  : "text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700"
              }`}
            >
              {t.label}
              {tab === t.key && (
                <span className="absolute bottom-0 left-2 right-2 h-0.5 bg-blue-500 dark:bg-blue-400 rounded-full" />
              )}
            </button>
          ))}
        </div>

        {/* 内容 */}
        <div className="flex-1 overflow-y-auto p-4 space-y-2">
          {loading && <div className="text-xs text-gray-400 text-center py-4">Loading...</div>}

          {!loading && tab === "tools" && (
            <div className="space-y-1.5">
              {tools && tools.length > 0 ? (
                tools.map((t) => (
                  <div key={t.name} className="px-3 py-2.5 bg-white dark:bg-gray-900/50 rounded-lg border border-gray-200 dark:border-gray-700/50 hover:border-gray-300 dark:hover:border-gray-600 transition-all duration-150">
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${t.enabled ? "bg-blue-500" : "bg-gray-300 dark:bg-gray-600"}`} />
                        <div className="text-xs font-medium text-gray-700 dark:text-gray-300 font-mono truncate">{t.name}</div>
                      </div>
                      <button
                        onClick={() => toggleTool(t.name)}
                        className={`relative inline-flex h-4 w-7 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                          t.enabled ? "bg-blue-500" : "bg-gray-300 dark:bg-gray-600"
                        }`}
                      >
                        <span className={`inline-block h-3 w-3 transform rounded-full bg-white shadow-sm ring-0 transition duration-200 ease-in-out ${
                          t.enabled ? "translate-x-3.5" : "translate-x-0"
                        }`} />
                      </button>
                    </div>
                    <div className="text-[10px] text-gray-500 dark:text-gray-400 mt-1 ml-3.5 leading-relaxed line-clamp-2">{t.description || "—"}</div>
                  </div>
                ))
              ) : (
                <p className="text-xs text-gray-400 text-center py-4">No tools available</p>
              )}
            </div>
          )}

          {!loading && tab === "mcp" && (
            <MCPTab mcp={mcp} onRefresh={loadData} />
          )}

          {!loading && tab === "config" && (
            <div className="space-y-3">
              {providers ? (
                Object.entries(providers.providers).map(([key, pc]) => (
                  <div key={key} className="px-3 py-2.5 bg-white dark:bg-gray-900/50 rounded-lg border border-gray-200 dark:border-gray-700/50 hover:border-gray-300 dark:hover:border-gray-600 transition-all duration-150">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-medium text-gray-700 dark:text-gray-300 flex items-center gap-2">
                        <span className="w-1.5 h-1.5 rounded-full bg-blue-500 shrink-0" />
                        {key}
                      </span>
                      <span className="text-[10px] text-gray-400 dark:text-gray-500">{pc.type}</span>
                    </div>
                    <div className="mt-1.5 flex flex-wrap gap-1">
                      {pc.models.map((m) => {
                        const isActive = providers.default_provider === key && model === m.name
                        return (
                          <button
                            key={m.name}
                            onClick={() => handleSwitch(key, m.name)}
                            className={`text-[10px] px-2 py-0.5 rounded-full border transition-colors cursor-pointer ${
                              isActive
                                ? "bg-blue-100 dark:bg-blue-900/40 border-blue-300 dark:border-blue-700 text-blue-700 dark:text-blue-300"
                                : "bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-600 text-gray-500 dark:text-gray-400 hover:border-blue-300 dark:hover:border-blue-700"
                            }`}
                          >
                            {m.name}
                          </button>
                        )
                      })}
                    </div>
                  </div>
                ))
              ) : (
                <p className="text-xs text-gray-400 text-center py-4">No provider config available</p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}


function MCPTab({ mcp, onRefresh }: { mcp: MCPStatusResult | null; onRefresh: () => void }) {
  const [showAdd, setShowAdd] = useState(false)
  const [addType, setAddType] = useState<"local" | "remote">("local")
  const [addName, setAddName] = useState("")
  const [addCommand, setAddCommand] = useState("")
  const [addUrl, setAddUrl] = useState("")
  const [adding, setAdding] = useState(false)
  const [removing, setRemoving] = useState<string | null>(null)

  const handleAdd = async () => {
    if (!addName.trim()) return
    setAdding(true)
    try {
      if (addType === "local") {
        const parts = addCommand.trim().split(/\s+/)
        await rpcClient.mcpAddServer({ name: addName.trim(), type: "local", command: parts })
      } else {
        await rpcClient.mcpAddServer({ name: addName.trim(), type: "remote", url: addUrl.trim() })
      }
      setShowAdd(false)
      setAddName("")
      setAddCommand("")
      setAddUrl("")
      onRefresh()
    } catch (e) {
      alert(`Failed to add MCP server: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setAdding(false)
    }
  }

  const handleRemove = async (name: string) => {
    setRemoving(name)
    try {
      await rpcClient.mcpRemoveServer(name)
      onRefresh()
    } catch (e) {
      alert(`Failed to remove MCP server: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setRemoving(null)
    }
  }

  return (
    <div className="space-y-1.5">
      {mcp && mcp.servers.length > 0 ? (
        mcp.servers.map((s) => (
          <div key={s.name} className="flex items-center justify-between px-3 py-2.5 bg-white dark:bg-gray-900/50 rounded-lg border border-gray-200 dark:border-gray-700/50 hover:border-gray-300 dark:hover:border-gray-600 transition-all duration-150">
            <span className="text-xs font-medium text-gray-700 dark:text-gray-300">{s.name}</span>
            <div className="flex items-center gap-2">
              <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
                s.status === "connected"
                  ? "bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400"
                  : "bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400"
              }`}>
                {s.status}
              </span>
              <button
                onClick={() => handleRemove(s.name)}
                disabled={removing === s.name}
                className="p-1 text-gray-400 hover:text-red-500 dark:hover:text-red-400 cursor-pointer rounded-md hover:bg-red-50 dark:hover:bg-red-900/20 transition-all duration-150"
                title="Remove MCP server"
              >
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            </div>
          </div>
        ))
      ) : (
        <p className="text-xs text-gray-400 text-center py-4">No MCP servers configured</p>
      )}

      {!showAdd ? (
        <button
          onClick={() => setShowAdd(true)}
          className="w-full mt-2 px-3 py-2 text-xs font-medium text-blue-600 dark:text-blue-400 border border-dashed border-blue-300 dark:border-blue-700 rounded-lg hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-all cursor-pointer"
        >
          + Add MCP Server
        </button>
      ) : (
        <div className="mt-2 p-3 bg-gray-50 dark:bg-gray-900/50 rounded-lg border border-gray-200 dark:border-gray-700/50 space-y-2">
          <div className="flex gap-2">
            <button
              onClick={() => setAddType("local")}
              className={`px-2 py-1 text-[10px] rounded-md cursor-pointer transition-all ${
                addType === "local"
                  ? "bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 font-medium"
                  : "text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700"
              }`}
            >
              Local
            </button>
            <button
              onClick={() => setAddType("remote")}
              className={`px-2 py-1 text-[10px] rounded-md cursor-pointer transition-all ${
                addType === "remote"
                  ? "bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 font-medium"
                  : "text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700"
              }`}
            >
              Remote
            </button>
          </div>
          <input
            type="text"
            value={addName}
            onChange={(e) => setAddName(e.target.value)}
            placeholder="Server name"
            className="w-full px-2 py-1.5 text-xs rounded-md border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 placeholder-gray-400 outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-400/30 transition-all"
          />
          {addType === "local" ? (
            <input
              type="text"
              value={addCommand}
              onChange={(e) => setAddCommand(e.target.value)}
              placeholder="Command and args (e.g. npx -y @modelcontextprotocol/server-everything)"
              className="w-full px-2 py-1.5 text-xs rounded-md border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 placeholder-gray-400 outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-400/30 transition-all"
            />
          ) : (
            <input
              type="text"
              value={addUrl}
              onChange={(e) => setAddUrl(e.target.value)}
              placeholder="URL (e.g. https://example.com/mcp)"
              className="w-full px-2 py-1.5 text-xs rounded-md border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 placeholder-gray-400 outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-400/30 transition-all"
            />
          )}
          <div className="flex gap-2">
            <button
              onClick={handleAdd}
              disabled={adding || !addName.trim()}
              className="px-3 py-1.5 text-xs font-medium text-white bg-blue-500 rounded-md hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-all cursor-pointer"
            >
              {adding ? "Connecting..." : "Add & Connect"}
            </button>
            <button
              onClick={() => setShowAdd(false)}
              className="px-3 py-1.5 text-xs text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 transition-all cursor-pointer"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  )
}