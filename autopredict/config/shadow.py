"""Strict, credential-free configuration for the shadow runtime."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_EVEN
import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

import yaml  # type: ignore[import-untyped]

if TYPE_CHECKING:
    from autopredict.live.shadow.contracts import ShadowRiskLimits


CASH_SCALE = 1_000_000
QUANTITY_SCALE = 1_000_000


SHADOW_CONFIG_VERSION = "autopredict.shadow.config.v1"
_FORBIDDEN_KEYS = {
    "api_key",
    "api_secret",
    "secret",
    "token",
    "password",
    "private_key",
    "credentials",
    "auth",
    "wallet",
    "funder",
}
_TOP_LEVEL_KEYS = {
    "schema_version",
    "mode",
    "state_path",
    "capture_manifest",
    "provider",
    "stale_after_seconds",
    "strategy",
    "risk",
}
_STRATEGY_KEYS = {"min_edge", "order_quantity"}
_RISK_KEYS = {
    "max_position",
    "max_total_exposure",
    "max_open_markets",
    "max_daily_loss",
}


@dataclass(frozen=True)
class ShadowConfig:
    state_path: Path
    capture_manifest: Path
    provider: str
    min_edge: float
    order_quantity_micros: int
    stale_after_seconds: int
    risk_limits: "ShadowRiskLimits"

    @property
    def sha256(self) -> str:
        payload = {
            "capture_manifest": str(self.capture_manifest),
            "min_edge": self.min_edge,
            "order_quantity_micros": self.order_quantity_micros,
            "provider": self.provider,
            "risk": {
                "max_open_markets": self.risk_limits.max_open_markets,
                "max_position_micros": self.risk_limits.max_position_micros,
                "max_total_exposure_cash_micros": self.risk_limits.max_total_exposure_cash_micros,
                "max_daily_loss_cash_micros": self.risk_limits.max_daily_loss_cash_micros,
            },
            "schema_version": SHADOW_CONFIG_VERSION,
            "stale_after_seconds": self.stale_after_seconds,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()


def load_shadow_config(path: str | Path) -> ShadowConfig:
    from autopredict.live.shadow.contracts import ShadowRiskLimits

    source = Path(path)
    data = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("shadow config must be a YAML object")
    _reject_credentials(data)
    _reject_unknown(data, _TOP_LEVEL_KEYS, "config")
    if data.get("schema_version") != SHADOW_CONFIG_VERSION:
        raise ValueError(f"shadow config schema_version must be {SHADOW_CONFIG_VERSION}")
    if data.get("mode") != "shadow":
        raise ValueError("shadow config mode must be 'shadow'")
    provider = data.get("provider", "market-baseline")
    if provider not in {"market-baseline", "market-recalibration"}:
        raise ValueError("unsupported shadow provider")
    strategy = _object(data.get("strategy", {}), "strategy")
    risk = _object(data.get("risk", {}), "risk")
    _reject_unknown(strategy, _STRATEGY_KEYS, "strategy")
    _reject_unknown(risk, _RISK_KEYS, "risk")
    stale = _strict_int(data.get("stale_after_seconds", 30), "stale_after_seconds")
    if stale <= 0:
        raise ValueError("stale_after_seconds must be positive")
    min_edge = float(strategy.get("min_edge", 0.05))
    if not 0 < min_edge < 1:
        raise ValueError("strategy.min_edge must be in (0, 1)")
    base = source.resolve().parent
    return ShadowConfig(
        state_path=_resolve(base, data.get("state_path"), "state_path"),
        capture_manifest=_resolve(base, data.get("capture_manifest"), "capture_manifest"),
        provider=str(provider),
        min_edge=min_edge,
        order_quantity_micros=_to_fixed(
            strategy.get("order_quantity", 1), QUANTITY_SCALE, field="strategy.order_quantity"
        ),
        stale_after_seconds=stale,
        risk_limits=ShadowRiskLimits(
            max_position_micros=_to_fixed(
                risk.get("max_position", 100), QUANTITY_SCALE, field="risk.max_position"
            ),
            max_total_exposure_cash_micros=_to_fixed(
                risk.get("max_total_exposure", 1000), CASH_SCALE, field="risk.max_total_exposure"
            ),
            max_open_markets=_strict_int(risk.get("max_open_markets", 20), "risk.max_open_markets"),
            max_daily_loss_cash_micros=_to_fixed(
                risk.get("max_daily_loss", 50), CASH_SCALE, field="risk.max_daily_loss"
            ),
        ),
    )


def _reject_credentials(value: Any, path: str = "config") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in _FORBIDDEN_KEYS or any(
                part in normalized for part in ("credential", "api_secret", "private_key")
            ):
                raise ValueError(
                    f"credential-bearing field is forbidden in shadow config: {path}.{key}"
                )
            _reject_credentials(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_credentials(item, f"{path}[{index}]")
    elif isinstance(value, str) and "${" in value:
        raise ValueError("environment substitution is forbidden in shadow config")


def _reject_unknown(value: Mapping[str, Any], allowed: set[str], path: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError(f"unknown shadow config field(s) at {path}: {unknown}")


def _object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    return value


def _resolve(base: Path, value: Any, field: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty path")
    path = Path(value)
    return path if path.is_absolute() else base / path


def _strict_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    return int(value)


def _to_fixed(value: Any, scale: int, *, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be numeric")
    try:
        decimal = Decimal(str(value))
    except Exception as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not decimal.is_finite():
        raise ValueError(f"{field} must be finite")
    fixed = int((decimal * scale).quantize(Decimal("1"), rounding=ROUND_HALF_EVEN))
    if fixed <= 0:
        raise ValueError(f"{field} must be positive")
    return fixed
