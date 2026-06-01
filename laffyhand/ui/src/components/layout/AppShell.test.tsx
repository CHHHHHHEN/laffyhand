import { describe, it, expect, beforeEach } from "vitest"
import { render, screen, fireEvent } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { AppShell } from "./AppShell"
import { useUiStore } from "@/stores/ui-store"

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
})

beforeEach(() => {
  useUiStore.setState({ sidebarOpen: true, busyMode: "interrupt" })
})

function renderAppShell() {
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/chat"]}>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/chat" element={<div data-testid="chat-page">Chat Page</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe("AppShell", () => {
  it("renders sidebar when open", () => {
    useUiStore.setState({ sidebarOpen: true })
    renderAppShell()
    expect(screen.getByTitle("Close sidebar")).toBeInTheDocument()
  })

  it("hides sidebar when closed", () => {
    useUiStore.setState({ sidebarOpen: false })
    renderAppShell()
    expect(screen.getByTitle("Open sidebar")).toBeInTheDocument()
    expect(screen.queryByTitle("Close sidebar")).not.toBeInTheDocument()
  })

  it("toggles sidebar on button click", () => {
    renderAppShell()
    const toggleBtn = screen.getByTitle("Close sidebar")
    fireEvent.click(toggleBtn)
    expect(useUiStore.getState().sidebarOpen).toBe(false)
    expect(screen.getByTitle("Open sidebar")).toBeInTheDocument()
  })

  it("shows branding text", () => {
    renderAppShell()
    expect(screen.getByText("Laffyhand")).toBeInTheDocument()
  })

  it("renders child route content", () => {
    renderAppShell()
    expect(screen.getByTestId("chat-page")).toBeInTheDocument()
    expect(screen.getByText("Chat Page")).toBeInTheDocument()
  })

  it("toggle button icon changes based on state", () => {
    useUiStore.setState({ sidebarOpen: true })
    const { rerender } = renderAppShell()
    expect(screen.getByTitle("Close sidebar")).toBeInTheDocument()

    useUiStore.setState({ sidebarOpen: false })
    rerender(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/chat"]}>
          <Routes>
            <Route element={<AppShell />}>
              <Route path="/chat" element={<div data-testid="chat-page">Chat Page</div>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )
    expect(screen.getByTitle("Open sidebar")).toBeInTheDocument()
  })
})
