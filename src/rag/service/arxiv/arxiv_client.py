# Copyright 2026 Muhammad Nizwa
# SPDX-License-Identifier: MIT

import asyncio
import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
from dateutil import parser as date_parser

from rag.config import ArxivSettings
from rag.schema import ArxivQueryParams, ArxivPaperMetadata
from rag.service.arxiv.arxiv_exceptions import (
    ArxivMalformedEntryError,
    ArxivMetadataFetchError,
    ArxivMetadataParseError,
)

logger = logging.getLogger(__name__)

_VERSION_SUFFIX_RE = re.compile(r"v(\d+)$")


class ArxivClient:
    """
    ArxivClient is an api client to fetch arxiv paper metadata
    through `fetch_papers()` method.
    """

    xml_namespaces: dict = {
        # current xml parsing mostly uses atom namespace, except for doi.
        "atom": "http://www.w3.org/2005/Atom",
        "arxiv": "http://arxiv.org/schemas/atom",
        # TODO: opensearch currently NOT USED, can be removed in the future.
        "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
    }

    def __init__(
        self,
        settings: ArxivSettings,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = settings.base_url
        self.rate_limit_seconds = settings.rate_limit_seconds
        self.max_retries = settings.fetch_max_retries
        self.timeout_seconds = settings.fetch_timeout_seconds
        self.retry_backoff_seconds = settings.retry_backoff_seconds
        self.last_request_at: float | None = None
        self.client = client

    async def fetch_papers(
        self, query: ArxivQueryParams, ignore_version: bool = True
    ) -> list[ArxivPaperMetadata]:
        """
        fetch arxiv papers metadata using `ArxivQueryParams`

        Args:
            query:
                arxiv query parameter schema that includes validation
            ignore_version:
                flag when version in arxiv paper id matters, best to ignore most of the time

        Returns:
            list of arxiv paper metadata schema

        Raises:
            ArxivMetadataFetchError: 
                if arxiv api request fails after retries
            ArxivMetadataParseError: 
                if arxiv xml response cannot be parsed
        """
        api_query_url = self._build_url(query, ignore_version)
        xml_text = await self._fetch_metadata(api_query_url)
        return self._parse_response(xml_text)

    def _build_search_query(self, query: ArxivQueryParams) -> str:
        """
        arXiv api client search query parameter builder

        initial field constraint validation is done at the class `ArxivQueryParams` itself

        build based on the official docs: https://info.arxiv.org/help/api/user-manual.html
        """
        clauses: list[str] = []

        def format_value(value: str) -> str:
            value = value.strip()

            if " " in value:
                return f'"{value}"'

            return value

        def build_or_group(field: str, values: list[str] | None) -> str | None:
            if not values:
                return None

            parts = [f"{field}:{format_value(val)}" for val in values]

            if len(parts) == 1:
                return parts[0]

            return "(" + " OR ".join(parts) + ")"

        def format_arxiv_datetime(value: datetime) -> str:
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)

            value = value.astimezone(timezone.utc)
            return value.strftime("%Y%m%d%H%M")

        for field, values in [
            ("all", query.all_terms),
            ("ti", query.title_terms),
            ("abs", query.abstract_terms),
            ("au", query.authors),
            ("cat", query.categories),
        ]:
            group = build_or_group(field, values)
            if group:
                clauses.append(group)

        if query.submitted_from or query.submitted_to:
            submitted_from = query.submitted_from or datetime(
                1970, 1, 1, tzinfo=timezone.utc
            )
            submitted_to = query.submitted_to or datetime.now(timezone.utc)

            query_date = (
                f"submittedDate:[{format_arxiv_datetime(submitted_from)} "
                f"TO {format_arxiv_datetime(submitted_to)}]"
            )
            clauses.append(query_date)

        search_query = " AND ".join(clauses) if clauses else "all:*"

        exclude_categories = build_or_group("cat", query.exclude_categories)
        if exclude_categories:
            return f"{search_query} ANDNOT {exclude_categories}"

        return search_query

    def _build_url(self, query: ArxivQueryParams, ignore_version: bool = True) -> str:
        """
        build arXiv api url from `ArxivQueryParams`

        by defaut ignore_version is enabled.
        when fetching by paper ids: `2401.12345` if ignore_version is enabled, otherwise `2401.12345v3`
        """
        has_search_query = any(
            [
                query.all_terms,
                query.title_terms,
                query.abstract_terms,
                query.authors,
                query.categories,
                query.exclude_categories,
                query.submitted_from,
                query.submitted_to,
            ]
        )

        params = {
            "start": query.start,
            "max_results": query.max_results,
        }

        if has_search_query:
            params.update(
                {
                    "search_query": self._build_search_query(query),
                    "sortBy": query.sort_by,
                    "sortOrder": query.sort_order,
                }
            )

        if query.ids:
            ids = [
                self.strip_version_suffix(arxiv_id) if ignore_version else arxiv_id
                for arxiv_id in query.ids
            ]
            params["id_list"] = ",".join(ids)

        return f"{self.base_url}?{urlencode(params)}"

    async def _wait_between_request(self) -> None:
        """
        any simultaneous next request is delayed by this method
        """
        if self.last_request_at is None:
            return

        elapsed = time.monotonic() - self.last_request_at
        wait_time = self.rate_limit_seconds - elapsed

        if wait_time > 0:
            await asyncio.sleep(wait_time)

    async def _fetch_metadata(self, url: str) -> str:
        last_error: Exception | None = None
        attempts = max(1, self.max_retries)

        for attempt in range(attempts):
            await self._wait_between_request()

            self.last_request_at = time.monotonic()

            try:
                logger.info("Fetching arXiv metadata: attempt=%s", attempt + 1)
                return await self._get_xml_text(url)

            except httpx.TimeoutException as error:
                last_error = error
                logger.warning("arXiv request timed out: %s", error)
                await self._wait_before_retry(attempt)

            except httpx.HTTPStatusError as error:
                last_error = error
                logger.warning("arXiv returned HTTP status error: status=%s", error)
                await self._wait_before_retry(attempt)

            except httpx.HTTPError as error:
                last_error = error
                logger.warning("arXiv request failed: %s", error)
                await self._wait_before_retry(attempt)

        raise ArxivMetadataFetchError(
            f"Failed to fetch arXiv papers: {last_error}"
        ) from last_error

    async def _get_xml_text(self, url: str) -> str:
        if self.client is None:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                return await self._request_xml_text(client, url)

        return await self._request_xml_text(self.client, url)

    async def _request_xml_text(self, client: httpx.AsyncClient, url: str) -> str:
        response = await client.get(url)

        # raise http status to catch error
        response.raise_for_status()

        # return format is expected in plain XML text
        return response.text

    async def close(self) -> None:
        if self.client is not None:
            await self.client.aclose()

    async def _wait_before_retry(self, attempt: int) -> None:
        """
        set a delayed time when api request failed before retrying
        """
        if attempt >= self.max_retries - 1:
            return

        time_before_retry = self.retry_backoff_seconds * (attempt + 1)
        await asyncio.sleep(time_before_retry)

    def _parse_response(self, xml_text: str) -> list[ArxivPaperMetadata]:
        """
        parse plain XML text into list of `ArxivPaperMetadata`
        """
        try:
            root = ET.fromstring(xml_text)

        except ET.ParseError as error:
            logger.exception("Failed to parse arXiv XML response: %s", error)
            raise ArxivMetadataParseError("Invalid arXiv XML response") from error

        entries = root.findall("atom:entry", self.xml_namespaces)

        # return empty list if no paper found
        if not entries:
            logger.info("arXiv response contained no paper entries")
            return []

        papers: list[ArxivPaperMetadata] = []

        malformed_entries = 0

        for entry in entries:
            try:
                papers.append(self._parse_metadata(entry))

            except ArxivMalformedEntryError as error:
                malformed_entries += 1
                logger.warning("Skipping malformed arXiv entry: %s", error)

        if malformed_entries == len(entries):
            raise ArxivMetadataParseError("All arXiv entries were malformed")

        return papers

    def _parse_metadata(self, entry: ET.Element) -> ArxivPaperMetadata:
        arxiv_id = self._required_text(entry, "atom:id").rsplit("/", maxsplit=1)[-1]
        title = self._normalized_text(entry, "atom:title")
        abstract = self._normalized_text(entry, "atom:summary")
        doi = self._normalized_text(entry, "arxiv:doi")
        published = self._required_datetime(entry, "atom:published")

        return ArxivPaperMetadata(
            arxiv_id=self.strip_version_suffix(arxiv_id),
            version=self.extract_version(arxiv_id),
            title=title,
            authors=self._authors(entry),
            abstract=abstract,
            categories=self._categories(entry),
            published_date=published,
            pdf_url=self._pdf_url(entry),
            # NOTE: we should keep track of the result for the doi field
            doi=None if doi == "" else doi,
        )

    def _text(self, element: ET.Element, path: str) -> str | None:
        found = element.find(path, self.xml_namespaces)
        if found is None or found.text is None:
            return None

        return found.text.strip()

    def _required_text(self, element: ET.Element, path: str) -> str:
        value = self._text(element, path)
        if not value:
            raise ArxivMalformedEntryError(
                f"arXiv entry is missing required field: {path}"
            )

        return value

    def _normalized_text(self, element: ET.Element, path: str) -> str:
        value = self._text(element, path) or ""
        return " ".join(value.split())

    def _required_datetime(self, element: ET.Element, path: str) -> datetime:
        value = self._required_text(element, path)
        try:
            return date_parser.parse(value)
        
        except (TypeError, ValueError, OverflowError) as error:
            raise ArxivMalformedEntryError(
                f"arXiv entry has invalid datetime field: {path}"
            ) from error

    def _authors(self, entry: ET.Element) -> list[str]:
        return [
            name
            for author in entry.findall("atom:author", self.xml_namespaces)
            if (name := self._normalized_text(author, "atom:name"))
        ]

    def _categories(self, entry: ET.Element) -> list[str]:
        return [
            term.strip()
            for category in entry.findall("atom:category", self.xml_namespaces)
            if (term := category.attrib.get("term"))
        ]

    def _pdf_url(self, entry: ET.Element) -> str | None:
        for link in entry.findall("atom:link", self.xml_namespaces):
            if link.attrib.get("type") != "application/pdf":
                continue

            href = link.attrib.get("href")
            if not href:
                return None

            return self._normalize_arxiv_url(href)

        return None

    @staticmethod
    def strip_version_suffix(arxiv_id: str) -> str:
        return _VERSION_SUFFIX_RE.sub("", arxiv_id)

    @staticmethod
    def extract_version(arxiv_id: str) -> int | None:
        match = _VERSION_SUFFIX_RE.search(arxiv_id)
        if match is None:
            return None

        return int(match.group(1))

    @staticmethod
    def _normalize_arxiv_url(url: str) -> str:
        if url.startswith("http://arxiv.org/"):
            return url.replace("http://arxiv.org/", "https://arxiv.org/", 1)

        return url
