import { describe, it, expect } from "vitest"
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

  it("defaultAgent is build by default", () => {
    expect(useUiStore.getState().defaultAgent).toBe("build")
  })

  it("sets defaultAgent", () => {
    useUiStore.getState().setDefaultAgent("general")
    expect(useUiStore.getState().defaultAgent).toBe("general")
    // Reset for other tests
    useUiStore.getState().setDefaultAgent("build")
    expect(useUiStore.getState().defaultAgent).toBe("build")
  })
})
