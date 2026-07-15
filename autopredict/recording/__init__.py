"""Read-only capture and deterministic replay for public market data."""

from autopredict.recording.contracts import (
    CAPTURE_SCHEMA_VERSION,
    CaptureBundle,
    CaptureManifest,
    CaptureRecord,
    CaptureValidationError,
    PublicResponse,
    load_capture,
    write_capture,
)
from autopredict.recording.replay import replay_capture

__all__ = [
    "CAPTURE_SCHEMA_VERSION",
    "CaptureBundle",
    "CaptureManifest",
    "CaptureRecord",
    "CaptureValidationError",
    "PolymarketCaptureSource",
    "PolymarketRecorder",
    "PublicJSONTransport",
    "PublicResponse",
    "ReadOnlyPolymarketSource",
    "RequestsPublicJSONTransport",
    "load_capture",
    "replay_capture",
    "write_capture",
]


def __getattr__(name: str):
    """Load HTTP recorder implementations only when explicitly requested."""

    recorder_names = {
        "PolymarketCaptureSource",
        "PolymarketRecorder",
        "PublicJSONTransport",
        "ReadOnlyPolymarketSource",
        "RequestsPublicJSONTransport",
    }
    if name in recorder_names:
        from autopredict.recording import recorder

        return getattr(recorder, name)
    raise AttributeError(name)
