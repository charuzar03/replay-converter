from __future__ import annotations

import json
import os
import re
from html import unescape
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import Request, urlopen

try:
    import requests
except ImportError:  # pragma: no cover - covered indirectly through fallback behavior
    requests = None


@dataclass
class ReplayInput:
    identifier: str
    content: str
    replay_url: str = ""
    metadata: Dict[str, object] | None = None


class ReplayFetcher:
    """Loads replay logs from Showdown URLs or local files."""

    URL_PATTERN = re.compile(r"https?://[^\s]+", re.IGNORECASE)

    def __init__(self, timeout: int = 20) -> None:
        self.timeout = timeout

    def load_url(self, url: str) -> ReplayInput:
        url = self._normalize_replay_url(url.strip())
        battle_id = self._battle_id_from_url(url)
        candidates = self._candidate_urls(url)
        last_error: Optional[Exception] = None

        for candidate in candidates:
            try:
                body, headers = self._http_get(candidate)
                content_type = headers.get("content-type", "")
                if candidate.endswith(".json") or content_type.startswith("application/json"):
                    payload = json.loads(body)
                    log = payload.get("log", "")
                    if not log:
                        raise ValueError(f"No 'log' field found in JSON replay payload from {candidate}")
                    metadata = {
                        "uploadtime": payload.get("uploadtime"),
                        "format": payload.get("format"),
                        "id": payload.get("id") or battle_id,
                    }
                    return ReplayInput(
                        identifier=str(metadata.get("id") or battle_id),
                        content=log,
                        replay_url=url,
                        metadata=metadata,
                    )
                if self._looks_like_html(body):
                    log = self._extract_protocol_log_from_html(body)
                    if log:
                        return ReplayInput(identifier=battle_id, content=log, replay_url=url, metadata={})
                    raise ValueError(f"HTML replay page from {candidate} did not contain embedded battle log data.")
                if not self._looks_like_protocol_log(body):
                    raise ValueError(
                        f"Response from {candidate} did not look like a Pokemon Showdown protocol log."
                    )
                return ReplayInput(identifier=battle_id, content=body, replay_url=url, metadata={})
            except Exception as exc:  # pragma: no cover - network paths are not hit in unit tests
                last_error = exc

        raise RuntimeError(f"Unable to fetch replay log from {url}: {last_error}")

    def load_file(self, path: str) -> ReplayInput:
        file_path = Path(path)
        content = file_path.read_text(encoding="utf-8")
        metadata: Dict[str, object] = {}

        if file_path.suffix.lower() == ".json":
            payload = json.loads(content)
            if isinstance(payload, dict) and "log" in payload:
                metadata = {
                    "uploadtime": payload.get("uploadtime"),
                    "format": payload.get("format"),
                    "id": payload.get("id") or file_path.stem,
                }
                content = str(payload["log"])
        elif self._looks_like_html(content):
            log = self._extract_protocol_log_from_html(content)
            if log:
                content = log

        return ReplayInput(
            identifier=str(metadata.get("id") or file_path.stem),
            content=content,
            replay_url="",
            metadata=metadata,
        )

    def load_folder(self, folder: str) -> List[ReplayInput]:
        supported = {".log", ".txt", ".json", ".html"}
        results: List[ReplayInput] = []
        for path in sorted(Path(folder).iterdir()):
            if path.is_file() and path.suffix.lower() in supported:
                results.append(self.load_file(str(path)))
        return results

    def load_input_file(self, path: str) -> List[ReplayInput]:
        return self.load_pasted_text(Path(path).read_text(encoding="utf-8"))

    def load_pasted_text(self, text: str) -> List[ReplayInput]:
        items: List[ReplayInput] = []
        for entry in self.parse_entries_from_text(text):
            if entry.startswith("http://") or entry.startswith("https://"):
                items.append(self.load_url(entry))
            else:
                items.append(self.load_file(entry))
        return items

    def load_many(
        self,
        urls: Iterable[str] | None = None,
        files: Iterable[str] | None = None,
        folders: Iterable[str] | None = None,
        input_files: Iterable[str] | None = None,
    ) -> List[ReplayInput]:
        results: List[ReplayInput] = []
        for url in urls or []:
            results.append(self.load_url(url))
        for file_path in files or []:
            results.append(self.load_file(file_path))
        for folder in folders or []:
            results.extend(self.load_folder(folder))
        for input_file in input_files or []:
            results.extend(self.load_input_file(input_file))
        return results

    @classmethod
    def parse_entries_from_text(cls, text: str) -> List[str]:
        entries: List[str] = []
        seen: set[str] = set()

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            urls = [cls._normalize_replay_url(match.group(0).rstrip(".,);]")) for match in cls.URL_PATTERN.finditer(line)]
            if urls:
                for url in urls:
                    if url not in seen:
                        entries.append(url)
                        seen.add(url)
                continue

            if Path(line).exists() and line not in seen:
                entries.append(line)
                seen.add(line)

        return entries

    @staticmethod
    def _battle_id_from_url(url: str) -> str:
        parsed = urlparse(url)
        stem = parsed.path.rstrip("/").split("/")[-1]
        if stem.endswith(".json") or stem.endswith(".log") or stem.endswith(".html"):
            stem = os.path.splitext(stem)[0]
        return stem or "unknown-battle"

    @staticmethod
    def _normalize_replay_url(url: str) -> str:
        parsed = urlparse(url)
        if parsed.netloc.lower().endswith("google.com") and parsed.path == "/url":
            query = parse_qs(parsed.query)
            for key in ("q", "url"):
                values = query.get(key)
                if values:
                    return ReplayFetcher._normalize_replay_url(unquote(values[0]).strip())
        if parsed.netloc.lower().endswith("pokemonshowdown.com"):
            cleaned_path = parsed.path.rstrip("/")
            return f"{parsed.scheme}://{parsed.netloc}{cleaned_path}"
        return url

    @classmethod
    def _candidate_urls(cls, url: str) -> List[str]:
        cleaned = url.rstrip("/")
        if cleaned.endswith(".html"):
            base = cleaned.rsplit(".", 1)[0]
            return [
                cleaned,
                f"{base}.json",
                f"{base}.log",
            ]
        if cleaned.endswith(".json") or cleaned.endswith(".log"):
            base = cleaned.rsplit(".", 1)[0]
        else:
            base = cleaned
        return [
            f"{base}.json",
            f"{base}.log",
            cleaned,
        ]

    def _http_get(self, url: str) -> tuple[str, Dict[str, str]]:
        if requests is not None:
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()
            return response.text, dict(response.headers)
        request = Request(url, headers={"User-Agent": "showdown-stats-parser/1.0"})
        with urlopen(request, timeout=self.timeout) as response:  # pragma: no cover - network not used in unit tests
            body = response.read().decode("utf-8")
            headers = {key.lower(): value for key, value in response.headers.items()}
            return body, headers

    @staticmethod
    def _looks_like_protocol_log(text: str) -> bool:
        for line in text.splitlines():
            if line.startswith("|"):
                return True
        return False

    @staticmethod
    def _looks_like_html(text: str) -> bool:
        snippet = text[:500].lower()
        return bool(re.search(r"<(html|!doctype|head|body)\b", snippet))

    @staticmethod
    def _extract_protocol_log_from_html(text: str) -> str:
        match = re.search(
            r"<script\b(?=[^>]*\bclass=[\"'][^\"']*\bbattle-log-data\b[^\"']*[\"'])[^>]*>(.*?)</script>",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        if not match:
            return ""
        log = unescape(match.group(1)).strip()
        return log if ReplayFetcher._looks_like_protocol_log(log) else ""
