import { useState, useEffect, useCallback } from "react"
import { rpcClient, type ConfigProvidersResult, type MCPStatusResult } from "@/lib/rpc"
import { useChatStore } from "@/stores/chat-store"

type Tab = "tools" | "mcp" | "config"

export function ConfigPanel() {
  const [open, setOpen] = useState(false)
  const [tab, setTab] = useState<Tab>("tools")
  const [providers, setProviders] = useState<ConfigProvidersResult | null>(null)
  const [mcp, setMcp] = useState<MCPStatusResult | null>(null)
  const [tools, setTools] = useState<{ name: string; description: string }[] | null>(null)
  const [loading, setLoading] = useState(false)

  const model = useChatStore((s) => s.model)

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

  useEffect(() => {
    if (open) loadData()
  }, [open, loadData])

  const handleSwitch = async (provider: string, modelName: string) => {
    try {
      await rpcClient.sessionSetConfig({ provider, model: modelName })
      useChatStore.getState().setSessionInfo(modelName, null)
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
            className="p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 cursor-pointer rounded-md hover:bg-gray-100 dark:hover:bg-gray-700"
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
              className={`px-3 py-1 text-xs rounded-md transition-colors cursor-pointer ${
                tab === t.key
                  ? "bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 font-medium"
                  : "text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700"
              }`}
            >
              {t.label}
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
                  <div key={t.name} className="px-3 py-2 bg-gray-50 dark:bg-gray-900/50 rounded-lg border border-gray-100 dark:border-gray-700/50">
                    <div className="text-xs font-medium text-gray-700 dark:text-gray-300 font-mono">{t.name}</div>
                    <div className="text-[10px] text-gray-400 dark:text-gray-500 mt-0.5 line-clamp-2">{t.description || "—"}</div>
                  </div>
                ))
              ) : (
                <p className="text-xs text-gray-400 text-center py-4">No tools available</p>
              )}
            </div>
          )}

          {!loading && tab === "mcp" && (
            <div className="space-y-1.5">
              {mcp && mcp.servers.length > 0 ? (
                mcp.servers.map((s) => (
                  <div key={s.name} className="flex items-center justify-between px-3 py-2 bg-gray-50 dark:bg-gray-900/50 rounded-lg border border-gray-100 dark:border-gray-700/50">
                    <span className="text-xs font-medium text-gray-700 dark:text-gray-300">{s.name}</span>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                      s.status === "connected"
                        ? "bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400"
                        : "bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400"
                    }`}>
                      {s.status}
                    </span>
                  </div>
                ))
              ) : (
                <p className="text-xs text-gray-400 text-center py-4">No MCP servers configured</p>
              )}
            </div>
          )}

          {!loading && tab === "config" && (
            <div className="space-y-3">
              {providers ? (
                Object.entries(providers.providers).map(([key, pc]) => (
                  <div key={key} className="px-3 py-2 bg-gray-50 dark:bg-gray-900/50 rounded-lg border border-gray-100 dark:border-gray-700/50">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-medium text-gray-700 dark:text-gray-300">{key}</span>
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