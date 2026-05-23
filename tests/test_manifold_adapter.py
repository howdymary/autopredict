"""Tests for unsupported Manifold venue behavior."""

from __future__ import annotations

import pytest

from autopredict.markets.manifold import ManifoldAdapter


def test_manifold_adapter_fails_closed_for_market_discovery() -> None:
    adapter = ManifoldAdapter()

    with pytest.raises(NotImplementedError, match="live Manifold API responses"):
        adapter.get_markets()
