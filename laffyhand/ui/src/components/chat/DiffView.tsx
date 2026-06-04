import { useMemo, useState, useRef, useEffect } from "react"

export interface DiffLine {
  kind: "header" | "hunk" | "add" | "del" | "context"
  text: string
  oldLine: number | null
  newLine: number | null
}

export function parseDiff(diff: string): DiffLine[] {
  const lines: DiffLine[] = []
  let oldLine = 0
  let newLine = 0

  const parts = diff.split(/\r?\n/)
  // Strip trailing empty line(s) from split
  while (parts.length > 0 && parts[parts.length - 1] === "") {
    parts.pop()
  }

  for (const raw of parts) {
    if (raw.startsWith("--- ") || raw.startsWith("+++ ")) {
      lines.push({ kind: "header", text: raw, oldLine: null, newLine: null })
      continue
    }
    if (raw.startsWith("@@")) {
      const m = raw.match(/@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/)
      if (m) {
        oldLine = Number(m[1])
        newLine = Number(m[2])
      }
      lines.push({ kind: "hunk", text: raw, oldLine: null, newLine: null })
      continue
    }
    if (raw.startsWith("+")) {
      lines.push({ kind: "add", text: raw, oldLine: null, newLine })
      newLine++
      continue
    }
    if (raw.startsWith("-")) {
      lines.push({ kind: "del", text: raw, oldLine, newLine: null })
      oldLine++
      continue
    }
    // context (space prefix) or any other line
    lines.push({ kind: "context", text: raw, oldLine, newLine })
    if (raw.startsWith(" ")) {
      oldLine++
      newLine++
    }
  }
  return lines
}

// ── Side-by-side row types ──

interface SideCell {
  kind: "context" | "del" | "add" | "hunk" | "header"
  text: string
  lineNum: number | null
}

export interface SideBySideRow {
  left: SideCell | null
  right: SideCell | null
}

/** Build side-by-side rows from parsed diff lines. */
export function buildSideBySideRows(lines: DiffLine[]): SideBySideRow[] {
  const rows: SideBySideRow[] = []
  for (const line of lines) {
    if (line.kind === "header" || line.kind === "hunk") {
      rows.push({
        left: { kind: line.kind, text: line.text, lineNum: null },
        right: null,
      })
    } else if (line.kind === "context") {
      rows.push({
        left: { kind: "context", text: line.text, lineNum: line.oldLine },
        right: { kind: "context", text: line.text, lineNum: line.newLine },
      })
    } else if (line.kind === "del") {
      rows.push({
        left: { kind: "del", text: line.text, lineNum: line.oldLine },
        right: null,
      })
    } else if (line.kind === "add") {
      rows.push({
        left: null,
        right: { kind: "add", text: line.text, lineNum: line.newLine },
      })
    }
  }
  return rows
}

// ── Shared helpers ──

function prefixFor(kind: SideCell["kind"]): string {
  switch (kind) {
    case "add": return "+"
    case "del": return "-"
    case "hunk": return "@@"
    default: return " "
  }
}

function textColorFor(kind: SideCell["kind"]): string {
  switch (kind) {
    case "add":
      return "text-[var(--diff-add-fg,#1a7f37)] dark:text-[var(--diff-add-fg-dark,#3fb950)]"
    case "del":
      return "text-[var(--diff-del-fg,#cf222e)] dark:text-[var(--diff-del-fg-dark,#f85149)]"
    case "hunk":
      return "text-[var(--text-faint)]"
    default:
      return "text-[var(--text-muted)]"
  }
}

function bgFor(kind: SideCell["kind"]): string {
  switch (kind) {
    case "add":
      return "bg-[var(--diff-add-bg,#e6ffec)] dark:bg-[var(--diff-add-bg-dark,#1a3d2e)]"
    case "del":
      return "bg-[var(--diff-del-bg,#ffebe9)] dark:bg-[var(--diff-del-bg-dark,#3d1a1a)]"
    case "hunk":
      return "bg-[var(--diff-hunk-bg,#f0f0f0)] dark:bg-[var(--diff-hunk-bg-dark,#1e1e1e)]"
    default:
      return ""
  }
}

function stripContent(text: string, kind: SideCell["kind"]): string {
  if (kind === "header") {
    return text.replace(/^--- |^\+\+\+ /, "")
  }
  if (kind === "context" && text.startsWith(" ")) {
    return text.slice(1)
  }
  // "+" or "-" prefix
  return text.slice(1)
}

const SIDEBYSIDE_THRESHOLD = 800

// ── DiffView component ──

interface DiffViewProps {
  diff: string
  maxLines?: number
}

