# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

from dataclasses import dataclass, field

TITLE_OPEN = "<conversation_title>"
TITLE_CLOSE = "</conversation_title>"


@dataclass(slots=True)
class ConversationTitleStreamParser:
    enabled: bool
    max_prefix_length: int = 512
    _buffer: str = field(default="", init=False)
    _resolved: bool = field(default=False, init=False)

    def parse_response(self, chunk: str) -> tuple[str | None, str]:
        if not self.enabled or self._resolved:
            return None, chunk

        self._buffer += chunk
        closing_index = self._buffer.find(TITLE_CLOSE)

        if closing_index >= 0:
            opening_index = self._buffer.find(TITLE_OPEN)
            if 0 <= opening_index < closing_index:
                raw_title = self._buffer[
                    opening_index + len(TITLE_OPEN) : closing_index
                ]
                answer = self._buffer[closing_index + len(TITLE_CLOSE) :]
                self._buffer = ""
                self._resolved = True
                return self._clean_title(raw_title), answer.lstrip("\r\n")

        if len(self._buffer) >= self.max_prefix_length:
            answer = self._buffer
            self._buffer = ""
            self._resolved = True
            return None, answer

        return None, ""

    def finish(self) -> str:
        if not self.enabled or self._resolved:
            return ""

        answer = self._buffer
        self._buffer = ""
        self._resolved = True
        return answer

    def _clean_title(self, value: str, limit: int = 72) -> str | None:
        cleaned = " ".join(value.split()).strip(" \"'`#*_:-.,;!")
        if not cleaned:
            return None

        if len(cleaned) <= limit:
            return cleaned

        return f"{cleaned[: limit - 3].rstrip()}..."
