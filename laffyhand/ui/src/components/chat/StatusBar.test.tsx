import { describe, it, expect, beforeEach } from "vitest"
import { render, screen } from "@testing-library/react"
import { StatusBar } from "./StatusBar"
import { useChatStore } from "@/stores/chat-store"

beforeEach(() => {
  useChatStore.setState({
    model: "",
    sessionUsage: null,
    isStreaming: false,
  })
})

describe("StatusBar", () => {
  it("returns null when no model and no usage", () => {
    const { container } = render(<StatusBar />)
    expect(container.innerHTML).toBe("")
  })

  // ── 模型显示 ──

  it("displays model name", () => {
    useChatStore.setState({ model: "gpt-4" })
    render(<StatusBar />)
    expect(screen.getByText("gpt-4")).toBeInTheDocument()
  })

  it("shows blue dot next to model name", () => {
    useChatStore.setState({ model: "claude-3" })
    render(<StatusBar />)

    const sections = screen.getByText("claude-3").closest("div")
    expect(sections).toBeInTheDocument()
  })

  // ── Token 用量 ──

  it("displays cumulative total when no turn usage yet", () => {
    useChatStore.setState({
      sessionUsage: {
        total_input: 5000,
        total_output: 1000,
        total_reasoning: 200,
        context_size: 128000,
      },
    })
    render(<StatusBar />)
    expect(screen.getByText("6k")).toBeInTheDocument() // total = 6000 → 6k
    expect(screen.getByText((c) => c.includes("128k"))).toBeInTheDocument()
  })

  it("displays per-turn input/output when turnUsage available", () => {
    useChatStore.setState({
      model: "test-model",
      sessionUsage: {
        total_input: 2500,
        total_output: 750,
        total_reasoning: 0,
        context_size: 32000,
      },
      turnUsage: {
        input: 2500,
        output: 750,
        reasoning: 0,
      },
    })
    render(<StatusBar />)
    expect(screen.getByText("2.5k")).toBeInTheDocument() // turn input
    expect(screen.getByText("750")).toBeInTheDocument() // turn output < 1000
  })

  it("shows turn total and cumulative/context when turnUsage available", () => {
    useChatStore.setState({
      sessionUsage: {
        total_input: 1500000,
        total_output: 2000000,
        total_reasoning: 0,
        context_size: 1000000,
      },
      turnUsage: {
        input: 1500000,
        output: 2000000,
        reasoning: 0,
      },
    })
    render(<StatusBar />)
    expect(screen.getByText("3500k")).toBeInTheDocument() // turn total
    expect(screen.getByText((c) => c.includes("1000k"))).toBeInTheDocument()
  })

  it("formats turn tokens as plain number when under 1000", () => {
    useChatStore.setState({
      sessionUsage: {
        total_input: 500,
        total_output: 300,
        total_reasoning: 0,
        context_size: 4096,
      },
      turnUsage: {
        input: 500,
        output: 300,
        reasoning: 0,
      },
    })
    render(<StatusBar />)
    expect(screen.getByText("500")).toBeInTheDocument() // turn input
    expect(screen.getByText("300")).toBeInTheDocument() // turn output
  })

  // ── 推理 Token ──

  it("shows reasoning tokens when > 0", () => {
    useChatStore.setState({
      sessionUsage: {
        total_input: 100,
        total_output: 50,
        total_reasoning: 30,
        context_size: 4096,
      },
      turnUsage: {
        input: 100,
        output: 50,
        reasoning: 30,
      },
    })
    render(<StatusBar />)
    expect(screen.getByText("30")).toBeInTheDocument()
    expect(screen.getByText("🧠")).toBeInTheDocument()
  })

  it("hides reasoning section when reasoning is 0", () => {
    useChatStore.setState({
      sessionUsage: {
        total_input: 100,
        total_output: 50,
        total_reasoning: 0,
        context_size: 4096,
      },
      turnUsage: {
        input: 100,
        output: 50,
        reasoning: 0,
      },
    })
    render(<StatusBar />)
    expect(screen.queryByText("🧠")).not.toBeInTheDocument()
  })

  // ── Streaming 指示器 ──

  it("shows streaming indicator when streaming", () => {
    useChatStore.setState({
      model: "test",
      sessionUsage: null,
      isStreaming: true,
    })
    render(<StatusBar />)
    expect(screen.getByText("Streaming")).toBeInTheDocument()
  })

  it("hides streaming indicator when not streaming", () => {
    useChatStore.setState({
      model: "test",
      isStreaming: false,
    })
    render(<StatusBar />)
    expect(screen.queryByText("Streaming")).not.toBeInTheDocument()
  })

  // ── 综合 ──

  it("renders all sections together with turnUsage", () => {
    useChatStore.setState({
      model: "deepseek-v4",
      sessionUsage: {
        total_input: 10000,
        total_output: 2000,
        total_reasoning: 500,
        context_size: 64000,
      },
      turnUsage: {
        input: 10000,
        output: 2000,
        reasoning: 500,
      },
      isStreaming: true,
    })
    render(<StatusBar />)

    expect(screen.getByText("deepseek-v4")).toBeInTheDocument()
    expect(screen.getByText("12k")).toBeInTheDocument() // turn total
    expect(screen.getByText((c) => c.includes("64k"))).toBeInTheDocument() // context
    expect(screen.getByText("10k")).toBeInTheDocument() // turn input
    expect(screen.getByText("2k")).toBeInTheDocument() // turn output
    expect(screen.getByText("500")).toBeInTheDocument() // reasoning
    expect(screen.getByText("Streaming")).toBeInTheDocument()
  })
})
