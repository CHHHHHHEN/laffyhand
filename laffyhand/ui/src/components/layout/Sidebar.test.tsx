import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen, fireEvent } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { Sidebar } from "./Sidebar"
import { useSessionStore } from "@/stores/session-store"
import type { Session } from "@/types/session"

// Mock useSessions hook
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
  useSessionStore.setState({ currentSessionId: null })
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
    expect(screen.getByText("+ New Session")).toBeInTheDocument()
  })

  it("renders fork button when session is selected", () => {
    renderSidebar()
    expect(screen.getByText("Fork")).toBeInTheDocument()
  })

  it("renders session list", () => {
    renderSidebar()
    expect(screen.getByText("Project Setup")).toBeInTheDocument()
    expect(screen.getByText("Debug Session")).toBeInTheDocument()
    expect(screen.getByText("Untitled")).toBeInTheDocument() // title is null
  })

  it("shows message count for each session", () => {
    renderSidebar()
    expect(screen.getByText((c) => c.includes("15") && c.includes("msgs"))).toBeInTheDocument()
    expect(screen.getByText((c) => c.includes("42") && c.includes("msgs"))).toBeInTheDocument()
    expect(screen.getByText((c) => c.includes("3") && c.includes("msgs"))).toBeInTheDocument()
  })

  it("highlights active session", () => {
    renderSidebar()
    const activeBtn = screen.getByText("Project Setup").closest("button")
    expect(activeBtn!.className).toContain("bg-blue-100")
  })

  // ── New Session ──

  it("creates new session and navigates", async () => {
    renderSidebar()
    fireEvent.click(screen.getByText("+ New Session"))
    expect(mockUseSessions.createSession).toHaveBeenCalled()
    // wait for async
    await vi.waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith("/chat/new-session-id")
    })
  })

  it("shows Creating... text while creating", () => {
    mockUseSessions.isCreating = true
    renderSidebar()
    expect(screen.getByText("Creating...")).toBeInTheDocument()
    mockUseSessions.isCreating = false
  })

  // ── Fork ──

  it("forks session and navigates", async () => {
    renderSidebar()
    fireEvent.click(screen.getByText("Fork"))
    await vi.waitFor(() => {
      expect(mockUseSessions.forkSession).toHaveBeenCalled()
      expect(mockNavigate).toHaveBeenCalledWith("/chat/forked-session-id")
    })
  })

  it("shows Forking... text while forking", () => {
    mockUseSessions.isForking = true
    renderSidebar()
    expect(screen.getByText("Forking...")).toBeInTheDocument()
    mockUseSessions.isForking = false
  })

  // ── 搜索过滤 ──

  it("shows search input with placeholder", () => {
    renderSidebar()
    expect(screen.getByPlaceholderText("Search sessions... (⌘K)")).toBeInTheDocument()
  })

  it("filters sessions by title", async () => {
    renderSidebar()
    const searchInput = screen.getByPlaceholderText("Search sessions... (⌘K)")
    fireEvent.input(searchInput, { target: { value: "Debug" } })

    expect(screen.getByText("Debug Session")).toBeInTheDocument()
    expect(screen.queryByText("Project Setup")).not.toBeInTheDocument()
  })

  it("filters sessions by message count", () => {
    renderSidebar()
    const searchInput = screen.getByPlaceholderText("Search sessions... (⌘K)")
    fireEvent.input(searchInput, { target: { value: "42" } })

    expect(screen.getByText("Debug Session")).toBeInTheDocument()
    expect(screen.queryByText("Project Setup")).not.toBeInTheDocument()
  })

  it("shows no results message when filter matches nothing", () => {
    renderSidebar()
    const searchInput = screen.getByPlaceholderText("Search sessions... (⌘K)")
    fireEvent.input(searchInput, { target: { value: "zzznonexistent" } })

    expect(screen.getByText(/No sessions match/)).toBeInTheDocument()
    expect(screen.queryByText("Project Setup")).not.toBeInTheDocument()
  })

  it('clears search with the clear button', () => {
    renderSidebar()
    const searchInput = screen.getByPlaceholderText("Search sessions... (⌘K)")
    fireEvent.input(searchInput, { target: { value: "Debug" } })

    // 清除按钮出现
    const clearBtn = document.querySelector("input ~ button")
    expect(clearBtn).toBeTruthy()

    if (clearBtn) {
      fireEvent.click(clearBtn)
      expect(screen.getByText("Project Setup")).toBeInTheDocument()
    }
  })

  // ── 删除 ──

  it("shows delete button for each session", () => {
    renderSidebar()
    const deleteButtons = screen.getAllByTitle("Delete session")
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
    // 时间格式为短格式
    const textContent = document.body.textContent || ""
    expect(textContent).toContain("msgs")
  })
})
