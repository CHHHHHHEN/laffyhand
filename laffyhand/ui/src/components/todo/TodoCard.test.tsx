import { describe, it, expect } from "vitest"
import { render, screen } from "@testing-library/react"
import { TodoCard } from "./TodoCard"
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

describe("TodoCard", () => {
  it("renders task content", () => {
    render(<TodoCard task={makeTask({ content: "Hello world" })} />)
    expect(screen.getByText("Hello world")).toBeInTheDocument()
  })

  it("shows blocked_by when present", () => {
    render(<TodoCard task={makeTask({ blockedBy: ["t0"], status: "blocked" })} />)
    expect(screen.getByText(/blocked by/)).toBeInTheDocument()
  })

  it("shows depends_on when blocked_by is empty", () => {
    render(<TodoCard task={makeTask({ dependsOn: ["t0", "t1"] })} />)
    expect(screen.getByText(/depends on/)).toBeInTheDocument()
  })

  it("does not show depends_on when blocked_by is present", () => {
    render(<TodoCard task={makeTask({ dependsOn: ["t0"], blockedBy: ["t0"], status: "blocked" })} />)
    expect(screen.getByText(/blocked by/)).toBeInTheDocument()
    expect(screen.queryByText(/depends on/)).not.toBeInTheDocument()
  })

  it("does not show dependency section when both arrays empty", () => {
    render(<TodoCard task={makeTask({ dependsOn: [], blockedBy: [] })} />)
    expect(screen.queryByText(/blocked by|depends on/)).not.toBeInTheDocument()
  })

  it("renders blocked status icon", () => {
    const { container } = render(<TodoCard task={makeTask({ status: "blocked" })} />)
    expect(container.textContent).toContain("⊘")
  })
})
