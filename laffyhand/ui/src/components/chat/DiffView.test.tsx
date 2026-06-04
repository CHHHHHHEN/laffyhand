import { describe, it, expect } from "vitest"
import { render, screen } from "@testing-library/react"
import { DiffView, parseDiff } from "./DiffView"
import { splitDiff } from "./ChatComponents"

const sampleDiff = `--- /path/to/file.txt
+++ /path/to/file.txt
@@ -1,3 +1,4 @@
 foo
-bar
 baz
+qux
+extra`

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

describe("DiffView", () => {
  it("renders diff lines", () => {
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

  it("renders empty state for empty diff", () => {
    const { container } = render(<DiffView diff="" />)
    expect(container.innerHTML).toBe("")
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
