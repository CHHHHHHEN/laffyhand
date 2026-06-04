@echo off
setlocal enabledelayedexpansion

set "PROJECT_DIR=%~dp0"

echo === Building UI ===
cd /d "%PROJECT_DIR%laffyhand\ui"
call pnpm build
if %errorlevel% neq 0 (
    echo UI build failed
    exit /b %errorlevel%
)

echo.
echo === Building laffyhand binary ===
cd /d "%PROJECT_DIR%"
uv run nuitka --onefile ^
    --noinclude-pytest-mode=nofollow ^
    --noinclude-setuptools-mode=nofollow ^
    --nofollow-import-to=mypy,pytest,ruff,vulture,types_pyyaml,nuitka ^
    --include-module=aiohttp,aiohttp.web,httpcore,h11,certifi ^
    --include-package=jwt,cryptography ^
    --include-data-dir=laffyhand\ui\dist=ui ^
    --output-dir=dist ^
    --output-filename=laffyhand ^
    laffyhand\__main__.py

if %errorlevel% equ 0 (
    echo.
    echo Build complete: dist\laffyhand.exe
) else (
    echo.
    echo Build failed
    exit /b %errorlevel%
)
