from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class PixabayImageResult:
    source_id: str
    preview_url: str
    full_image_url: str
    source_page_url: str
    width: int | None
    height: int | None


class PixabayImageSearchClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        helper_terms: tuple[str, ...] = (),
        timeout: int = 30,
    ) -> None:
        self._api_key = (api_key or os.getenv("PIXABAY_API_KEY", "")).strip()
        self._base_url = (base_url or os.getenv("PIXABAY_BASE_URL", "https://pixabay.com/api/")).rstrip("/")
        self._helper_terms = helper_terms
        self._timeout = timeout

    def build_query(self, *, english_word: str) -> str:
        normalized_word = " ".join(english_word.split()).strip()
        parts = [normalized_word, *self._helper_terms]
        return " ".join(part for part in parts if part).strip()

    def search(
        self,
        *,
        english_word: str,
        query: str | None = None,
        page: int = 1,
        per_page: int = 5,
    ) -> tuple[str, list[PixabayImageResult]]:
        if not self._api_key:
            raise ValueError("PIXABAY_API_KEY is not configured.")
        normalized_query = " ".join((query or self.build_query(english_word=english_word)).split()).strip()
        if not normalized_query:
            raise ValueError("Pixabay search query is required.")
        logger.debug(
            "Pixabay search start english_word=%r query=%r page=%s per_page=%s helper_terms=%s",
            english_word,
            normalized_query,
            page,
            per_page,
            self._helper_terms,
        )
        results = self._search_once(
            query=normalized_query,
            page=page,
            per_page=per_page,
            image_type="illustration",
        )
        if results:
            logger.debug(
                "Pixabay search done query=%r page=%s result_count=%s source=illustration",
                normalized_query,
                page,
                len(results),
            )
            return normalized_query, results
        logger.debug(
            "Pixabay illustration search returned no results query=%r page=%s; falling back to image_type=all",
            normalized_query,
            page,
        )
        return normalized_query, self._search_once(
            query=normalized_query,
            page=page,
            per_page=per_page,
            image_type="all",
        )

    def _search_once(
        self,
        *,
        query: str,
        page: int,
        per_page: int,
        image_type: str,
    ) -> list[PixabayImageResult]:
        try:
            import requests
        except ImportError as error:
            raise RuntimeError("requests is required for Pixabay image search.") from error
        request_params = {
            "q": query,
            "page": page,
            "per_page": per_page,
            "image_type": image_type,
            "safesearch": "true",
            "order": "popular",
        }
        logger.debug(
            "Pixabay request url=%s params=%s auth=api_key_present",
            self._base_url,
            request_params,
        )
        response = requests.get(
            self._base_url,
            params={
                "key": self._api_key,
                **request_params,
            },
            timeout=self._timeout,
        )
        response.raise_for_status()
        payload = response.json()
        hits = payload.get("hits", [])
        total = payload.get("total")
        total_hits = payload.get("totalHits")
        results: list[PixabayImageResult] = []
        if not isinstance(hits, list):
            logger.debug(
                "Pixabay response query=%r page=%s image_type=%s total=%r total_hits=%r hit_count=0 invalid_hits=true",
                query,
                page,
                image_type,
                total,
                total_hits,
            )
            return results
        for hit in hits:
            if not isinstance(hit, dict):
                continue
            source_id = str(hit.get("id", "")).strip()
            preview_url = str(hit.get("webformatURL") or hit.get("previewURL") or "").strip()
            full_image_url = str(hit.get("largeImageURL") or hit.get("webformatURL") or "").strip()
            source_page_url = str(hit.get("pageURL", "")).strip()
            if not source_id or not preview_url or not full_image_url or not source_page_url:
                continue
            width = hit.get("imageWidth")
            height = hit.get("imageHeight")
            results.append(
                PixabayImageResult(
                    source_id=source_id,
                    preview_url=preview_url,
                    full_image_url=full_image_url,
                    source_page_url=source_page_url,
                    width=int(width) if isinstance(width, int) else None,
                    height=int(height) if isinstance(height, int) else None,
                )
            )
        logger.debug(
            "Pixabay response query=%r page=%s image_type=%s total=%r total_hits=%r hit_count=%s candidates=%s",
            query,
            page,
            image_type,
            total,
            total_hits,
            len(hits),
            [
                {
                    "id": result.source_id,
                    "preview_url": result.preview_url,
                    "source_page_url": result.source_page_url,
                    "size": (
                        f"{result.width}x{result.height}"
                        if result.width is not None and result.height is not None
                        else None
                    ),
                }
                for result in results[:5]
            ],
        )
        return results


class RemoteImageDownloader:
    def __init__(self, *, timeout: int = 60) -> None:
        self._timeout = timeout

    def download(self, *, url: str, output_path: Path) -> None:
        try:
            import requests
        except ImportError as error:
            raise RuntimeError("requests is required for remote image download.") from error
        logger.debug(
            "Remote image download start url=%s output_path=%s",
            url,
            output_path,
        )
        response = requests.get(url, timeout=self._timeout)
        response.raise_for_status()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(response.content)
        logger.debug(
            "Remote image download done url=%s output_path=%s bytes=%s",
            url,
            output_path,
            len(response.content),
        )


def pixabay_preview_path(
    *,
    assets_dir: Path,
    topic_id: str,
    item_id: str,
    source_id: str,
    preview_url: str,
) -> Path:
    suffix = Path(urlparse(preview_url).path).suffix or ".jpg"
    return assets_dir / topic_id / "review" / f"{item_id}--pixabay-{source_id}{suffix}"
