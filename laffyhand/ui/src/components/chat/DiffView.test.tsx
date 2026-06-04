import { describe, it, expect, vi, beforeAll, afterAll } from "vitest"
import { render, screen, fireEvent } from "@testing-library/react"
import { DiffView, parseDiff, buildSideBySideRows } from "./DiffView"
import { splitDiff } from "./ChatComponents"

// Mock ResizeObserver for jsdom (no layout measurements available)
class MockResizeObserver {
  observe = vi.fn()
  unobserve = vi.fn()
  disconnect = vi.fn()
}

beforeAll(() => {
  vi.stubGlobal("ResizeObserver", MockResizeObserver)
})

afterAll(() => {
  vi.unstubAllGlobals()
})

const sampleDiff = [
  "--- /path/to/file.txt",
  "+++ /path/to/file.txt",
  "@@ -1,3 +1,4 @@",
  " foo",
  "-bar",
  " baz",
  "+qux",
  "+extra",
].join("\n")

describe("parseDiff", () => {
  it("parses header lines", () => {
    const lines = parseDiff(sampleDiff)
    expect(lines[0]).toMatchObject({ kind: "header", text: "--- /path/to/file.txt" })
    expect(lines[1]).toMatchObject({ kind: "header", text: "+++ /path/to/file.txt" })
  })

  it("parses hunk header", () => {
    const lines = parseDiff(sampleDiff)
    const hunk = lines.find((l) => l.kind === "hunk")!
    expect(hunk).toBeDefined()
    expect(hunk.text).toContain("@@")
  })

  it("assigns correct line numbers", () => {
    const lines = parseDiff(sampleDiff)
    // lines[0] = --- header, lines[1] = +++ header, lines[2] = @@ hunk
    // foo (context) → old=1, new=1
    const foo = lines[3]!
    expect(foo.kind).toBe("context")
    expect(foo.oldLine).toBe(1)
    expect(foo.newLine).toBe(1)

    // -bar (deletion) → old=2, new=null
    const bar = lines[4]!
    expect(bar.kind).toBe("del")
    expect(bar.oldLine).toBe(2)
    expect(bar.newLine).toBeNull()

    // baz (context) → old=3, new=2
    const baz = lines[5]!
    expect(baz.kind).toBe("context")
    expect(baz.oldLine).toBe(3)
    expect(baz.newLine).toBe(2)

    // +qux (addition) → old=null, new=3
    const qux = lines[6]!
    expect(qux.kind).toBe("add")
    expect(qux.oldLine).toBeNull()
    expect(qux.newLine).toBe(3)

    // +extra (addition) → old=null, new=4
    const extra = lines[7]!
    expect(extra.kind).toBe("add")
    expect(extra.oldLine).toBeNull()
    expect(extra.newLine).toBe(4)
  })

  it("strips content prefix characters correctly", () => {
    const lines = parseDiff(sampleDiff)
    // context line with space prefix → content after stripping space
    const foo = lines.find((l) => l.kind === "context" && l.text.includes("foo"))!
    expect(foo).toBeDefined()

    // deletion line with - prefix
    const bar = lines.find((l) => l.text.includes("bar"))!
    expect(bar).toBeDefined()
    expect(bar.kind).toBe("del")

    // addition line with + prefix
    const qux = lines.find((l) => l.text.includes("qux"))!
    expect(qux).toBeDefined()
    expect(qux.kind).toBe("add")
  })

  it("returns empty array for empty input", () => {
    const lines = parseDiff("")
    expect(lines).toHaveLength(0)
  })

  it("handles single-file diff with no changes", () => {
    const lines = parseDiff("--- a/file\n+++ b/file")
    expect(lines).toHaveLength(2)
    expect(lines[0]!.kind).toBe("header")
    expect(lines[1]!.kind).toBe("header")
  })
})

