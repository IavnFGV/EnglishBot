from __future__ import annotations

from pathlib import Path

from englishbot.image_generation.clients import ComfyUIImageGenerationClient
from englishbot.image_generation.resilient import (
    ExternalImageCapabilityAvailability,
    ExternalImageGenerationGateway,
    ExternalImageGenerationInvalidResponse,
    ExternalImageGenerationRemoteError,
    ExternalImageGenerationSuccess,
    ExternalImageGenerationTimeout,
    ExternalImageGenerationUnavailable,
)
from englishbot.logging_utils import logged_service_call


class ComfyUIImageGenerationGateway:
    def __init__(self, client: ComfyUIImageGenerationClient) -> None:
        self._client = client

    @logged_service_call("ComfyUIImageGenerationGateway.check_availability")
    def check_availability(self) -> ExternalImageCapabilityAvailability:
        try:
            import requests
        except ImportError as error:
            return ExternalImageCapabilityAvailability(is_available=False, detail=str(error))
        try:
            response = requests.get(self._client.base_url, timeout=5)
            response.raise_for_status()
        except requests.Timeout as error:
            return ExternalImageCapabilityAvailability(is_available=False, detail=str(error))
        except requests.RequestException as error:
            return ExternalImageCapabilityAvailability(is_available=False, detail=str(error))
        return ExternalImageCapabilityAvailability(is_available=True)

    @logged_service_call(
        "ComfyUIImageGenerationGateway.generate",
        transforms={
            "english_word": lambda value: {"english_word": value},
            "output_path": lambda value: {"output_path": value},
        },
    )
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
        availability = self.check_availability()
        if not availability.is_available:
            return ExternalImageGenerationUnavailable(detail=availability.detail)
        try:
            self._client.generate(
                prompt=prompt,
                english_word=english_word,
                output_path=output_path,
            )
        except TimeoutError as error:
            return ExternalImageGenerationTimeout(detail=str(error))
        except ValueError as error:
            return ExternalImageGenerationInvalidResponse(detail=str(error))
        except RuntimeError as error:
            return _map_runtime_error(error)
        except Exception as error:  # noqa: BLE001
            return _map_unknown_error(error)
        return ExternalImageGenerationSuccess(output_path=output_path)


def _map_runtime_error(
    error: RuntimeError,
) -> (
    ExternalImageGenerationUnavailable
    | ExternalImageGenerationTimeout
    | ExternalImageGenerationInvalidResponse
    | ExternalImageGenerationRemoteError
):
    detail = str(error).strip()
    lowered = detail.lower()
    if "timed out" in lowered or "read timeout" in lowered or "timeout" in lowered:
        return ExternalImageGenerationTimeout(detail=detail)
    if "connection refused" in lowered or "failed to establish a new connection" in lowered:
        return ExternalImageGenerationUnavailable(detail=detail)
    if "invalid" in lowered and "response" in lowered:
        return ExternalImageGenerationInvalidResponse(detail=detail)
    return ExternalImageGenerationRemoteError(detail=detail)


def _map_unknown_error(
    error: Exception,
) -> (
    ExternalImageGenerationUnavailable
    | ExternalImageGenerationTimeout
    | ExternalImageGenerationInvalidResponse
    | ExternalImageGenerationRemoteError
):
    detail = str(error).strip()
    lowered = detail.lower()
    if "timed out" in lowered or "read timeout" in lowered or "timeout" in lowered:
        return ExternalImageGenerationTimeout(detail=detail)
    if "connection refused" in lowered or "failed to establish a new connection" in lowered:
        return ExternalImageGenerationUnavailable(detail=detail)
    return ExternalImageGenerationRemoteError(detail=detail)