export function DiffView({ diff, maxLines = 200 }: DiffViewProps) {
  const lines = useMemo(() => parseDiff(diff), [diff])
  const rows = useMemo(() => buildSideBySideRows(lines), [lines])
  const totalLines = lines.length
  const [collapsed, setCollapsed] = useState(totalLines > maxLines)
  const containerRef = useRef<HTMLDivElement>(null)
  const [useSideBySide, setUseSideBySide] = useState(false)

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const wide = entry.contentRect.width >= SIDEBYSIDE_THRESHOLD
        setUseSideBySide(wide)
      }
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  if (totalLines === 0) return null

  if (collapsed) {
    return (
      <div className="mt-1.5">
        <button
          onClick={() => setCollapsed(false)}
          className="flex items-center gap-1 text-[10px] text-[var(--accent)] hover:opacity-80 transition-opacity cursor-pointer font-sans"
        >
          <svg className="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
          Show diff ({totalLines} lines)
        </button>
      </div>
    )
  }

  return (
    <div className="mt-1.5 rounded border border-[var(--border-muted)] overflow-hidden" ref={containerRef}>
      {useSideBySide ? (
        <SideBySideTable rows={rows} />
      ) : (
        <UnifiedTable lines={lines} />
      )}
    </div>
  )
}

// ── Unified (single-column) view ──

function UnifiedTable({ lines }: { lines: DiffLine[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[11px] leading-[1.4] font-mono border-collapse">
        <tbody>
          {lines.map((line, i) => (
            <UnifiedRow key={i} line={line} />
          ))}
        </tbody>
      </table>
    </div>
  )
}

function UnifiedRow({ line }: { line: DiffLine }) {
  const bg = bgFor(line.kind)
  const prefix = prefixFor(line.kind)
  const textColor = textColorFor(line.kind)

  const oldStr = line.oldLine !== null ? String(line.oldLine) : ""
  const newStr = line.newLine !== null ? String(line.newLine) : ""

  return (
    <tr className={`${bg} align-top`}>
      <td className="w-[2ch] min-w-[2ch] text-right pr-2 pl-1 select-none text-[var(--text-faint)]">
        {oldStr}
      </td>
      <td className="w-[2ch] min-w-[2ch] text-right pr-2 select-none text-[var(--text-faint)]">
        {newStr}
      </td>
      <td className={`w-[1ch] min-w-[1ch] select-none ${textColor}`}>
        {prefix}
      </td>
      <td className={`whitespace-pre-wrap break-all ${textColor}`}>
        {stripContent(line.text, line.kind)}
      </td>
    </tr>
  )
}

// ── Side-by-side view ──

function SideBySideTable({ rows }: { rows: SideBySideRow[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[11px] leading-[1.4] font-mono border-collapse table-fixed">
        <colgroup>
          <col className="w-[2ch] min-w-[2ch]" />
          <col />
          <col className="w-px" />
          <col className="w-[2ch] min-w-[2ch]" />
          <col />
        </colgroup>
        <tbody>
          {rows.map((row, i) => (
            <SideBySideRow key={i} row={row} />
          ))}
        </tbody>
      </table>
    </div>
  )
}

function SideBySideRow({ row }: { row: SideBySideRow }) {
  // ── Span-row for headers/hunks ──
  if (row.left?.kind === "header" || row.left?.kind === "hunk") {
    return (
      <tr className={`${bgFor(row.left.kind)} align-top`}>
        <td colSpan={5} className="px-2 py-[1px] text-[var(--text-faint)] select-none">
          {stripContent(row.left.text, row.left.kind)}
        </td>
      </tr>
    )
  }

  const leftBg = row.left ? bgFor(row.left.kind) : ""
  const rightBg = row.right ? bgFor(row.right.kind) : ""

  return (
    <tr className="align-top">
      {/* Left side: line number */}
      <td className={`text-right pr-2 pl-1 select-none text-[var(--text-faint)] ${leftBg}`}>
        {row.left?.lineNum ?? ""}
      </td>
      {/* Left side: content */}
      <td className={`whitespace-pre-wrap break-all ${leftBg} ${row.left ? textColorFor(row.left.kind) : ""}`}>
        {row.left ? stripContent(row.left.text, row.left.kind) : ""}
      </td>
      {/* Divider */}
      <td className="bg-[var(--border-muted)] w-px p-0" />
      {/* Right side: line number */}
      <td className={`text-right pr-2 select-none text-[var(--text-faint)] ${rightBg}`}>
        {row.right?.lineNum ?? ""}
      </td>
      {/* Right side: content */}
      <td className={`whitespace-pre-wrap break-all ${rightBg} ${row.right ? textColorFor(row.right.kind) : ""}`}>
        {row.right ? stripContent(row.right.text, row.right.kind) : ""}
      </td>
    </tr>
  )
}
