import { describe, it, expect, beforeEach } from "vitest"
import { useTodoStore } from "./todo-store"
import type { TodoItem } from "@/types/session"

const SESSION_ID = "sess-1"

function makeTask(overrides: Partial<TodoItem> = {}): TodoItem {
  return {
    id: "t1",
    sessionId: SESSION_ID,
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
  useTodoStore.setState({ taskMap: {} })
})

describe("todo-store", () => {
  it("setSessionTasks stores tasks per session", () => {
    const tasks1 = [makeTask({ id: "a" }), makeTask({ id: "b" })]
    useTodoStore.getState().setSessionTasks("sess-1", tasks1)
    useTodoStore.getState().setSessionTasks("sess-2", [makeTask({ id: "c" })])
    expect(useTodoStore.getState().taskMap["sess-1"]).toHaveLength(2)
    expect(useTodoStore.getState().taskMap["sess-1"]![0]!.id).toBe("a")
    expect(useTodoStore.getState().taskMap["sess-2"]).toHaveLength(1)
    expect(useTodoStore.getState().taskMap["sess-2"]![0]!.id).toBe("c")
  })

  it("setSessionTasks replaces existing tasks for same session", () => {
    useTodoStore.getState().setSessionTasks(SESSION_ID, [makeTask({ id: "a" })])
    useTodoStore.getState().setSessionTasks(SESSION_ID, [makeTask({ id: "b" })])
    expect(useTodoStore.getState().taskMap[SESSION_ID]).toHaveLength(1)
    expect(useTodoStore.getState().taskMap[SESSION_ID]![0]!.id).toBe("b")
  })

  it("addTask appends to list for given session", () => {
    useTodoStore.getState().setSessionTasks(SESSION_ID, [makeTask({ id: "t1" })])
    useTodoStore.getState().addTask(SESSION_ID, makeTask({ id: "t2" }))
    expect(useTodoStore.getState().taskMap[SESSION_ID]).toHaveLength(2)
    expect(useTodoStore.getState().taskMap[SESSION_ID]![1]!.id).toBe("t2")
  })

  it("addTask creates new entry for unknown session", () => {
    useTodoStore.getState().addTask("sess-new", makeTask({ id: "t1" }))
    expect(useTodoStore.getState().taskMap["sess-new"]).toHaveLength(1)
  })

  it("updateTask modifies existing task in place", () => {
    useTodoStore.getState().addTask(SESSION_ID, makeTask({ id: "t1", status: "pending" }))
    useTodoStore.getState().updateTask(SESSION_ID, "t1", { status: "completed" })
    const task = useTodoStore.getState().taskMap[SESSION_ID]![0]!
    expect(task.status).toBe("completed")
  })

  it("updateTask does nothing for unknown id", () => {
    useTodoStore.getState().addTask(SESSION_ID, makeTask({ id: "t1" }))
    useTodoStore.getState().updateTask(SESSION_ID, "no-such", { status: "completed" })
    expect(useTodoStore.getState().taskMap[SESSION_ID]).toHaveLength(1)
    expect(useTodoStore.getState().taskMap[SESSION_ID]![0]!.id).toBe("t1")
  })

  it("updateTask does nothing for unknown session", () => {
    useTodoStore.getState().updateTask("no-such-session", "t1", { status: "completed" })
    expect(useTodoStore.getState().taskMap).toEqual({})
  })

  it("removeTask removes only the matching task", () => {
    useTodoStore.getState().setSessionTasks(SESSION_ID, [
      makeTask({ id: "a", content: "Task A" }),
      makeTask({ id: "b", content: "Task B" }),
    ])
    useTodoStore.getState().removeTask(SESSION_ID, "a")
    const remaining = useTodoStore.getState().taskMap[SESSION_ID]!
    expect(remaining).toHaveLength(1)
    expect(remaining[0]!.id).toBe("b")
  })

  it("removeTask does nothing for unknown id", () => {
    useTodoStore.getState().addTask(SESSION_ID, makeTask({ id: "t1" }))
    useTodoStore.getState().removeTask(SESSION_ID, "no-such")
    expect(useTodoStore.getState().taskMap[SESSION_ID]).toHaveLength(1)
  })

  it("removeTask does nothing for unknown session", () => {
    useTodoStore.getState().removeTask("no-such-session", "t1")
    expect(useTodoStore.getState().taskMap).toEqual({})
  })

  it("clearSessionTasks removes entry for that session", () => {
    useTodoStore.getState().setSessionTasks(SESSION_ID, [makeTask({ id: "a" })])
    useTodoStore.getState().setSessionTasks("sess-2", [makeTask({ id: "b" })])
    useTodoStore.getState().clearSessionTasks(SESSION_ID)
    expect(useTodoStore.getState().taskMap[SESSION_ID]).toBeUndefined()
    expect(useTodoStore.getState().taskMap["sess-2"]).toHaveLength(1)
  })

  it("clearSessionTasks does nothing for unknown session", () => {
    useTodoStore.getState().setSessionTasks(SESSION_ID, [makeTask({ id: "a" })])
    useTodoStore.getState().clearSessionTasks("no-such")
    expect(useTodoStore.getState().taskMap[SESSION_ID]).toHaveLength(1)
  })

  it("updateTask can change multiple fields", () => {
    useTodoStore.getState().addTask(SESSION_ID, makeTask({ id: "t1" }))
    useTodoStore.getState().updateTask(SESSION_ID, "t1", {
      status: "in_progress",
      priority: "high",
    })
    const task = useTodoStore.getState().taskMap[SESSION_ID]![0]!
    expect(task.status).toBe("in_progress")
    expect(task.priority).toBe("high")
  })
})
