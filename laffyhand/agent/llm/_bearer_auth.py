from laffyhand.agent.llm.specs import Auth


class BearerAuth(Auth):
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def apply(self, headers: dict[str, str]) -> None:
        headers["Authorization"] = f"Bearer {self.api_key}"
