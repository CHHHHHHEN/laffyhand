import { useState } from "react"
import type { Message } from "@/types/session"
import { rpcClient } from "@/lib/rpc"

interface PermissionBannerProps {
  requests: Message[]
  onResolve: (messageId: string, denyReason?: string) => void
}

export function PermissionBanner({ requests, onResolve }: PermissionBannerProps) {
  const [denyingId, setDenyingId] = useState<string | null>(null)
  const [denyReasonInput, setDenyReasonInput] = useState("")

  if (requests.length === 0) return null

  return (
    <div className="shrink-0 px-4 py-2 space-y-2 border-b border-[var(--border-base)] bg-[var(--bg-layer-1)]">
      {requests.map((msg) => {
        const info = msg.permissionInfo
        if (!info || info.resolved) return null
        return (
          <div
            key={msg.id}
            className="flex items-center gap-3 px-3 py-2 rounded-lg border border-amber-200/50 dark:border-amber-700/30 bg-amber-50/80 dark:bg-amber-900/20"
          >
            <svg className="w-4 h-4 shrink-0 text-amber-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
            </svg>
            <span className="text-sm text-[var(--text-base)] flex-1">
              Allow <span className="font-semibold">{info.permission}</span> '<span className="font-mono text-xs">{info.pattern}</span>'?
            </span>

            {denyingId === info.requestId ? (
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={denyReasonInput}
                  onChange={(e) => setDenyReasonInput(e.target.value)}
                  placeholder="Reason (optional)"
                  className="w-48 px-2 py-1 text-xs rounded border border-[var(--border-strong)] bg-[var(--bg-base)] text-[var(--text-base)] placeholder-[var(--text-faint)] outline-none focus:border-[var(--accent)] transition-colors"
                  autoFocus
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      const reason = denyReasonInput.trim() || undefined
                      rpcClient.permissionRespond(info.requestId, "deny", reason)
                      onResolve(msg.id, reason)
                      setDenyingId(null)
                      setDenyReasonInput("")
                    }
                  }}
                />
                <button
                  onClick={async () => {
                    await rpcClient.permissionRespond(info.requestId, "deny")
                    onResolve(msg.id)
                    setDenyingId(null)
                  }}
                  className="px-2 py-1 text-xs rounded border border-[var(--border-strong)] text-[var(--text-muted)] hover:bg-[var(--overlay-hover)] transition-colors cursor-pointer"
                >
                  Skip
                </button>
                <button
                  onClick={async () => {
                    const reason = denyReasonInput.trim() || undefined
                    await rpcClient.permissionRespond(info.requestId, "deny", reason)
                    onResolve(msg.id, reason)
                    setDenyingId(null)
                    setDenyReasonInput("")
                  }}
                  className="px-2 py-1 text-xs rounded bg-red-500 text-white hover:opacity-90 transition-opacity cursor-pointer"
                >
                  Send
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-1.5 shrink-0">
                <button
                  onClick={() => setDenyingId(info.requestId)}
                  className="px-2 py-1 text-xs rounded border border-[var(--border-strong)] text-[var(--text-muted)] hover:bg-[var(--overlay-hover)] transition-colors cursor-pointer"
                >
                  Deny
                </button>
                <button
                  onClick={async () => {
                    await rpcClient.permissionRespond(info.requestId, "allow")
                    onResolve(msg.id)
                  }}
                  className="px-2 py-1 text-xs rounded bg-[var(--accent)] text-white hover:opacity-90 transition-opacity cursor-pointer"
                >
                  Allow Once
                </button>
                <button
                  onClick={async () => {
                    await rpcClient.permissionRespond(info.requestId, "always")
                    onResolve(msg.id)
                  }}
                  className="px-2 py-1 text-xs rounded bg-green-600 text-white hover:opacity-90 transition-opacity cursor-pointer"
                >
                  Always Allow
                </button>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
