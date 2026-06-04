import { useMemo, useState } from "react"

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

interface DiffViewProps {
  diff: string
  maxLines?: number
}

export function DiffView({ diff, maxLines = 200 }: DiffViewProps) {
  const lines = useMemo(() => parseDiff(diff), [diff])
  const totalLines = lines.length
  const [collapsed, setCollapsed] = useState(totalLines > maxLines)

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
    <div className="mt-1.5 rounded border border-[var(--border-muted)] overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-[11px] leading-[1.4] font-mono border-collapse">
          <tbody>
            {lines.map((line, i) => (
              <DiffRow key={i} line={line} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function DiffRow({ line }: { line: DiffLine }) {
  const bg = line.kind === "add"
    ? "bg-[var(--diff-add-bg,#e6ffec)] dark:bg-[var(--diff-add-bg-dark,#1a3d2e)]"
    : line.kind === "del"
      ? "bg-[var(--diff-del-bg,#ffebe9)] dark:bg-[var(--diff-del-bg-dark,#3d1a1a)]"
      : line.kind === "hunk"
        ? "bg-[var(--diff-hunk-bg,#f0f0f0)] dark:bg-[var(--diff-hunk-bg-dark,#1e1e1e)]"
        : ""

  const prefix = line.kind === "add"
    ? "+"
    : line.kind === "del"
      ? "-"
      : line.kind === "hunk"
        ? "@@"
        : " "

  const textColor = line.kind === "add"
    ? "text-[var(--diff-add-fg,#1a7f37)] dark:text-[var(--diff-add-fg-dark,#3fb950)]"
    : line.kind === "del"
      ? "text-[var(--diff-del-fg,#cf222e)] dark:text-[var(--diff-del-fg-dark,#f85149)]"
      : line.kind === "hunk"
        ? "text-[var(--text-faint)]"
        : "text-[var(--text-muted)]"

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
        {line.kind === "header"
          ? line.text.replace(/^--- |^\+\+\+ /, "")
          : line.kind === "context" && line.text.startsWith(" ")
            ? line.text.slice(1)
            : line.text.slice(1)}
      </td>
    </tr>
  )
}

