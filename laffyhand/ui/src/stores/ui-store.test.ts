import { describe, it, expect, beforeEach } from "vitest"
import { useUiStore } from "./ui-store"

describe("ui-store", () => {
  it("sidebar is open by default", () => {
    expect(useUiStore.getState().sidebarOpen).toBe(true)
  })

  it("toggles sidebar", () => {
    useUiStore.getState().toggleSidebar()
    expect(useUiStore.getState().sidebarOpen).toBe(false)
    useUiStore.getState().toggleSidebar()
    expect(useUiStore.getState().sidebarOpen).toBe(true)
  })

  it("sets sidebar explicitly", () => {
    useUiStore.getState().setSidebarOpen(false)
    expect(useUiStore.getState().sidebarOpen).toBe(false)
    useUiStore.getState().setSidebarOpen(true)
    expect(useUiStore.getState().sidebarOpen).toBe(true)
  })
})
