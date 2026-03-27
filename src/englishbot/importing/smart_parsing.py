from __future__ import annotations

import logging
from typing import Protocol

from englishbot.importing.clients import LessonExtractionClient, OllamaLessonExtractionClient
from englishbot.importing.models import (
    AICapabilityAvailability,
    LessonExtractionDraft,
    SmartParseInvalidResponse,
    SmartParseRemoteError,
    SmartParseSuccess,
    SmartParseTimeout,
    SmartParseUnavailable,
)
from englishbot.logging_utils import logged_service_call

logger = logging.getLogger(__name__)


class SmartLessonParsingGateway(Protocol):
    def check_availability(self) -> AICapabilityAvailability:
        ...

    def parse(
        self,
        *,
        raw_text: str,
    ) -> (
        SmartParseSuccess
        | SmartParseUnavailable
        | SmartParseTimeout
        | SmartParseInvalidResponse
        | SmartParseRemoteError
    ):
        ...


class LegacySmartLessonParsingGateway:
    def __init__(self, extraction_client: LessonExtractionClient) -> None:
        self._extraction_client = extraction_client

    @logged_service_call("LegacySmartLessonParsingGateway.check_availability")
    def check_availability(self) -> AICapabilityAvailability:
        return AICapabilityAvailability(is_available=True)

    @logged_service_call(
        "LegacySmartLessonParsingGateway.parse",
        transforms={"raw_text": lambda value: {"text_length": len(value)}},
    )
    def parse(
        self,
        *,
        raw_text: str,
    ) -> (
        SmartParseSuccess
        | SmartParseUnavailable
        | SmartParseTimeout
        | SmartParseInvalidResponse
        | SmartParseRemoteError
    ):
        extracted = self._extraction_client.extract(raw_text)
        if isinstance(extracted, LessonExtractionDraft):
            return SmartParseSuccess(draft=extracted)
        return _map_non_draft_result(extracted)


class OllamaSmartLessonParsingGateway:
    def __init__(self, extraction_client: OllamaLessonExtractionClient) -> None:
        self._extraction_client = extraction_client

    @logged_service_call("OllamaSmartLessonParsingGateway.check_availability")
    def check_availability(self) -> AICapabilityAvailability:
        try:
            import requests
        except ImportError as error:
            return AICapabilityAvailability(is_available=False, detail=str(error))

        base_url = self._extraction_client.base_url
        try:
            response = requests.get(f"{base_url}/api/tags", timeout=5)
            response.raise_for_status()
        except requests.Timeout as error:
            return AICapabilityAvailability(is_available=False, detail=str(error))
        except requests.RequestException as error:
            return AICapabilityAvailability(is_available=False, detail=str(error))
        return AICapabilityAvailability(is_available=True)

    @logged_service_call(
        "OllamaSmartLessonParsingGateway.parse",
        transforms={"raw_text": lambda value: {"text_length": len(value)}},
    )
    def parse(
        self,
        *,
        raw_text: str,
    ) -> (
        SmartParseSuccess
        | SmartParseUnavailable
        | SmartParseTimeout
        | SmartParseInvalidResponse
        | SmartParseRemoteError
    ):
        availability = self.check_availability()
        if not availability.is_available:
            return SmartParseUnavailable(detail=availability.detail)
        extracted = self._extraction_client.extract(raw_text)
        if isinstance(extracted, LessonExtractionDraft):
            return SmartParseSuccess(draft=extracted)
        return _map_non_draft_result(extracted)


def _map_non_draft_result(
    extracted: object,
) -> SmartParseUnavailable | SmartParseTimeout | SmartParseInvalidResponse | SmartParseRemoteError:
    if isinstance(extracted, dict):
        detail = str(extracted.get("error", "")).strip() or None
        if detail is not None:
            lowered = detail.lower()
            if "timed out" in lowered or "read timeout" in lowered or "timeout" in lowered:
                return SmartParseTimeout(detail=detail)
            if "failed to establish a new connection" in lowered or "connection refused" in lowered:
                return SmartParseUnavailable(detail=detail)
            return SmartParseRemoteError(detail=detail)
        return SmartParseInvalidResponse(detail="Extraction returned a malformed object.")
    return SmartParseInvalidResponse(
        detail=f"Extraction returned an unsupported result type: {type(extracted).__name__}."
    )
