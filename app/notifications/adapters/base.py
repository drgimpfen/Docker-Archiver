from dataclasses import dataclass
from typing import Optional


@dataclass
class AdapterResult:
    channel: str
    success: bool
    detail: Optional[str] = None


class AdapterBase:
    def send(self, title: str, body: str, body_format: object = None, attach: Optional[str] = None, context: str = '') -> AdapterResult:
        raise NotImplementedError()
