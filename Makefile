.PHONY: build ui distclean

build: ui dist/laffyhand

ui:
	cd laffyhand/ui && pnpm build

dist/laffyhand: laffyhand/__main__.py $(shell find laffyhand -name '*.py') $(shell find laffyhand/ui/dist -type f 2>/dev/null)
	uv run nuitka --onefile \
		--noinclude-pytest-mode=nofollow \
		--noinclude-setuptools-mode=nofollow \
		--nofollow-import-to=mypy,pytest,ruff,vulture,types_pyyaml,nuitka \
		--include-module=aiohttp,aiohttp.web,httpcore,h11,certifi \
		--include-package=jwt,cryptography \
		--include-data-dir=laffyhand/ui/dist=ui \
		--output-dir=dist \
		--output-filename=laffyhand \
		laffyhand/__main__.py

distclean:
	rm -rf dist/ __main__.build __main__.dist build/
