# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

import logging
import asyncio
from pathlib import Path
from urllib.parse import urlparse

import httpx

from rag.config import ArxivSettings

logger = logging.getLogger(__name__)


class PDFDownloader:
    """
    `PDFDownloader` download PDF file from the given url through http/s
    """

    def __init__(
        self,
        settings: ArxivSettings,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.timeout_seconds = settings.download_timeout_seconds
        self.max_retries = settings.download_max_retries
        self.retry_backoff_seconds = settings.retry_backoff_seconds
        self.client = client

    async def download_pdf(self, pdf_url: str, output_path: Path) -> None:
        """
        Download arXiv PDF file and write into local output path

        example of a valid arXiv pdf_url: https://arxiv.org/pdf/1706.03762
        """
        self._validate_pdf_url(pdf_url)

        # make sure dir exist before write
        output_path.parent.mkdir(parents=True, exist_ok=True)

        last_error: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                logger.info("Downloading arXiv PDF: attempt=%s", attempt + 1)

                await self._download_to_path(pdf_url, output_path)
                self._validate_downloaded_pdf(output_path)
                return

            except Exception as error:
                last_error = error

                if output_path.exists():
                    output_path.unlink()

                logger.warning("PDF download failed: %s", error)

                if attempt < self.max_retries - 1:
                    await self._wait_before_retry(attempt)

        raise RuntimeError(
            f"Failed to download arXiv PDF paper: {last_error}"
        ) from last_error

    async def _wait_before_retry(self, attempt: int) -> None:
        time_before_retry = self.retry_backoff_seconds * (attempt + 1)
        await asyncio.sleep(time_before_retry)

    async def _download_to_path(self, pdf_url: str, output_path: Path) -> None:
        """
        Stream GET request, and write bytes to download into output path
        """
        if self.client is None:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                await self._stream_to_path(client, pdf_url, output_path)
            return

        await self._stream_to_path(self.client, pdf_url, output_path)

    async def _stream_to_path(
        self,
        client: httpx.AsyncClient,
        pdf_url: str,
        output_path: Path,
    ) -> None:
        async with client.stream(method="GET", url=pdf_url) as response:
            # check http status
            response.raise_for_status()

            # write to output path
            with output_path.open("wb") as file:
                async for chunk in response.aiter_bytes():
                    file.write(chunk)

    async def close(self) -> None:
        if self.client is not None:
            await self.client.aclose()

    def _validate_pdf_url(self, pdf_url: str) -> None:
        parsed = urlparse(pdf_url)

        if parsed.scheme not in {"http", "https"}:
            raise ValueError("PDF url must use http or https")

        if not parsed.netloc:
            raise ValueError("PDF url must include a host")

    def _validate_downloaded_pdf(self, output_path: Path) -> None:
        if not output_path.exists() or output_path.stat().st_size == 0:
            raise ValueError("Downloaded PDF is empty")

        with output_path.open("rb") as file:
            header = file.read(5)

        if header != b"%PDF-":
            raise ValueError("Downloaded file is not a valid PDF")
