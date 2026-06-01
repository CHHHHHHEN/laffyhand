import { useChatStore } from "@/stores/chat-store"
import { rpcClient } from "@/lib/rpc"

export function PermissionModal() {
  const pendingPermission = useChatStore((s) => s.pendingPermission)
  const setPendingPermission = useChatStore((s) => s.setPendingPermission)

  if (!pendingPermission) return null

  const handleAction = async (action: "allow" | "always" | "deny") => {
    const reqId = pendingPermission.requestId
    setPendingPermission(null)
    try {
      await rpcClient.permissionRespond(reqId, action)
    } catch {
      // best effort
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/20 backdrop-blur-sm">
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-xl border border-gray-200 dark:border-gray-700 w-full max-w-sm mx-4 p-5">
        <div className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
          Allow {pendingPermission.permission} '{pendingPermission.pattern}'?
        </div>
        <div className="flex gap-2 justify-end">
          <button
            onClick={() => handleAction("deny")}
            className="px-3 py-1.5 text-xs rounded-lg border border-gray-200 dark:border-gray-600 text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 cursor-pointer"
          >
            Deny
          </button>
          <button
            onClick={() => handleAction("allow")}
            className="px-3 py-1.5 text-xs rounded-lg bg-blue-600 text-white hover:bg-blue-700 cursor-pointer"
          >
            Allow Once
          </button>
          <button
            onClick={() => handleAction("always")}
            className="px-3 py-1.5 text-xs rounded-lg bg-green-600 text-white hover:bg-green-700 cursor-pointer"
          >
            Always Allow
          </button>
        </div>
      </div>
    </div>
  )
}