import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen, fireEvent } from "@testing-library/react"
import { PermissionModal } from "./PermissionModal"
import { useChatStore } from "@/stores/chat-store"
import { rpcClient } from "@/lib/rpc"

vi.mock("@/lib/rpc", () => ({
  rpcClient: {
    permissionRespond: vi.fn(),
  },
}))

beforeEach(() => {
  vi.clearAllMocks()
  useChatStore.setState({ pendingPermission: null })
})

describe("PermissionModal", () => {
  it("renders nothing when no pending permission", () => {
    const { container } = render(<PermissionModal />)
    expect(container.innerHTML).toBe("")
  })

  it("renders permission and pattern text", () => {
    useChatStore.getState().setPendingPermission({
      requestId: "req-1",
      permission: "skill",
      pattern: "code-review",
    })
    render(<PermissionModal />)
    expect(screen.getByText("Allow skill 'code-review'?")).toBeInTheDocument()
  })

  it("shows three action buttons", () => {
    useChatStore.getState().setPendingPermission({
      requestId: "req-1",
      permission: "skill",
      pattern: "test",
    })
    render(<PermissionModal />)
    expect(screen.getByText("Deny")).toBeInTheDocument()
    expect(screen.getByText("Allow Once")).toBeInTheDocument()
    expect(screen.getByText("Always Allow")).toBeInTheDocument()
  })

  it("calls permissionRespond with 'deny' on Deny click", () => {
    useChatStore.getState().setPendingPermission({
      requestId: "req-1",
      permission: "skill",
      pattern: "test",
    })
    render(<PermissionModal />)
    fireEvent.click(screen.getByText("Deny"))
    expect(rpcClient.permissionRespond).toHaveBeenCalledWith("req-1", "deny")
  })

  it("calls permissionRespond with 'allow' on Allow Once click", () => {
    useChatStore.getState().setPendingPermission({
      requestId: "req-1",
      permission: "skill",
      pattern: "test",
    })
    render(<PermissionModal />)
    fireEvent.click(screen.getByText("Allow Once"))
    expect(rpcClient.permissionRespond).toHaveBeenCalledWith("req-1", "allow")
  })

  it("calls permissionRespond with 'always' on Always Allow click", () => {
    useChatStore.getState().setPendingPermission({
      requestId: "req-1",
      permission: "skill",
      pattern: "test",
    })
    render(<PermissionModal />)
    fireEvent.click(screen.getByText("Always Allow"))
    expect(rpcClient.permissionRespond).toHaveBeenCalledWith("req-1", "always")
  })

  it("clears pendingPermission after clicking any button", () => {
    useChatStore.getState().setPendingPermission({
      requestId: "req-1",
      permission: "skill",
      pattern: "test",
    })
    render(<PermissionModal />)
    fireEvent.click(screen.getByText("Deny"))
    expect(useChatStore.getState().pendingPermission).toBeNull()
  })

  it("handles rpc error gracefully", () => {
    vi.mocked(rpcClient.permissionRespond).mockRejectedValue(new Error("network error"))
    useChatStore.getState().setPendingPermission({
      requestId: "req-1",
      permission: "skill",
      pattern: "test",
    })
    render(<PermissionModal />)
    expect(() => fireEvent.click(screen.getByText("Deny"))).not.toThrow()
  })
})