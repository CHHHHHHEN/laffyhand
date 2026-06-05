import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen, fireEvent } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { Sidebar } from "./Sidebar"
import { useSessionStore } from "@/stores/session-store"
import type { Session } from "@/types/session"

const mockSessions: Session[] = [
  { id: "s1", title: "Project Setup", status: "active", messageCount: 15, turnCount: 3, createdAt: "2026-05-30T10:00:00Z", updatedAt: "2026-05-30T12:00:00Z" },
  { id: "s2", title: "Debug Session", status: "active", messageCount: 42, turnCount: 8, createdAt: "2026-05-29T10:00:00Z", updatedAt: "2026-05-30T10:00:00Z" },
  { id: "s3", title: null, status: "active", messageCount: 3, turnCount: 1, createdAt: "2026-05-28T10:00:00Z", updatedAt: "2026-05-28T11:00:00Z" },
]

const mockUseSessions = {
  sessions: mockSessions,
  isLoading: false,
  error: null,
  refetch: vi.fn(),
  createSession: vi.fn().mockResolvedValue("new-session-id"),
  deleteSession: vi.fn().mockResolvedValue(undefined),
  forkSession: vi.fn().mockResolvedValue("forked-session-id"),
  isCreating: false,
  isDeleting: false,
  isForking: false,
}

const mockUseAgents = {
  agents: [
    { name: "build", description: "Main coding agent", mode: "primary", system_prompt: "", model: null },
  ],
  isLoading: false,
  error: null,
}

vi.mock("@/hooks/use-sessions", () => ({
  useSessions: () => mockUseSessions,
  useAgents: () => mockUseAgents,
}))

vi.mock("@/lib/rpc", () => ({
  rpcClient: {
    sessionSetTitle: vi.fn().mockResolvedValue(undefined),
  },
}))

// Mock navigation
const mockNavigate = vi.fn()
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom")
  return {
    ...actual,
    useNavigate: () => mockNavigate,
    useParams: () => ({ sessionId: "s1" }),
  }
})

beforeEach(() => {
  vi.clearAllMocks()
  useSessionStore.setState({ activeSessionId: "s1", activeSessionIds: [] })
})

function renderSidebar() {
  return render(
    <MemoryRouter>
      <Sidebar />
    </MemoryRouter>,
  )
}

describe("Sidebar", () => {
  // ── 基本渲染 ──

  it("renders new session button", () => {
    renderSidebar()
    expect(screen.getByText("New Session")).toBeInTheDocument()
  })

  it("does not render fork button (replaced by /fork command)", () => {
    renderSidebar()
    expect(screen.queryByText("Fork")).not.toBeInTheDocument()
  })

  it("renders session list", () => {
    renderSidebar()
    expect(screen.getByText("Project Setup")).toBeInTheDocument()
    expect(screen.getByText("Debug Session")).toBeInTheDocument()
    expect(screen.getByText("Untitled")).toBeInTheDocument() // title is null
  })

  it("shows session metadata for each session", () => {
    renderSidebar()
    const timeLabels = document.querySelectorAll("div.text-xs.text-\\[var\\(--text-muted\\)\\]")
    expect(timeLabels.length).toBe(mockSessions.length)
  })

  it("highlights active session", () => {
    renderSidebar()
    const titleEl = screen.getByText("Project Setup")
    expect(titleEl.className).toContain("text-[var(--accent)]")
  })

  // ── New Session ──

  it("creates new session and navigates", async () => {
    renderSidebar()
    fireEvent.click(screen.getByText("New Session"))
    await vi.waitFor(() => {
      expect(mockUseSessions.createSession).toHaveBeenCalled()
      expect(mockNavigate).toHaveBeenCalledWith("/chat/new-session-id")
    })
  })

  // ── 搜索过滤 ──

  it("shows search input with placeholder", () => {
    renderSidebar()
    expect(screen.getByPlaceholderText("Search sessions...")).toBeInTheDocument()
  })

  it("filters sessions by title", async () => {
    renderSidebar()
    const searchInput = screen.getByPlaceholderText("Search sessions...")
    fireEvent.input(searchInput, { target: { value: "Debug" } })

    expect(screen.getByText("Debug Session")).toBeInTheDocument()
    expect(screen.queryByText("Project Setup")).not.toBeInTheDocument()
  })

  it("filters sessions by search term", () => {
    renderSidebar()
    const searchInput = screen.getByPlaceholderText("Search sessions...")
    fireEvent.input(searchInput, { target: { value: "Setup" } })

    expect(screen.getByText("Project Setup")).toBeInTheDocument()
    expect(screen.queryByText("Debug Session")).not.toBeInTheDocument()
  })

  it("shows no results message when filter matches nothing", () => {
    renderSidebar()
    const searchInput = screen.getByPlaceholderText("Search sessions...")
    fireEvent.input(searchInput, { target: { value: "zzznonexistent" } })

    expect(screen.getByText(/No sessions match/)).toBeInTheDocument()
    expect(screen.queryByText("Project Setup")).not.toBeInTheDocument()
  })

  // ── 删除 ──

  it("shows delete button for each session", () => {
    renderSidebar()
    const deleteButtons = screen.getAllByTitle("Delete")
    expect(deleteButtons).toHaveLength(3)
  })

  it("navigates on session click", () => {
    renderSidebar()
    fireEvent.click(screen.getByText("Project Setup"))
    expect(mockNavigate).toHaveBeenCalledWith("/chat/s1")
  })

  // ── 空状态 ──

  it("shows empty state when no sessions", () => {
    mockUseSessions.sessions = []
    renderSidebar()
    expect(screen.getByText("No sessions yet")).toBeInTheDocument()
    mockUseSessions.sessions = mockSessions
  })

  // ── 时间格式 ──

  it("shows relative time in short format", () => {
    renderSidebar()
    const textContent = document.body.textContent || ""
    expect(textContent).toMatch(/\d+[dhms]|just now/)
  })
})
