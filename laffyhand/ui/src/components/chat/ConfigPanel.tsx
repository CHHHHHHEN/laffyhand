import { useState, useEffect, useCallback } from "react"
import { rpcClient, type ConfigProvidersResult, type MCPStatusResult } from "@/lib/rpc"
import { useChatStore } from "@/stores/chat-store"
import { useSessionStore } from "@/stores/session-store"
import { useUiStore } from "@/stores/ui-store"
import { useAgents } from "@/hooks/use-sessions"

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
  const defaultAgent = useUiStore((s) => s.defaultAgent)
  const setDefaultAgent = useUiStore((s) => s.setDefaultAgent)
  const { agents } = useAgents()

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
        className="flex items-center gap-1 text-[11px] text-[var(--icon-muted)] hover:text-[var(--icon-base)] transition-colors cursor-pointer shrink-0"
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/20 backdrop-blur-sm" onClick={() => setOpen(false)}>
      <div className="bg-[var(--bg-base)] rounded-lg shadow-lg border border-[var(--border-base)] w-full max-w-lg max-h-[70vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--border-muted)] shrink-0">
          <h3 className="text-sm text-[var(--text-base)]" style={{ fontWeight: 500 }}>Config & Tools</h3>
          <button
            onClick={() => setOpen(false)}
            className="p-1 rounded-md text-[var(--icon-muted)] hover:text-[var(--text-base)] hover:bg-[var(--overlay-hover)] transition-colors cursor-pointer"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="flex gap-1 px-4 pt-3 shrink-0">
          {tabs.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`px-3 py-1.5 text-xs rounded-md transition-colors cursor-pointer ${
                tab === t.key
                  ? "bg-[var(--accent)] text-white"
                  : "text-[var(--text-muted)] hover:text-[var(--text-base)] hover:bg-[var(--overlay-hover)]"
              }`}
              style={tab === t.key ? { fontWeight: 500 } : {}}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-2">
          {loading && <div className="text-xs text-[var(--text-muted)] text-center py-4">Loading...</div>}

          {!loading && tab === "tools" && (
            <div className="space-y-1.5">
              {tools && tools.length > 0 ? (
                tools.map((t) => (
                  <div key={t.name} className="px-3 py-2.5 bg-[var(--bg-deep)] rounded-lg border border-[var(--border-muted)] hover:border-[var(--border-base)] transition-all">
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${t.enabled ? "bg-[var(--accent)]" : "bg-[var(--border-strong)]"}`} />
                        <div className="text-xs text-[var(--text-base)] font-mono truncate">{t.name}</div>
                      </div>
                      <button
                        onClick={() => toggleTool(t.name)}
                        className={`relative inline-flex h-4 w-7 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ${
                          t.enabled ? "bg-[var(--accent)]" : "bg-[var(--border-strong)]"
                        }`}
                      >
                        <span className={`inline-block h-3 w-3 transform rounded-full bg-white shadow-sm ring-0 transition duration-200 ${
                          t.enabled ? "translate-x-3.5" : "translate-x-0"
                        }`} />
                      </button>
                    </div>
                    <div className="text-[10px] text-[var(--text-muted)] mt-1 ml-3.5 leading-relaxed line-clamp-2">{t.description || "—"}</div>
                  </div>
                ))
              ) : (
                <p className="text-xs text-[var(--text-muted)] text-center py-4">No tools available</p>
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
                  <div key={key} className="px-3 py-2.5 bg-[var(--bg-deep)] rounded-lg border border-[var(--border-muted)] hover:border-[var(--border-base)] transition-all">
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-[var(--text-base)] flex items-center gap-2">
                        <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent)] shrink-0" />
                        {key}
                      </span>
                      <span className="text-[10px] text-[var(--text-muted)]">{pc.type}</span>
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
                                ? "bg-[var(--accent)] text-white border-[var(--accent)]"
                                : "bg-[var(--bg-base)] border-[var(--border-base)] text-[var(--text-muted)] hover:border-[var(--accent)]"
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
                <p className="text-xs text-[var(--text-muted)] text-center py-4">No provider config available</p>
              )}

              {/* Default Agent selector */}
              <div className="px-3 py-2.5 bg-[var(--bg-deep)] rounded-lg border border-[var(--border-muted)]">
                <div className="text-xs text-[var(--text-base)] flex items-center gap-2 mb-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent)] shrink-0" />
                  Default Agent
                </div>
                <div className="flex flex-wrap gap-1">
                  {agents.map((agent) => (
                    <button
                      key={agent.name}
                      onClick={() => setDefaultAgent(agent.name)}
                      className={`text-[10px] px-2 py-0.5 rounded-full border transition-colors cursor-pointer ${
                        defaultAgent === agent.name
                          ? "bg-[var(--accent)] text-white border-[var(--accent)]"
                          : "bg-[var(--bg-base)] border-[var(--border-base)] text-[var(--text-muted)] hover:border-[var(--accent)]"
                      }`}
                    >
                      {agent.name}
                    </button>
                  ))}
                </div>
              </div>

              {/* Workspace setting */}
              <WorkspaceSetting />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}


function WorkspaceSetting() {
  const [path, setPath] = useState("")
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState("")

  const handleSave = async () => {
    if (!path.trim()) return
    setSaving(true)
    setError("")
    try {
      await rpcClient.workspaceSet(path.trim())
      setPath("")
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="px-3 py-2.5 bg-[var(--bg-deep)] rounded-lg border border-[var(--border-muted)]">
      <div className="text-xs text-[var(--text-base)] flex items-center gap-2 mb-2">
        <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent)] shrink-0" />
        Workspace
      </div>
      <div className="text-[10px] text-[var(--text-muted)] mb-2">
        Set the workspace directory. Agent file access is restricted to this path unless you approve otherwise.
      </div>
      <div className="flex gap-2">
        <input
          type="text"
          value={path}
          onChange={(e) => setPath(e.target.value)}
          placeholder="/path/to/workspace"
          className="flex-1 px-2 py-1.5 text-xs rounded-md border border-[var(--border-base)] bg-[var(--bg-base)] text-[var(--text-base)] placeholder-[var(--text-faint)] outline-none focus:border-[var(--accent)] transition-colors"
        />
        <button
          onClick={handleSave}
          disabled={saving || !path.trim()}
          className="px-3 py-1.5 text-xs font-medium text-white bg-[var(--accent)] rounded-md hover:opacity-90 disabled:opacity-50 transition-all cursor-pointer"
        >
          {saving ? "Setting..." : "Set"}
        </button>
      </div>
      {error && <div className="text-[10px] text-[var(--state-danger-fg)] mt-1">{error}</div>}
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
          <div key={s.name} className="flex items-center justify-between px-3 py-2.5 bg-[var(--bg-deep)] rounded-lg border border-[var(--border-muted)] hover:border-[var(--border-base)] transition-all">
            <span className="text-xs text-[var(--text-base)]">{s.name}</span>
            <div className="flex items-center gap-2">
              <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
                s.status === "connected"
                  ? "bg-[var(--state-success-bg)] text-[var(--state-success-fg)]"
                  : "bg-[var(--state-danger-bg)] text-[var(--state-danger-fg)]"
              }`}>
                {s.status}
              </span>
              <button
                onClick={() => handleRemove(s.name)}
                disabled={removing === s.name}
                className="p-1 text-[var(--icon-muted)] hover:text-[var(--state-danger-fg)] hover:bg-[var(--state-danger-bg)] rounded-md transition-colors cursor-pointer"
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
        <p className="text-xs text-[var(--text-muted)] text-center py-4">No MCP servers configured</p>
      )}

      {!showAdd ? (
        <button
          onClick={() => setShowAdd(true)}
          className="w-full mt-2 px-3 py-2 text-xs text-[var(--accent)] border border-dashed border-[var(--accent)] rounded-md hover:bg-[var(--state-info-bg)] transition-colors cursor-pointer"
        >
          + Add MCP Server
        </button>
      ) : (
        <div className="mt-2 p-3 bg-[var(--bg-deep)] rounded-lg border border-[var(--border-muted)] space-y-2">
          <div className="flex gap-2">
            <button
              onClick={() => setAddType("local")}
              className={`px-2 py-1 text-[10px] rounded-md cursor-pointer transition-all ${
                addType === "local"
                  ? "bg-[var(--accent)] text-white"
                  : "text-[var(--text-muted)] hover:bg-[var(--overlay-hover)]"
              }`}
            >
              Local
            </button>
            <button
              onClick={() => setAddType("remote")}
              className={`px-2 py-1 text-[10px] rounded-md cursor-pointer transition-all ${
                addType === "remote"
                  ? "bg-[var(--accent)] text-white"
                  : "text-[var(--text-muted)] hover:bg-[var(--overlay-hover)]"
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
            className="w-full px-2 py-1.5 text-xs rounded-md border border-[var(--border-base)] bg-[var(--bg-base)] text-[var(--text-base)] placeholder-[var(--text-faint)] outline-none focus:border-[var(--accent)] transition-colors"
          />
          {addType === "local" ? (
            <input
              type="text"
              value={addCommand}
              onChange={(e) => setAddCommand(e.target.value)}
              placeholder="Command and args (e.g. npx -y @modelcontextprotocol/server-everything)"
              className="w-full px-2 py-1.5 text-xs rounded-md border border-[var(--border-base)] bg-[var(--bg-base)] text-[var(--text-base)] placeholder-[var(--text-faint)] outline-none focus:border-[var(--accent)] transition-colors"
            />
          ) : (
            <input
              type="text"
              value={addUrl}
              onChange={(e) => setAddUrl(e.target.value)}
              placeholder="URL (e.g. https://example.com/mcp)"
              className="w-full px-2 py-1.5 text-xs rounded-md border border-[var(--border-base)] bg-[var(--bg-base)] text-[var(--text-base)] placeholder-[var(--text-faint)] outline-none focus:border-[var(--accent)] transition-colors"
            />
          )}
          <div className="flex gap-2">
            <button
              onClick={handleAdd}
              disabled={adding || !addName.trim()}
              className="px-3 py-1.5 text-xs font-medium text-white bg-[var(--accent)] rounded-md hover:opacity-90 disabled:opacity-50 transition-all cursor-pointer"
            >
              {adding ? "Connecting..." : "Add & Connect"}
            </button>
            <button
              onClick={() => setShowAdd(false)}
              className="px-3 py-1.5 text-xs text-[var(--text-muted)] hover:text-[var(--text-base)] transition-colors cursor-pointer"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
