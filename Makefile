.PHONY: build distclean

build: dist/laffyhand

dist/laffyhand: laffyhand/__main__.py $(shell find laffyhand -name '*.py')
	uv run nuitka --onefile \
		--enable-plugin=upx \
		--noinclude-pytest-mode=nofollow \
		--noinclude-setuptools-mode=nofollow \
		--nofollow-import-to=mypy,pytest,ruff,vulture,types_pyyaml,nuitka \
		--include-module=aiohttp,aiohttp.web,httpcore,h11,certifi \
		--include-package=jwt,cryptography \
		--output-dir=dist \
		--output-filename=laffyhand \
		laffyhand/__main__.py

distclean:
	rm -rf dist/ __main__.build __main__.dist build/
