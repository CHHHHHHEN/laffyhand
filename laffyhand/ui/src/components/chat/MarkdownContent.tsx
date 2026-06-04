import { memo, useMemo, useRef, useEffect } from "react"
import { marked } from "marked"
import DOMPurify from "dompurify"

export const MarkdownContent = memo(function MarkdownContent({
  content,
  className = "",
}: {
  content: string
  className?: string
}) {
  const html = useMemo(() => {
    try {
      const raw = marked.parse(content, { async: false }) as string
      return DOMPurify.sanitize(raw)
    } catch (err) {
      console.warn("[MarkdownContent] Markdown parse failed:", err)
      return DOMPurify.sanitize(content)
    }
  }, [content])

  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!containerRef.current) return
    containerRef.current.querySelectorAll("pre").forEach((pre) => {
      if (pre.parentElement?.classList.contains("code-block-wrapper")) return
      const wrapper = document.createElement("div")
      wrapper.className = "code-block-wrapper relative group"
      pre.parentNode?.insertBefore(wrapper, pre)
      wrapper.appendChild(pre)

      const copyBtn = document.createElement("button")
      copyBtn.className = "copy-code-btn"
      copyBtn.textContent = "Copy"
      copyBtn.onclick = async () => {
        const code = pre.querySelector("code") || pre
        try {
          await navigator.clipboard.writeText(code.textContent || "")
          copyBtn.textContent = "Copied!"
          copyBtn.classList.add("!opacity-100")
          setTimeout(() => {
            copyBtn.textContent = "Copy"
            copyBtn.classList.remove("!opacity-100")
          }, 2000)
        } catch {
          copyBtn.textContent = "Failed"
        }
      }
      wrapper.appendChild(copyBtn)

      const lineCount = (pre.textContent || "").split("\n").length
      if (lineCount > 15) {
        pre.style.maxHeight = "200px"
        pre.style.overflow = "hidden"
        pre.style.transition = "max-height 0.25s ease"

        const expandBtn = document.createElement("button")
        expandBtn.className = "code-expand-btn"
        expandBtn.textContent = `Show more (${lineCount} lines)`

        let expanded = false
        expandBtn.onclick = () => {
          expanded = !expanded
          pre.style.maxHeight = expanded ? `${pre.scrollHeight}px` : "200px"
          expandBtn.textContent = expanded ? "Show less" : `Show more (${lineCount} lines)`
        }

        wrapper.appendChild(expandBtn)
      }
    })
  }, [html])

  return (
    <div
      ref={containerRef}
      className={"prose prose-base dark:prose-invert max-w-none break-words" + (className ? ` ${className}` : "")}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  )
})
