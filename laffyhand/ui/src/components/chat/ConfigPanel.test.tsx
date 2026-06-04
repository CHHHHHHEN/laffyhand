import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen, fireEvent, waitFor } from "@testing-library/react"
import { ConfigPanel } from "./ConfigPanel"
import { useUiStore } from "@/stores/ui-store"
import { rpcClient } from "@/lib/rpc"

vi.mock("@/lib/rpc", () => ({
  rpcClient: {
    configProviders: vi.fn(),
    mcpStatus: vi.fn(),
    toolsList: vi.fn(),
    toolsSetDisabled: vi.fn(),
    sessionSetConfig: vi.fn(),
    mcpAddServer: vi.fn(),
    mcpRemoveServer: vi.fn(),
  },
}))

vi.mock("@/hooks/use-sessions", () => ({
  useAgents: () => ({
    agents: [
      { name: "build", description: "Main coding agent", mode: "primary", system_prompt: "", model: null },
      { name: "general", description: "General purpose", mode: "subagent", system_prompt: "", model: null },
    ],
    isLoading: false,
    error: null,
  }),
}))

beforeEach(() => {
  vi.clearAllMocks()
})

describe("ConfigPanel", () => {
  it("renders gear button when closed", () => {
    render(<ConfigPanel />)
    const button = document.querySelector("button")
    expect(button).toBeTruthy()
    expect(button?.getAttribute("title")).toBe("Config & Tools")
  })

  it("opens modal and loads data on click", async () => {
    vi.mocked(rpcClient.configProviders).mockResolvedValue({
      default_provider: "test",
      providers: {},
    })
    vi.mocked(rpcClient.mcpStatus).mockResolvedValue({ servers: [] })
    vi.mocked(rpcClient.toolsList).mockResolvedValue({ tools: [] })

    render(<ConfigPanel />)
    fireEvent.click(screen.getByTitle("Config & Tools"))

    expect(screen.getByText("Config & Tools")).toBeInTheDocument()
    expect(rpcClient.configProviders).toHaveBeenCalledTimes(1)
    expect(rpcClient.mcpStatus).toHaveBeenCalledTimes(1)
    expect(rpcClient.toolsList).toHaveBeenCalledTimes(1)
  })

  it("shows three tabs (Tools, MCP, Config)", async () => {
    vi.mocked(rpcClient.configProviders).mockResolvedValue({
      default_provider: "test",
      providers: {},
    })
    vi.mocked(rpcClient.mcpStatus).mockResolvedValue({ servers: [] })
    vi.mocked(rpcClient.toolsList).mockResolvedValue({ tools: [] })

    render(<ConfigPanel />)
    fireEvent.click(screen.getByTitle("Config & Tools"))

    expect(screen.getByText("Tools")).toBeInTheDocument()
    expect(screen.getByText("MCP")).toBeInTheDocument()
    expect(screen.getByText("Config")).toBeInTheDocument()
  })

  it("displays tools from API", async () => {
    vi.mocked(rpcClient.configProviders).mockResolvedValue({
      default_provider: "test",
      providers: {},
    })
    vi.mocked(rpcClient.mcpStatus).mockResolvedValue({ servers: [] })
    vi.mocked(rpcClient.toolsList).mockResolvedValue({
      tools: [
        { name: "read_file", description: "Read a file", input_schema: {}, enabled: true },
        { name: "write_file", description: "Write a file", input_schema: {}, enabled: true },
      ],
    })

    render(<ConfigPanel />)
    fireEvent.click(screen.getByTitle("Config & Tools"))

    await waitFor(() => {
      expect(screen.getByText("read_file")).toBeInTheDocument()
    })
    expect(screen.getByText("write_file")).toBeInTheDocument()
  })

  it("shows MCP server status", async () => {
    vi.mocked(rpcClient.configProviders).mockResolvedValue({
      default_provider: "test",
      providers: {},
    })
    vi.mocked(rpcClient.mcpStatus).mockResolvedValue({
      servers: [
        { name: "server-a", status: "connected" },
        { name: "server-b", status: "failed: Connection refused" },
      ],
    })
    vi.mocked(rpcClient.toolsList).mockResolvedValue({ tools: [] })

    render(<ConfigPanel />)
    fireEvent.click(screen.getByTitle("Config & Tools"))

    await waitFor(() => {
      expect(screen.getByText("MCP")).toBeInTheDocument()
    })
    fireEvent.click(screen.getByText("MCP"))

    await waitFor(() => {
      expect(screen.getByText("server-a")).toBeInTheDocument()
    })
    expect(screen.getByText("server-b")).toBeInTheDocument()
  })

  it("displays provider config with model buttons", async () => {
    vi.mocked(rpcClient.configProviders).mockResolvedValue({
      default_provider: "test",
      providers: {
        opencode: {
          type: "deepseek",
          base_url: "https://opencode.ai/zen/go",
          models: [
            { name: "deepseek-v4-flash", context_size: 128000 },
          ],
        },
      },
    })
    vi.mocked(rpcClient.mcpStatus).mockResolvedValue({ servers: [] })
    vi.mocked(rpcClient.toolsList).mockResolvedValue({ tools: [] })

    render(<ConfigPanel />)
    fireEvent.click(screen.getByTitle("Config & Tools"))
    fireEvent.click(screen.getByText("Config"))

    await waitFor(() => {
      expect(screen.getByText("opencode")).toBeInTheDocument()
    })
    expect(screen.getByText("deepseek-v4-flash")).toBeInTheDocument()
  })

  it("closes modal when clicking the overlay background", async () => {
    vi.mocked(rpcClient.configProviders).mockResolvedValue({
      default_provider: "test",
      providers: {},
    })
    vi.mocked(rpcClient.mcpStatus).mockResolvedValue({ servers: [] })
    vi.mocked(rpcClient.toolsList).mockResolvedValue({ tools: [] })

    render(<ConfigPanel />)
    fireEvent.click(screen.getByTitle("Config & Tools"))

    await waitFor(() => {
      expect(screen.getByText("Tools")).toBeInTheDocument()
    })

    const overlay = document.querySelector(".fixed.inset-0")
    expect(overlay).toBeTruthy()
    fireEvent.click(overlay!)

    expect(screen.getByTitle("Config & Tools")).toBeInTheDocument()
  })

  it("shows empty state when no tools", async () => {
    vi.mocked(rpcClient.configProviders).mockResolvedValue({
      default_provider: "test",
      providers: {},
    })
    vi.mocked(rpcClient.mcpStatus).mockResolvedValue({ servers: [] })
    vi.mocked(rpcClient.toolsList).mockResolvedValue({ tools: [] })

    render(<ConfigPanel />)
    fireEvent.click(screen.getByTitle("Config & Tools"))

    await waitFor(() => {
      expect(screen.getByText("No tools available")).toBeInTheDocument()
    })
  })

  it("shows default agent selector in Config tab", async () => {
    vi.mocked(rpcClient.configProviders).mockResolvedValue({
      default_provider: "test",
      providers: {},
    })
    vi.mocked(rpcClient.mcpStatus).mockResolvedValue({ servers: [] })
    vi.mocked(rpcClient.toolsList).mockResolvedValue({ tools: [] })

    render(<ConfigPanel />)
    fireEvent.click(screen.getByTitle("Config & Tools"))
    fireEvent.click(screen.getByText("Config"))

    await waitFor(() => {
      expect(screen.getByText("Default Agent")).toBeInTheDocument()
    })
    expect(screen.getByText("build")).toBeInTheDocument()
    expect(screen.getByText("general")).toBeInTheDocument()
  })

  it("changes default agent on click", async () => {
    vi.mocked(rpcClient.configProviders).mockResolvedValue({
      default_provider: "test",
      providers: {},
    })
    vi.mocked(rpcClient.mcpStatus).mockResolvedValue({ servers: [] })
    vi.mocked(rpcClient.toolsList).mockResolvedValue({ tools: [] })

    render(<ConfigPanel />)
    fireEvent.click(screen.getByTitle("Config & Tools"))
    fireEvent.click(screen.getByText("Config"))

    await waitFor(() => {
      expect(screen.getByText("Default Agent")).toBeInTheDocument()
    })

    // Default should be "build"
    expect(useUiStore.getState().defaultAgent).toBe("build")

    // Click "general"
    fireEvent.click(screen.getByText("general"))

    expect(useUiStore.getState().defaultAgent).toBe("general")
  })

  it("shows empty state when no MCP servers", async () => {
    vi.mocked(rpcClient.configProviders).mockResolvedValue({
      default_provider: "test",
      providers: {},
    })
    vi.mocked(rpcClient.mcpStatus).mockResolvedValue({ servers: [] })
    vi.mocked(rpcClient.toolsList).mockResolvedValue({ tools: [] })

    render(<ConfigPanel />)
    fireEvent.click(screen.getByTitle("Config & Tools"))

    await waitFor(() => {
      expect(screen.getByText("MCP")).toBeInTheDocument()
    })
    fireEvent.click(screen.getByText("MCP"))

    await waitFor(() => {
      expect(screen.getByText("No MCP servers configured")).toBeInTheDocument()
    })
  })
})