import json
import traceback
from http.client import HTTPResponse
from typing import Generator
from loguru import logger as _logger


def parse_sse(response: HTTPResponse) -> Generator[dict, None, None]:
    for line in response:
        decoded = line.decode('utf-8').rstrip('\n')
        if not decoded:
            continue
        if decoded == 'data: [DONE]':
            return
        if decoded.startswith('data: '):
            try:
                yield json.loads(decoded[6:])
            except Exception as e:
                _logger.warning(f"Line: {decoded}\nUnexpected error: {e}\n{traceback.format_exc()}")
                return
