import { describe, it, expect } from "vitest"
import { render, screen } from "@testing-library/react"
import { MarkdownContent } from "./MarkdownContent"

describe("MarkdownContent", () => {
  it("renders plain text as paragraph", () => {
    render(<MarkdownContent content="hello world" />)
    expect(screen.getByText("hello world")).toBeInTheDocument()
  })

  it("renders bold markdown", () => {
    render(<MarkdownContent content="this is **bold** text" />)
    expect(screen.getByText("bold").tagName).toBe("STRONG")
  })

  it("renders inline code", () => {
    render(<MarkdownContent content="use `npx tsc` to check" />)
    expect(screen.getByText("npx tsc")).toBeInTheDocument()
  })

  it("renders code fence as <pre>", () => {
    const { container } = render(<MarkdownContent content={"```\nhello()\n```"} />)
    expect(container.querySelector("pre")).toBeTruthy()
  })

  it("renders list items", () => {
    render(<MarkdownContent content={"- item 1\n- item 2"} />)
    expect(screen.getByText("item 1")).toBeInTheDocument()
    expect(screen.getByText("item 2")).toBeInTheDocument()
  })

  it("renders headings", () => {
    render(<MarkdownContent content={"# Title\n\n## Subtitle"} />)
    expect(screen.getByText("Title").tagName).toBe("H1")
    expect(screen.getByText("Subtitle").tagName).toBe("H2")
  })

  it("sanitizes dangerous HTML", () => {
    render(<MarkdownContent content='<script>alert("xss")</script>hello' />)
    expect(screen.queryByText(/alert/i)).not.toBeInTheDocument()
    expect(screen.getByText("hello")).toBeInTheDocument()
  })

  it("renders links", () => {
    render(<MarkdownContent content="[click here](https://example.com)" />)
    const link = screen.getByText("click here")
    expect(link.tagName).toBe("A")
    expect(link).toHaveAttribute("href", "https://example.com")
  })
})
