import { Outlet } from "react-router-dom"
import { Sidebar } from "./Sidebar"
import { ErrorBoundary } from "@/components/ui/ErrorBoundary"
import { useUiStore } from "@/stores/ui-store"

export function AppShell() {
  const sidebarOpen = useUiStore((s) => s.sidebarOpen)

  return (
    <div className="flex h-full">
      {sidebarOpen && (
        <div className="w-64 border-r border-gray-200 dark:border-gray-700 shadow-sm shrink-0">
          <Sidebar />
        </div>
      )}
      <div className="flex-1 flex flex-col min-w-0">
        <ErrorBoundary>
          <Outlet />
        </ErrorBoundary>
      </div>
    </div>
  )
}
