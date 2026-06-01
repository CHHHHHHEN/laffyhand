import { describe, it, expect, beforeEach } from "vitest"
import { render, screen, fireEvent, act } from "@testing-library/react"
import { TodoPanel } from "./TodoPanel"
import { useTodoStore } from "@/stores/todo-store"
import { useUiStore } from "@/stores/ui-store"
import type { TodoItem } from "@/types/session"

function makeTask(overrides: Partial<TodoItem> = {}): TodoItem {
  return {
    id: "t1",
    sessionId: "sess-1",
    content: "Test task",
    status: "pending",
    priority: "medium",
    dependsOn: [],
    blockedBy: [],
    createdAt: "2025-01-01T00:00:00",
    updatedAt: "2025-01-01T00:00:00",
    completedAt: null,
    taskToolId: null,
    ...overrides,
  }
}

beforeEach(() => {
  useUiStore.getState().setTodoPanelOpen(true)
  useTodoStore.setState({ tasks: [] })
})

describe("TodoPanel", () => {
  it("renders header with total count", () => {
    act(() => { useUiStore.getState().setTodoPanelOpen(true) })
    useTodoStore.getState().setTasks([
      makeTask({ id: "a" }),
      makeTask({ id: "b" }),
    ])
    render(<TodoPanel />)
    expect(screen.getByText(/Tasks/)).toBeInTheDocument()
    const countElements = screen.getAllByText(/\(2\)/)
    expect(countElements.length).toBeGreaterThanOrEqual(1)
  })

  it("groups tasks into correct columns by status", () => {
    act(() => { useUiStore.getState().setTodoPanelOpen(true) })
    useTodoStore.getState().setTasks([
      makeTask({ id: "a", content: "Blocked task", status: "blocked" }),
      makeTask({ id: "b", content: "Pending task", status: "pending" }),
      makeTask({ id: "c", content: "Running task", status: "in_progress" }),
      makeTask({ id: "d", content: "Done task", status: "completed" }),
      makeTask({ id: "e", content: "Cancelled task", status: "cancelled" }),
    ])
    render(<TodoPanel />)
    expect(screen.getByText("Blocked task")).toBeInTheDocument()
    expect(screen.getByText("Pending task")).toBeInTheDocument()
    expect(screen.getByText("Running task")).toBeInTheDocument()
    expect(screen.getByText("Done task")).toBeInTheDocument()
    expect(screen.getByText("Cancelled task")).toBeInTheDocument()
  })

  it("shows 0 count when no tasks", () => {
    act(() => { useUiStore.getState().setTodoPanelOpen(true) })
    render(<TodoPanel />)
    const zeroCounts = screen.getAllByText(/\(0\)/)
    expect(zeroCounts.length).toBeGreaterThanOrEqual(1)
  })

  it("close button hides the panel", () => {
    act(() => { useUiStore.getState().setTodoPanelOpen(true) })
    render(<TodoPanel />)
    const closeBtn = screen.getByTitle(/Close tasks panel/)
    fireEvent.click(closeBtn)
    expect(useUiStore.getState().todoPanelOpen).toBe(false)
  })

  it("does not render content when panel is closed", () => {
    useUiStore.getState().setTodoPanelOpen(false)
    useTodoStore.getState().addTask(makeTask({ content: "Hidden task" }))
    render(<TodoPanel />)
    expect(screen.queryByText("Hidden task")).not.toBeInTheDocument()
  })

  it("renders all five column labels", () => {
    act(() => { useUiStore.getState().setTodoPanelOpen(true) })
    render(<TodoPanel />)
    expect(screen.getByText(/Blocked/)).toBeInTheDocument()
    expect(screen.getByText(/Pending/)).toBeInTheDocument()
    expect(screen.getByText(/In Progress/)).toBeInTheDocument()
    expect(screen.getByText(/Completed/)).toBeInTheDocument()
    expect(screen.getByText(/Cancelled/)).toBeInTheDocument()
  })
})
