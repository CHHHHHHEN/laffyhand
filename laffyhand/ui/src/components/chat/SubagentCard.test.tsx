import { describe, it, expect } from "vitest"
import { render, screen, fireEvent } from "@testing-library/react"
import { SubagentCard, SubagentTreeCard } from "./SubagentCard"
import type { ActiveSubagent } from "@/types/session"
import type { SubagentTreeNode } from "@/lib/subagentTree"

function makeSubagent(overrides: Partial<ActiveSubagent> = {}): ActiveSubagent {
  return {
    id: "sa-1",
    parentId: null,
    agentType: "explore",
    description: "Search the codebase for test files",
    mode: "foreground",
    depth: 0,
    status: "running",
    text: "",
    reasoning: "",
    tools: [],
    toolCount: 0,
    summary: undefined,
    inputTokens: 0,
    outputTokens: 0,
    ...overrides,
  }
}

describe("SubagentCard", () => {
  describe("header", () => {
    it("shows agent type name", () => {
      render(<SubagentCard subagent={makeSubagent({ agentType: "general" })} />)
      expect(screen.getByText("general")).toBeInTheDocument()
    })

    it("shows running label when status is running", () => {
      render(<SubagentCard subagent={makeSubagent({ status: "running" })} />)
      expect(screen.getByText("running")).toBeInTheDocument()
    })

    it("shows tool count in header when completed with tools", () => {
      const sub = makeSubagent({ toolCount: 3, status: "completed" })
      render(<SubagentCard subagent={sub} />)
      expect(screen.getByText("3 tools")).toBeInTheDocument()
    })

    it("is collapsed by default when running", () => {
      const sub = makeSubagent({ status: "running", summary: "secret summary" })
      render(<SubagentCard subagent={sub} />)
      expect(screen.queryByText("secret summary")).not.toBeInTheDocument()
    })

    it("is collapsed by default when completed", () => {
      const sub = makeSubagent({ status: "completed", summary: "done summary" })
      render(<SubagentCard subagent={sub} />)
      expect(screen.queryByText("done summary")).not.toBeInTheDocument()
    })

    it("shows description text in header", () => {
      const sub = makeSubagent({ description: "Find all TODO comments" })
      render(<SubagentCard subagent={sub} />)
      expect(screen.getByText("Find all TODO comments")).toBeInTheDocument()
    })
  })

  describe("expanded content", () => {
    it("shows summary when expanded", () => {
      const sub = makeSubagent({
        status: "completed",
        summary: "Found 42 results",
      })
      render(<SubagentCard subagent={sub} />)
      fireEvent.click(screen.getByText("explore"))
      expect(screen.getByText("Found 42 results")).toBeInTheDocument()
    })

    it("shows token usage when expanded", () => {
      const sub = makeSubagent({
        status: "completed",
        inputTokens: 150,
        outputTokens: 75,
      })
      render(<SubagentCard subagent={sub} />)
      fireEvent.click(screen.getByText("explore"))
      expect(screen.getByText((c) => c.includes("150"))).toBeInTheDocument()
      expect(screen.getByText((c) => c.includes("75"))).toBeInTheDocument()
    })
  })

  describe("interaction", () => {
    it("toggles expanded state on header click", () => {
      const sub = makeSubagent({ status: "completed", summary: "hidden content" })
      render(<SubagentCard subagent={sub} />)
      expect(screen.queryByText("hidden content")).not.toBeInTheDocument()
      fireEvent.click(screen.getByText("explore"))
      expect(screen.getByText("hidden content")).toBeInTheDocument()
      fireEvent.click(screen.getByText("explore"))
      expect(screen.queryByText("hidden content")).not.toBeInTheDocument()
    })
  })

  describe("depth indentation", () => {
    it("applies marginLeft based on depth", () => {
      const sub = makeSubagent()
      const { container } = render(<SubagentCard subagent={sub} depth={2} />)
      const inner = container.firstChild as HTMLElement
      expect(inner.style.marginLeft).toBe("32px")
    })
  })
})

describe("SubagentTreeCard", () => {
  const root: ActiveSubagent = makeSubagent({
    id: "root",
    agentType: "general",
    description: "Main task",
    status: "completed",
  })

  const child: ActiveSubagent = makeSubagent({
    id: "child-1",
    parentId: "root",
    agentType: "explore",
    description: "Sub task",
    status: "completed",
  })

  const grandchild: ActiveSubagent = makeSubagent({
    id: "gc-1",
    parentId: "child-1",
    agentType: "explore",
    description: "Grandchild task",
    status: "completed",
  })

  const flatAgg = {
    totalTools: 0, activeCount: 0, descendantCount: 0,
    totalDuration: 0, maxDepthFromHere: 0, inputTokens: 0, outputTokens: 0,
  }
  const flatTree: SubagentTreeNode[] = [
    { item: root, children: [], aggregate: flatAgg },
    { item: child, children: [], aggregate: flatAgg },
    { item: grandchild, children: [], aggregate: flatAgg },
  ]

  it("renders root level subagent", () => {
    render(<SubagentTreeCard subagent={root} tree={flatTree} />)
    expect(screen.getByText("Main task")).toBeInTheDocument()
  })

  it("renders child subagents recursively after expanding root", () => {
    render(<SubagentTreeCard subagent={root} tree={flatTree} depth={0} />)
    fireEvent.click(screen.getByText("Main task"))
    expect(screen.getByText("Sub task")).toBeInTheDocument()
    fireEvent.click(screen.getByText("Sub task"))
    expect(screen.getByText("Grandchild task")).toBeInTheDocument()
  })

  it("passes increased depth to children after expanding", () => {
    const { container } = render(<SubagentTreeCard subagent={root} tree={flatTree} depth={0} />)
    fireEvent.click(screen.getByText("Main task"))
    fireEvent.click(screen.getByText("Sub task"))

    const allCards = container.querySelectorAll('[style*="margin-left"]')
    const margins = Array.from(allCards).map((el) => (el as HTMLElement).style.marginLeft)
    expect(margins).toContain("0px")
    expect(margins).toContain("16px")
    expect(margins).toContain("32px")
  })
})
