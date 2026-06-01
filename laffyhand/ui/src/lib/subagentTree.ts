import type { ActiveSubagent } from "@/types/session"

export interface SubagentAggregate {
  totalTools: number
  activeCount: number
  descendantCount: number
  totalDuration: number
  maxDepthFromHere: number
  inputTokens: number
  outputTokens: number
}

export interface SubagentTreeNode {
  item: ActiveSubagent
  children: SubagentTreeNode[]
  aggregate: SubagentAggregate
}

const ROOT_KEY = "__root__"

export function buildSubagentTree(items: ActiveSubagent[]): SubagentTreeNode[] {
  if (!items.length) return []

  const byParent = new Map<string, ActiveSubagent[]>()
  const known = new Set<string>()

  for (const item of items) {
    known.add(item.id)
  }

  for (const item of items) {
    const parentKey = item.parentId && known.has(item.parentId) ? item.parentId : ROOT_KEY
    const bucket = byParent.get(parentKey) ?? []
    bucket.push(item)
    byParent.set(parentKey, bucket)
  }

  for (const bucket of byParent.values()) {
    bucket.sort((a, b) => a.depth - b.depth || a.id.localeCompare(b.id))
  }

  function build(item: ActiveSubagent): SubagentTreeNode {
    const kids = byParent.get(item.id) ?? []
    const children = kids.map(build)
    return { aggregate: aggregate(item, children), children, item }
  }

  return (byParent.get(ROOT_KEY) ?? []).map(build)
}

export function aggregate(
  item: ActiveSubagent,
  children: readonly SubagentTreeNode[],
): SubagentAggregate {
  let totalTools = item.toolCount
  let descendantCount = 0
  let activeCount = item.status === "running" ? 1 : 0
  let maxDepthFromHere = 0
  let inputTokens = item.inputTokens
  let outputTokens = item.outputTokens

  for (const child of children) {
    totalTools += child.aggregate.totalTools
    descendantCount += child.aggregate.descendantCount + 1
    activeCount += child.aggregate.activeCount
    maxDepthFromHere = Math.max(maxDepthFromHere, child.aggregate.maxDepthFromHere + 1)
    inputTokens += child.aggregate.inputTokens
    outputTokens += child.aggregate.outputTokens
  }

  return {
    totalTools,
    activeCount,
    descendantCount,
    totalDuration: 0,
    maxDepthFromHere,
    inputTokens,
    outputTokens,
  }
}

export function flattenTree(tree: readonly SubagentTreeNode[]): SubagentTreeNode[] {
  const out: SubagentTreeNode[] = []
  function walk(nodes: readonly SubagentTreeNode[]) {
    for (const node of nodes) {
      out.push(node)
      walk(node.children)
    }
  }
  walk(tree)
  return out
}