describe("buildSideBySideRows", () => {
  it("pairs context lines on both sides", () => {
    const lines = parseDiff(sampleDiff)
    const rows = buildSideBySideRows(lines)
    const fooRow = rows.find((r) => r.left?.text.includes("foo"))
    expect(fooRow).toBeDefined()
    expect(fooRow!.left).toBeTruthy()
    expect(fooRow!.right).toBeTruthy()
    expect(fooRow!.left!.kind).toBe("context")
    expect(fooRow!.right!.kind).toBe("context")
  })

  it("puts deletions only on the left", () => {
    const lines = parseDiff(sampleDiff)
    const rows = buildSideBySideRows(lines)
    const barRow = rows.find((r) => r.left?.text.includes("bar"))
    expect(barRow).toBeDefined()
    expect(barRow!.left).toBeTruthy()
    expect(barRow!.left!.kind).toBe("del")
    expect(barRow!.right).toBeNull()
  })

  it("puts additions only on the right", () => {
    const lines = parseDiff(sampleDiff)
    const rows = buildSideBySideRows(lines)
    const quxRow = rows.find((r) => r.right?.text.includes("qux"))
    expect(quxRow).toBeDefined()
    expect(quxRow!.right).toBeTruthy()
    expect(quxRow!.right!.kind).toBe("add")
    expect(quxRow!.left).toBeNull()
  })

  it("maps header lines to left-only span rows", () => {
    const lines = parseDiff(sampleDiff)
    const rows = buildSideBySideRows(lines)
    const header = rows.find((r) => r.left?.kind === "header")
    expect(header).toBeDefined()
    expect(header!.left).toBeTruthy()
    expect(header!.right).toBeNull()
  })

  it("maps hunk headers to left-only span rows", () => {
    const lines = parseDiff(sampleDiff)
    const rows = buildSideBySideRows(lines)
    const hunk = rows.find((r) => r.left?.kind === "hunk")
    expect(hunk).toBeDefined()
    expect(hunk!.left).toBeTruthy()
    expect(hunk!.right).toBeNull()
  })

  it("preserves correct line numbers on both sides", () => {
    const lines = parseDiff(sampleDiff)
    const rows = buildSideBySideRows(lines)
    const fooRow = rows.find((r) => r.left?.text.includes("foo"))
    expect(fooRow!.left!.lineNum).toBe(1)
    expect(fooRow!.right!.lineNum).toBe(1)
  })

  it("returns empty array for empty input", () => {
    expect(buildSideBySideRows([])).toEqual([])
  })
})

describe("DiffView", () => {
  it("renders diff lines in unified view by default", () => {
    render(<DiffView diff={sampleDiff} />)
    expect(screen.getByText("foo")).toBeInTheDocument()
    expect(screen.getByText("bar")).toBeInTheDocument()
    expect(screen.getByText("baz")).toBeInTheDocument()
    expect(screen.getByText("qux")).toBeInTheDocument()
  })

  it("shows collapse button for large diffs", () => {
    const largeDiff = Array.from({ length: 250 }, (_, i) => `+line ${i}`).join("\n")
    const fullDiff = `--- a/file\n+++ b/file\n@@ -1 +1,250 @@\n${largeDiff}`
    render(<DiffView diff={fullDiff} />)
    expect(screen.getByText(/Show diff/)).toBeInTheDocument()
  })

  it("expands diff when clicking collapse button", () => {
    const largeDiff = Array.from({ length: 250 }, (_, i) => `+line ${i}`).join("\n")
    const fullDiff = `--- a/file\n+++ b/file\n@@ -1 +1,250 @@\n${largeDiff}`
    render(<DiffView diff={fullDiff} />)
    fireEvent.click(screen.getByText(/Show diff/))
    expect(screen.getByText("line 0")).toBeInTheDocument()
  })

  it("renders empty state for empty diff", () => {
    const { container } = render(<DiffView diff="" />)
    expect(container.innerHTML).toBe("")
  })

  it("does not collapse diffs under the maxLines threshold", () => {
    render(<DiffView diff={sampleDiff} maxLines={10} />)
    expect(screen.queryByText(/Show diff/)).not.toBeInTheDocument()
    expect(screen.getByText("foo")).toBeInTheDocument()
  })

  it("shows diff header text (file path) in unified view", () => {
    render(<DiffView diff={sampleDiff} />)
    // Header text appears twice (--- and +++ both show the path)
    const headers = screen.getAllByText("/path/to/file.txt")
    expect(headers.length).toBeGreaterThanOrEqual(1)
  })
})

describe("splitDiff", () => {
  it("splits result with unified diff", () => {
    const result = `Edited file (exact match): replaced 1 occurrence (+2 lines, -1 lines)

--- /path/to/file
+++ /path/to/file
@@ -1,3 +1,4 @@
 foo
 -bar
 baz
+qux`
    const { summary, diff } = splitDiff(result)
    expect(summary).toContain("replaced 1 occurrence (+2 lines, -1 lines)")
    expect(diff).toContain("--- /path/to/file")
    expect(diff).toContain("+qux")
  })

  it("returns null diff for plain result", () => {
    const { summary, diff } = splitDiff("File written: /path/file (42 chars)")
    expect(summary).toBe("File written: /path/file (42 chars)")
    expect(diff).toBeNull()
  })

  it("returns null diff for single --- match without +++", () => {
    const result = "Some text\n--- not a diff marker"
    const { diff } = splitDiff(result)
    expect(diff).toBeNull()
  })

  it("returns null diff for empty string", () => {
    const { summary, diff } = splitDiff("")
    expect(summary).toBe("")
    expect(diff).toBeNull()
  })
})
