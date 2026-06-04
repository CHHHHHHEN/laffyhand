import { describe, it, expect, vi } from "vitest"
import { render, screen, fireEvent } from "@testing-library/react"
import { Button } from "./Button"

describe("Button", () => {
  it("renders children", () => {
    render(<Button>Click me</Button>)
    expect(screen.getByRole("button", { name: /click me/i })).toBeInTheDocument()
  })

  it("calls onClick when clicked", () => {
    const onClick = vi.fn()
    render(<Button onClick={onClick}>Click</Button>)
    fireEvent.click(screen.getByRole("button"))
    expect(onClick).toHaveBeenCalledOnce()
  })

  it("is disabled when disabled prop is true", () => {
    render(<Button disabled>Click</Button>)
    expect(screen.getByRole("button")).toBeDisabled()
  })

  it("does not call onClick when disabled", () => {
    const onClick = vi.fn()
    render(<Button onClick={onClick} disabled>Click</Button>)
    fireEvent.click(screen.getByRole("button"))
    expect(onClick).not.toHaveBeenCalled()
  })

  it("applies variant styles", () => {
    const { container } = render(<Button variant="danger">Delete</Button>)
    expect(container.querySelector("button")!.className).toContain("bg-[var(--state-danger-fg)]")
  })

  it("applies size styles", () => {
    const { container } = render(<Button size="lg">Big</Button>)
    expect(container.querySelector("button")!.className).toContain("text-base")
  })
})
