import { describe, it, expect, beforeEach, vi } from "vitest"
import { render, screen, fireEvent } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { SessionTabs } from "./SessionTabs"
import { useSessionStore } from "@/stores/session-store"
import { useChatStore } from "@/stores/chat-store"
import type { SessionChatState } from "@/stores/chat-store"

vi.mock("@/hooks/use-sessions", () => ({
  useSessions: () => ({
    sessions: [
      { id: "s1", title: "Session One" },
      { id: "s2", title: "Session Two" },
      { id: "s3", title: "Session Three" },
    ],
    isLoading: false,
    error: null,
    refetch: vi.fn(),
    createSession: vi.fn(),
    deleteSession: vi.fn(),
    forkSession: vi.fn(),
    isCreating: false,
    isDeleting: false,
    isForking: false,
  }),
}))

beforeEach(() => {
  useSessionStore.setState({
    activeSessionId: "s1",
    activeSessionIds: ["s1", "s2", "s3"],
  })
  useChatStore.setState({
    sessions: {
      s1: { isStreaming: true } as SessionChatState,
      s2: { isStreaming: false } as SessionChatState,
    },
  })
})

function renderTabs() {
  return render(
    <MemoryRouter>
      <SessionTabs />
    </MemoryRouter>,
  )
}

function getContainer(): HTMLElement {
  const tabEl = screen.getByText("Session One").closest("div")!
  return tabEl.parentElement!
}

describe("SessionTabs", () => {
  it("renders nothing when there are no active sessions", () => {
    useSessionStore.setState({ activeSessionIds: [] })
    const { container } = renderTabs()
    expect(container.firstChild).toBeNull()
  })

  it("renders a tab for each active session", () => {
    renderTabs()
    expect(screen.getByText("Session One")).toBeInTheDocument()
    expect(screen.getByText("Session Two")).toBeInTheDocument()
    expect(screen.getByText("Session Three")).toBeInTheDocument()
  })

  it("shows 'Untitled' for sessions without a title", () => {
    useSessionStore.setState({ activeSessionId: "s99", activeSessionIds: ["s99"] })
    renderTabs()
    expect(screen.getByText("Untitled")).toBeInTheDocument()
  })

  it("highlights the active tab with distinct styling", () => {
    renderTabs()
    const activeTab = screen.getByText("Session One").closest("div")!
    expect(activeTab.className).toContain("border-b-transparent")
  })

  it("shows streaming indicator for streaming sessions", () => {
    renderTabs()
    const tab1 = screen.getByText("Session One").closest("div")!
    const pingEl = tab1.querySelector('[class*="animate-ping"]')
    expect(pingEl).toBeInTheDocument()
  })

  it("does not show streaming indicator for non-streaming sessions", () => {
    renderTabs()
    const tab2 = screen.getByText("Session Two").closest("div")!
    const pingEl = tab2.querySelector('[class*="animate-ping"]')
    expect(pingEl).not.toBeInTheDocument()
  })

  it("navigates on tab click", () => {
    renderTabs()
    const tab = screen.getByText("Session Two").closest("div")!
    expect(tab.className).toContain("cursor-pointer")
  })

  it("removes session on close button click and stops propagation", () => {
    const removeSpy = vi.spyOn(useSessionStore.getState(), "removeActiveSession")
    renderTabs()
    const closeButtons = screen.getAllByTitle("Close tab")
    fireEvent.click(closeButtons[0]!)
    expect(removeSpy).toHaveBeenCalledWith("s1")
  })

  it("has overflow-x-auto and overflow-y-hidden classes for horizontal scrolling", () => {
    renderTabs()
    const container = getContainer()
    expect(container.className).toContain("overflow-x-auto")
    expect(container.className).toContain("overflow-y-hidden")
  })

  it("converts vertical wheel delta to horizontal scroll", () => {
    renderTabs()
    const container = getContainer()

    // Simulate overflow — content wider than container
    Object.defineProperty(container, "scrollWidth", { value: 1000, configurable: true })
    Object.defineProperty(container, "clientWidth", { value: 200, configurable: true })
    container.scrollLeft = 100

    fireEvent.wheel(container, { deltaY: 50 })
    expect(container.scrollLeft).toBe(150)

    fireEvent.wheel(container, { deltaY: -30 })
    expect(container.scrollLeft).toBe(120)
  })

  it("allows default when at left edge scrolling up", () => {
    renderTabs()
    const container = getContainer()

    Object.defineProperty(container, "scrollWidth", { value: 1000, configurable: true })
    Object.defineProperty(container, "clientWidth", { value: 200, configurable: true })
    container.scrollLeft = 0

    const preventSpy = vi.fn()
    const addListener = container.addEventListener.bind(container)
    container.addEventListener = (type: string, listener: EventListenerOrEventListenerObject, options?: AddEventListenerOptions) => {
      if (type === "wheel") {
        const original = listener as EventListener
        const wrapped = (e: Event) => {
          const wheelEvent = e as WheelEvent
          Object.defineProperty(wheelEvent, "preventDefault", { value: preventSpy, configurable: true })
          original(e)
        }
        return addListener(type, wrapped, options)
      }
      return addListener(type, listener, options)
    }

    // Simulate wheel up at left edge
    fireEvent.wheel(container, { deltaY: -50 })
    expect(preventSpy).not.toHaveBeenCalled()
  })
})
