import { describe, it, expect, vi } from "vitest"
import { render, screen, fireEvent, act } from "@testing-library/react"
import { ErrorBoundary } from "./ErrorBoundary"

const ThrowError = ({ message }: { message: string }) => {
  throw new Error(message)
}

beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => {})
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe("ErrorBoundary", () => {
  it("renders children when no error", () => {
    render(
      <ErrorBoundary>
        <p>normal content</p>
      </ErrorBoundary>,
    )
    expect(screen.getByText("normal content")).toBeInTheDocument()
  })

  it("catches error and shows default fallback", () => {
    render(
      <ErrorBoundary>
        <ThrowError message="test error" />
      </ErrorBoundary>,
    )
    expect(screen.getByText("Something went wrong")).toBeInTheDocument()
    expect(screen.getByText("test error")).toBeInTheDocument()
    expect(screen.getByText("Retry")).toBeInTheDocument()
  })

  it("shows custom fallback when provided", () => {
    render(
      <ErrorBoundary fallback={<p>Custom error UI</p>}>
        <ThrowError message="test" />
      </ErrorBoundary>,
    )
    expect(screen.getByText("Custom error UI")).toBeInTheDocument()
    expect(screen.queryByText("Retry")).not.toBeInTheDocument()
  })

  it("resets error state on retry click", async () => {
    const { rerender } = render(
      <ErrorBoundary>
        <ThrowError message="test error" />
      </ErrorBoundary>,
    )
    expect(screen.getByText("Something went wrong")).toBeInTheDocument()

    // Click retry AND swap to safe children in the same act batch
    // to avoid the throwing child re-triggering the error before the new children render
    await act(async () => {
      fireEvent.click(screen.getByText("Retry"))
      rerender(
        <ErrorBoundary>
          <p>recovered</p>
        </ErrorBoundary>,
      )
    })

    expect(screen.getByText("recovered")).toBeInTheDocument()
    expect(screen.queryByText("Something went wrong")).not.toBeInTheDocument()
  })
})
