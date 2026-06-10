## Laffyhand -- A General Purpose AI Agent

<div align="center">

![Python](https://img.shields.io/badge/Python_3.14-3776AB?style=for-the-badge&logo=python&logoColor=white)
![React](https://img.shields.io/badge/React_19-61DAFB?style=for-the-badge&logo=react&logoColor=black)

</div>

Laffyhand is a general purpose AI agent. It can complete programming tasks, search the internet for information, make plans and follow them to achieve goals, parse documents and store them in a vector knowledge base, and have personal memory.

<div align="center">
  <img src="assets/screenshot.png" alt="Laffyhand UI Screenshot" width="800">
</div>

## Quick Start

### Prerequisites

- Python 3.14+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Node.js 22+
- [pnpm](https://pnpm.io/) (Node.js package manager)

### Setup

```bash
# Clone the repository
git clone <repo-url> && cd laffyhand

# Install Python dependencies
uv sync

# Install frontend dependencies and build UI
cd laffyhand/ui && pnpm install && pnpm build && cd ../..

# Create configuration from example
cp laffyhand.example.yml laffyhand.yml
# Edit laffyhand.yml and fill in your LLM provider api_key
```

### Development

```bash
# Start the web UI (backend + frontend)
uv run laffyhand ui

# Or use the dev script (kills existing process, rebuilds UI, starts server)
./dev.sh
```

The web UI is available at http://127.0.0.1:9090.

### Production Build

```bash
# Build a single-file executable with Nuitka (Linux/macOS)
make build

# Windows
build.bat

# The binary is at dist/laffyhand (dist/laffyhand.exe on Windows)
```

On first launch the binary auto-creates a default `laffyhand.yml` in the current directory. Edit it to add your LLM provider configuration before use.
