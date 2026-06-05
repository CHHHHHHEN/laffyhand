import { describe, it, expect } from "vitest"
import { buildSubagentTree, aggregate, flattenTree } from "./subagentTree"
import type { ActiveSubagent } from "@/types/session"

function makeSubagent(overrides: Partial<ActiveSubagent> & { id: string }): ActiveSubagent {
  return {
    parentId: null,
    agentType: "explore",
    description: "",
    mode: "foreground",
    depth: 0,
    status: "running",
    text: "",
    reasoning: "",
    tools: [],
    toolCount: 0,
    events: [],
    summary: undefined,
    inputTokens: 0,
    outputTokens: 0,
    ...overrides,
  }
}

describe("buildSubagentTree", () => {
  it("returns empty array for no items", () => {
    expect(buildSubagentTree([])).toEqual([])
  })

  it("builds flat tree for root items", () => {
    const items = [
      makeSubagent({ id: "a", description: "first" }),
      makeSubagent({ id: "b", description: "second" }),
    ]
    const tree = buildSubagentTree(items)
    expect(tree).toHaveLength(2)
    expect(tree[0]!.item.description).toBe("first")
    expect(tree[1]!.item.description).toBe("second")
  })

  it("nests children under parents", () => {
    const items = [
      makeSubagent({ id: "parent", description: "root" }),
      makeSubagent({ id: "child", parentId: "parent", description: "leaf" }),
    ]
    const tree = buildSubagentTree(items)
    expect(tree).toHaveLength(1)
    expect(tree[0]!.item.id).toBe("parent")
    expect(tree[0]!.children).toHaveLength(1)
    expect(tree[0]!.children[0]!.item.id).toBe("child")
  })

  it("promotes orphaned items to root when parent unknown", () => {
    const items = [
      makeSubagent({ id: "orphan", parentId: "nonexistent", description: "lost" }),
    ]
    const tree = buildSubagentTree(items)
    expect(tree).toHaveLength(1)
    expect(tree[0]!.item.id).toBe("orphan")
  })

  it("sorts siblings by depth then id", () => {
    const items = [
      makeSubagent({ id: "z", depth: 1 }),
      makeSubagent({ id: "a", depth: 0 }),
      makeSubagent({ id: "m", depth: 0 }),
    ]
    const tree = buildSubagentTree(items)
    expect(tree[0]!.item.id).toBe("a")
    expect(tree[1]!.item.id).toBe("m")
    expect(tree[2]!.item.id).toBe("z")
  })

  it("handles multi-level nesting", () => {
    const items = [
      makeSubagent({ id: "l1", description: "level1" }),
      makeSubagent({ id: "l2", parentId: "l1", description: "level2" }),
      makeSubagent({ id: "l3", parentId: "l2", description: "level3" }),
    ]
    const tree = buildSubagentTree(items)
    expect(tree[0]!.children[0]!.children[0]!.item.id).toBe("l3")
  })
})

describe("aggregate", () => {
  it("aggregates tool counts from children", () => {
    const parent = makeSubagent({ id: "p", toolCount: 1 })
    const child = makeSubagent({ id: "c", toolCount: 3 })
    const childNode = { item: child, children: [], aggregate: aggregate(child, []) }
    const result = aggregate(parent, [childNode])
    expect(result.totalTools).toBe(4)
  })

  it("counts active descendants", () => {
    const running = makeSubagent({ id: "r", status: "running" })
    const completed = makeSubagent({ id: "c", status: "completed" })
    const runningNode = { item: running, children: [], aggregate: aggregate(running, []) }
    const completedNode = { item: completed, children: [], aggregate: aggregate(completed, []) }
    const result = aggregate(makeSubagent({ id: "p", status: "completed" }), [runningNode, completedNode])
    expect(result.activeCount).toBe(1)
  })

  it("computes max depth from children", () => {
    const deep = makeSubagent({ id: "deep" })
    const middle = makeSubagent({ id: "mid" })
    const deepNode = { item: deep, children: [], aggregate: aggregate(deep, []) }
    const midNode = {
      item: middle,
      children: [deepNode],
      aggregate: aggregate(middle, [deepNode]),
    }
    // middle has depth 0 + max child depth (deep has depth 0), so middle's maxDepthFromHere = 1
    expect(midNode.aggregate.maxDepthFromHere).toBe(1)
    // parent has depth 0 + max child depth (middle has maxDepthFromHere=1), so parent's = 2
    const result = aggregate(makeSubagent({ id: "p" }), [midNode])
    expect(result.maxDepthFromHere).toBe(2)
  })

  it("aggregates token counts", () => {
    const child = makeSubagent({ id: "c", inputTokens: 10, outputTokens: 5 })
    const childNode = { item: child, children: [], aggregate: aggregate(child, []) }
    const result = aggregate(makeSubagent({ id: "p", inputTokens: 3, outputTokens: 2 }), [childNode])
    expect(result.inputTokens).toBe(13)
    expect(result.outputTokens).toBe(7)
  })

  it("totalDuration is always 0 (placeholder)", () => {
    const result = aggregate(makeSubagent({ id: "x" }), [])
    expect(result.totalDuration).toBe(0)
  })
})

describe("flattenTree", () => {
  it("flattens nested tree depth-first", () => {
    const items = [
      makeSubagent({ id: "a" }),
      makeSubagent({ id: "a1", parentId: "a" }),
      makeSubagent({ id: "a2", parentId: "a" }),
      makeSubagent({ id: "b" }),
    ]
    const tree = buildSubagentTree(items)
    const flat = flattenTree(tree)
    expect(flat).toHaveLength(4)
    expect(flat[0]!.item.id).toBe("a")
    expect(flat[1]!.item.id).toBe("a1")
    expect(flat[2]!.item.id).toBe("a2")
    expect(flat[3]!.item.id).toBe("b")
  })

  it("returns empty array for empty tree", () => {
    expect(flattenTree([])).toEqual([])
  })
})
