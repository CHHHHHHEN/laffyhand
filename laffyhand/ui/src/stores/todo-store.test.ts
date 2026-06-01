import { describe, it, expect, beforeEach } from "vitest"
import { useTodoStore } from "./todo-store"
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
  useTodoStore.setState({ tasks: [] })
})

describe("todo-store", () => {
  it("setTasks replaces all tasks", () => {
    const tasks = [makeTask({ id: "a" }), makeTask({ id: "b" })]
    useTodoStore.getState().setTasks(tasks)
    expect(useTodoStore.getState().tasks).toHaveLength(2)
    expect(useTodoStore.getState().tasks[0]!.id).toBe("a")
  })

  it("addTask appends to list", () => {
    useTodoStore.getState().addTask(makeTask({ id: "t1" }))
    useTodoStore.getState().addTask(makeTask({ id: "t2" }))
    expect(useTodoStore.getState().tasks).toHaveLength(2)
    expect(useTodoStore.getState().tasks[1]!.id).toBe("t2")
  })

  it("updateTask modifies existing task in place", () => {
    useTodoStore.getState().addTask(makeTask({ id: "t1", status: "pending" }))
    useTodoStore.getState().updateTask("t1", { status: "completed" })
    const task = useTodoStore.getState().tasks[0]!
    expect(task.status).toBe("completed")
  })

  it("updateTask does nothing for unknown id", () => {
    useTodoStore.getState().addTask(makeTask({ id: "t1" }))
    useTodoStore.getState().updateTask("no-such", { status: "completed" })
    expect(useTodoStore.getState().tasks).toHaveLength(1)
    expect(useTodoStore.getState().tasks[0]!.id).toBe("t1")
  })

  it("removeTask removes only the matching task", () => {
    useTodoStore.getState().setTasks([
      makeTask({ id: "a", content: "Task A" }),
      makeTask({ id: "b", content: "Task B" }),
    ])
    useTodoStore.getState().removeTask("a")
    const remaining = useTodoStore.getState().tasks
    expect(remaining).toHaveLength(1)
    expect(remaining[0]!.id).toBe("b")
  })

  it("removeTask does nothing for unknown id", () => {
    useTodoStore.getState().addTask(makeTask({ id: "t1" }))
    useTodoStore.getState().removeTask("no-such")
    expect(useTodoStore.getState().tasks).toHaveLength(1)
  })

  it("clearTasks empties the list", () => {
    useTodoStore.getState().setTasks([
      makeTask({ id: "a" }),
      makeTask({ id: "b" }),
    ])
    useTodoStore.getState().clearTasks()
    expect(useTodoStore.getState().tasks).toHaveLength(0)
  })

  it("updateTask can change multiple fields", () => {
    useTodoStore.getState().addTask(makeTask({ id: "t1" }))
    useTodoStore.getState().updateTask("t1", {
      status: "in_progress",
      priority: "high",
    })
    const task = useTodoStore.getState().tasks[0]!
    expect(task.status).toBe("in_progress")
    expect(task.priority).toBe("high")
  })
})
