import { describe, it, expect } from "vitest"
import { render, screen } from "@testing-library/react"
import { TodoColumn } from "./TodoColumn"
import type { TodoItem } from "@/types/session"

function makeTask(overrides: Partial<TodoItem> = {}): TodoItem {
  return {
    id: "t1",
    sessionId: "sess-1",
    content: "Test task",
    status: "pending",
    dependsOn: [],
    blockedBy: [],
    createdAt: "2025-01-01T00:00:00",
    updatedAt: "2025-01-01T00:00:00",
    completedAt: null,
    taskToolId: null,
    ...overrides,
  }
}

describe("TodoColumn", () => {
  it("renders column label with count", () => {
    render(<TodoColumn status="pending" tasks={[makeTask(), makeTask()]} />)
    expect(screen.getByText(/Pending/)).toBeInTheDocument()
    expect(screen.getByText(/\(2\)/)).toBeInTheDocument()
  })

  it("renders all task cards", () => {
    const tasks = [
      makeTask({ id: "a", content: "Task A" }),
      makeTask({ id: "b", content: "Task B" }),
    ]
    render(<TodoColumn status="in_progress" tasks={tasks} />)
    expect(screen.getByText("Task A")).toBeInTheDocument()
    expect(screen.getByText("Task B")).toBeInTheDocument()
  })

  it("shows empty indicator when no tasks", () => {
    render(<TodoColumn status="blocked" tasks={[]} />)
    expect(screen.getByText("No tasks")).toBeInTheDocument()
    expect(screen.getByText(/Blocked/)).toBeInTheDocument()
    expect(screen.getByText(/\(0\)/)).toBeInTheDocument()
  })

  it("displays correct label for completed status", () => {
    render(<TodoColumn status="completed" tasks={[]} />)
    expect(screen.getByText(/Completed/)).toBeInTheDocument()
  })
})
