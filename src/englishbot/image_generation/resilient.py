from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from englishbot.domain.image_review_models import ImageGenerationMetadata
from englishbot.image_generation.clients import ImageGenerationClient
from englishbot.logging_utils import logged_service_call

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class ExternalImageCapabilityAvailability:
    is_available: bool
    detail: str | None = None


@dataclass(slots=True, frozen=True)
class ExternalImageGenerationSuccess:
    output_path: Path


@dataclass(slots=True, frozen=True)
class ExternalImageGenerationUnavailable:
    detail: str | None = None


@dataclass(slots=True, frozen=True)
class ExternalImageGenerationTimeout:
    detail: str | None = None


@dataclass(slots=True, frozen=True)
class ExternalImageGenerationInvalidResponse:
    detail: str | None = None


@dataclass(slots=True, frozen=True)
class ExternalImageGenerationRemoteError:
    detail: str | None = None


class ExternalImageGenerationGateway(Protocol):
    def check_availability(self) -> ExternalImageCapabilityAvailability:
        ...

    def generate(
        self,
        *,
        prompt: str,
        english_word: str,
        output_path: Path,
    ) -> (
        ExternalImageGenerationSuccess
        | ExternalImageGenerationUnavailable
        | ExternalImageGenerationTimeout
        | ExternalImageGenerationInvalidResponse
        | ExternalImageGenerationRemoteError
    ):
        ...


@dataclass(slots=True, frozen=True)
class ResilientImageGenerationResult:
    output_path: Path
    metadata: ImageGenerationMetadata


class ResilientImageGenerator:
    def __init__(
        self,
        *,
        external_gateway: ExternalImageGenerationGateway,
        fallback_client: ImageGenerationClient,
    ) -> None:
        self._external_gateway = external_gateway
        self._fallback_client = fallback_client

    @logged_service_call(
        "ResilientImageGenerator.generate",
        transforms={
            "english_word": lambda value: {"english_word": value},
            "output_path": lambda value: {"output_path": value},
        },
        result=lambda value: {
            "output_path": value.output_path,
            "path": value.metadata.path,
            "smart_generation_status": value.metadata.smart_generation_status,
        },
    )
    def generate(
        self,
        *,
        prompt: str,
        english_word: str,
        output_path: Path,
    ) -> ResilientImageGenerationResult:
        external_result = self._external_gateway.generate(
            prompt=prompt,
            english_word=english_word,
            output_path=output_path,
        )
        if isinstance(external_result, ExternalImageGenerationSuccess):
            return ResilientImageGenerationResult(
                output_path=external_result.output_path,
                metadata=ImageGenerationMetadata(
                    path="smart",
                    smart_generation_status="success",
                ),
            )

        self._fallback_client.generate(
            prompt=prompt,
            english_word=english_word,
            output_path=output_path,
        )
        return ResilientImageGenerationResult(
            output_path=output_path,
            metadata=ImageGenerationMetadata(
                path="fallback",
                smart_generation_status=_smart_status_code(external_result),
                status_messages=_fallback_status_messages(external_result),
            ),
        )


def _smart_status_code(
    result: (
        ExternalImageGenerationUnavailable
        | ExternalImageGenerationTimeout
        | ExternalImageGenerationInvalidResponse
        | ExternalImageGenerationRemoteError
    ),
) -> str:
    if isinstance(result, ExternalImageGenerationUnavailable):
        return "unavailable"
    if isinstance(result, ExternalImageGenerationTimeout):
        return "timeout"
    if isinstance(result, ExternalImageGenerationInvalidResponse):
        return "invalid_response"
    return "remote_error"


def _fallback_status_messages(
    result: (
        ExternalImageGenerationUnavailable
        | ExternalImageGenerationTimeout
        | ExternalImageGenerationInvalidResponse
        | ExternalImageGenerationRemoteError
    ),
) -> list[str]:
    if isinstance(result, ExternalImageGenerationUnavailable):
        return [
            "Local AI image generation is currently unavailable. I will use placeholder images for now.",
            "You can still search Pixabay, upload a photo, or edit the prompt.",
        ]
    if isinstance(result, ExternalImageGenerationTimeout):
        return [
            "Local AI image generation timed out. I will use placeholder images for now.",
            "You can still search Pixabay, upload a photo, or edit the prompt.",
        ]
    if isinstance(result, ExternalImageGenerationInvalidResponse):
        return [
            "Local AI image generation returned an invalid response. I will use placeholder images for now.",
            "You can still search Pixabay, upload a photo, or edit the prompt.",
        ]
    return [
        "Local AI image generation failed. I will use placeholder images for now.",
        "You can still search Pixabay, upload a photo, or edit the prompt.",
    ]
