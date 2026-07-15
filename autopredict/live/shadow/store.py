"""Crash-safe SQLite journal and projections for shadow execution."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_EVEN
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Callable, Iterator, Mapping, Sequence
import uuid

from .contracts import (
    ShadowFill,
    ShadowIntegrityError,
    ShadowOrder,
    ShadowSide,
    canonical_json,
    stable_id,
    utc_text,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY, started_at TEXT NOT NULL, ended_at TEXT,
  status TEXT NOT NULL, config_sha256 TEXT NOT NULL, provider_sha256 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS run_episodes (
  episode_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(run_id),
  episode_number INTEGER NOT NULL, lease_token TEXT NOT NULL,
  started_at TEXT NOT NULL, ended_at TEXT, status TEXT NOT NULL,
  UNIQUE(run_id,episode_number)
);
CREATE TABLE IF NOT EXISTS feed_events (
  event_id TEXT PRIMARY KEY, feed_id TEXT NOT NULL, capture_sequence INTEGER NOT NULL,
  payload_sha256 TEXT NOT NULL, payload_json TEXT NOT NULL,
  event_type TEXT NOT NULL, observed_at TEXT NOT NULL
  , UNIQUE(feed_id,capture_sequence)
);
CREATE TABLE IF NOT EXISTS feed_cursors (
  feed_id TEXT PRIMARY KEY, capture_sequence INTEGER NOT NULL,
  event_id TEXT NOT NULL, observed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS decisions (
  decision_id TEXT PRIMARY KEY, decision_key TEXT UNIQUE NOT NULL,
  payload_sha256 TEXT NOT NULL, payload_json TEXT NOT NULL,
  status TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS intents (
  client_order_id TEXT PRIMARY KEY, decision_id TEXT NOT NULL REFERENCES decisions(decision_id),
  payload_sha256 TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS orders (
  client_order_id TEXT PRIMARY KEY REFERENCES intents(client_order_id),
  decision_id TEXT NOT NULL, market_id TEXT NOT NULL, side TEXT NOT NULL,
  order_type TEXT NOT NULL, quantity_micros INTEGER NOT NULL,
  remaining_micros INTEGER NOT NULL, limit_price_nanos INTEGER,
  reduce_only INTEGER NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
  queue_ahead_micros INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS fills (
  fill_id TEXT PRIMARY KEY, client_order_id TEXT NOT NULL REFERENCES orders(client_order_id),
  market_id TEXT NOT NULL, side TEXT NOT NULL, quantity_micros INTEGER NOT NULL,
  price_nanos INTEGER NOT NULL, source_event_id TEXT NOT NULL, filled_at TEXT NOT NULL,
  fee_cash_micros INTEGER NOT NULL, payload_sha256 TEXT NOT NULL,
  application_sequence INTEGER UNIQUE NOT NULL
);
CREATE TABLE IF NOT EXISTS positions (
  market_id TEXT PRIMARY KEY, quantity_micros INTEGER NOT NULL,
  avg_entry_price_nanos INTEGER NOT NULL, realized_pnl_cash_micros INTEGER NOT NULL,
  fees_cash_micros INTEGER NOT NULL, mark_price_nanos INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS risk_state (
  singleton INTEGER PRIMARY KEY CHECK(singleton=1), breaker_active INTEGER NOT NULL,
  breaker_reason TEXT, breaker_detail TEXT, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS state_events (
  sequence INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT UNIQUE NOT NULL,
  event_type TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rejections (
  rejection_id TEXT PRIMARY KEY, decision_id TEXT NOT NULL REFERENCES decisions(decision_id),
  reason TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS trade_applications (
  source_event_id TEXT PRIMARY KEY REFERENCES feed_events(event_id),
  plan_sha256 TEXT NOT NULL, plan_json TEXT NOT NULL, applied_at TEXT NOT NULL
);
"""


class ShadowStateStore:
    """SQLite v1 state whose journal and projections change atomically."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        path: Path,
        lease_clock: Callable[[], datetime],
    ) -> None:
        self.connection = connection
        self.path = path
        self.connection.row_factory = sqlite3.Row
        self._lease_token: str | None = None
        self._episode_id: str | None = None
        self._lease_clock = lease_clock

    @classmethod
    def open(
        cls,
        path: str | Path,
        *,
        lease_clock: Callable[[], datetime] | None = None,
    ) -> "ShadowStateStore":
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(target), isolation_level=None)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA foreign_keys=ON")
        store = cls(
            connection,
            target,
            lease_clock or (lambda: datetime.now(timezone.utc)),
        )
        store.initialize()
        return store

    def initialize(self) -> None:
        version = int(self.connection.execute("PRAGMA user_version").fetchone()[0])
        if version not in {0, 1}:
            raise ShadowIntegrityError(f"unsupported shadow state schema: {version}")
        self.connection.executescript(_SCHEMA)
        self.connection.execute("PRAGMA user_version=1")

    def close(self) -> None:
        self.connection.close()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield
        except Exception:
            self.connection.execute("ROLLBACK")
            raise
        else:
            self.connection.execute("COMMIT")

    def _journal(self, event_type: str, payload: Mapping[str, Any], at: datetime) -> None:
        body = dict(payload)
        event_id = stable_id(event_type, body)
        self.connection.execute(
            "INSERT OR IGNORE INTO state_events(event_id,event_type,payload_json,created_at) "
            "VALUES(?,?,?,?)",
            (event_id, event_type, canonical_json(body), utc_text(at)),
        )

    def _assert_lease(self) -> None:
        row = self.connection.execute(
            "SELECT value FROM metadata WHERE key='writer_lease'"
        ).fetchone()
        if row is None:
            raise ShadowIntegrityError("shadow writer lease is missing")
        lease = json.loads(row["value"])
        if self._lease_token is None or lease.get("token") != self._lease_token:
            raise ShadowIntegrityError("shadow writer does not hold the current fencing token")
        expires = datetime.fromisoformat(lease["expires_at"].replace("Z", "+00:00"))
        if self._lease_clock() >= expires:
            raise ShadowIntegrityError("shadow writer lease has expired")

    def start_run(
        self,
        *,
        run_id: str,
        at: datetime,
        config_sha256: str,
        provider_sha256: str,
        lease_seconds: int = 60,
    ) -> None:
        with self.transaction():
            if lease_seconds <= 0:
                raise ValueError("lease_seconds must be positive")
            lease_now = self._lease_clock()
            utc_text(lease_now)
            lease = self.connection.execute(
                "SELECT value FROM metadata WHERE key='writer_lease'"
            ).fetchone()
            if lease:
                value = json.loads(lease["value"])
                expires = datetime.fromisoformat(value["expires_at"].replace("Z", "+00:00"))
                if expires > lease_now:
                    raise ShadowIntegrityError("another shadow writer holds the lease")
            self._lease_token = uuid.uuid4().hex
            self.connection.execute(
                "UPDATE runs SET status='interrupted', ended_at=? WHERE status='running' AND run_id<>?",
                (utc_text(at), run_id),
            )
            self.connection.execute(
                "UPDATE run_episodes SET status='interrupted',ended_at=? WHERE status='running'",
                (utc_text(at),),
            )
            existing = self.connection.execute(
                "SELECT config_sha256,provider_sha256 FROM runs WHERE run_id=?", (run_id,)
            ).fetchone()
            if existing and tuple(existing) != (config_sha256, provider_sha256):
                raise ShadowIntegrityError("run id reused with different configuration")
            self.connection.execute(
                "INSERT INTO runs VALUES(?,?,NULL,'running',?,?) ON CONFLICT(run_id) DO UPDATE SET "
                "ended_at=NULL,status='running'",
                (run_id, utc_text(at), config_sha256, provider_sha256),
            )
            episode_number = self.connection.execute(
                "SELECT COALESCE(MAX(episode_number),0)+1 FROM run_episodes WHERE run_id=?",
                (run_id,),
            ).fetchone()[0]
            self._episode_id = f"{run_id}:episode:{episode_number}"
            self.connection.execute(
                "INSERT INTO run_episodes VALUES(?,?,?,?,?,NULL,'running')",
                (
                    self._episode_id,
                    run_id,
                    episode_number,
                    self._lease_token,
                    utc_text(at),
                ),
            )
            expires_at = lease_now + timedelta(seconds=lease_seconds)
            self.connection.execute(
                "INSERT INTO metadata VALUES('writer_lease',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (
                    canonical_json(
                        {
                            "run_id": run_id,
                            "token": self._lease_token,
                            "expires_at": utc_text(expires_at),
                        }
                    ),
                ),
            )
            self._journal(
                "run_started",
                {"run_id": run_id, "episode_id": self._episode_id},
                at,
            )

    def renew_lease(self, run_id: str, *, at: datetime, lease_seconds: int = 60) -> None:
        with self.transaction():
            self._assert_lease()
            if lease_seconds <= 0:
                raise ValueError("lease_seconds must be positive")
            lease = self.connection.execute(
                "SELECT value FROM metadata WHERE key='writer_lease'"
            ).fetchone()
            if not lease or json.loads(lease["value"])["run_id"] != run_id:
                raise ShadowIntegrityError("shadow writer lease is not held by this run")
            lease_now = self._lease_clock()
            utc_text(lease_now)
            expires = lease_now + timedelta(seconds=lease_seconds)
            self.connection.execute(
                "UPDATE metadata SET value=? WHERE key='writer_lease'",
                (
                    canonical_json(
                        {
                            "run_id": run_id,
                            "token": self._lease_token,
                            "expires_at": utc_text(expires),
                        }
                    ),
                ),
            )

    def release_lease(self, run_id: str) -> None:
        with self.transaction():
            self._assert_lease()
            lease = self.connection.execute(
                "SELECT value FROM metadata WHERE key='writer_lease'"
            ).fetchone()
            if lease and json.loads(lease["value"])["run_id"] == run_id:
                self.connection.execute("DELETE FROM metadata WHERE key='writer_lease'")
                self._lease_token = None
                self._episode_id = None

    def end_run(self, run_id: str, at: datetime, status: str = "completed") -> None:
        with self.transaction():
            self._assert_lease()
            changed = self.connection.execute(
                "UPDATE runs SET status=?, ended_at=? WHERE run_id=? AND status='running'",
                (status, utc_text(at), run_id),
            ).rowcount
            if changed != 1:
                raise ShadowIntegrityError("cannot end a run that is not active")
            episode_changed = self.connection.execute(
                "UPDATE run_episodes SET status=?,ended_at=? WHERE episode_id=? AND status='running'",
                (status, utc_text(at), self._episode_id),
            ).rowcount
            if episode_changed != 1:
                raise ShadowIntegrityError("cannot end a missing run episode")
            self._journal(
                "run_ended",
                {"run_id": run_id, "episode_id": self._episode_id, "status": status},
                at,
            )
        self.release_lease(run_id)

    def record_feed_event(
        self,
        *,
        event_id: str,
        capture_sequence: int,
        event_type: str,
        observed_at: datetime,
        payload: Mapping[str, Any],
        feed_id: str = "default",
    ) -> bool:
        if any(
            not isinstance(value, str) or not value.strip()
            for value in (event_id, event_type, feed_id)
        ):
            raise ValueError("feed identifiers must be non-empty strings")
        digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
        rendered = canonical_json(payload)
        with self.transaction():
            self._assert_lease()
            existing = self.connection.execute(
                "SELECT event_id,payload_sha256,event_type,observed_at FROM feed_events "
                "WHERE feed_id=? AND capture_sequence=?",
                (feed_id, capture_sequence),
            ).fetchone()
            if existing:
                if (
                    existing["event_id"] != event_id
                    or existing["payload_sha256"] != digest
                    or existing["event_type"] != event_type
                    or existing["observed_at"] != utc_text(observed_at)
                ):
                    raise ShadowIntegrityError("feed sequence reused with conflicting payload")
                return False
            duplicate_id = self.connection.execute(
                "SELECT capture_sequence,payload_sha256 FROM feed_events WHERE event_id=?",
                (event_id,),
            ).fetchone()
            if duplicate_id:
                raise ShadowIntegrityError("feed event id reused at a different sequence")
            prior = self.connection.execute(
                "SELECT capture_sequence,observed_at FROM feed_cursors WHERE feed_id=?", (feed_id,)
            ).fetchone()
            if prior is None and capture_sequence != 1 and event_type != "FeedFault":
                raise ShadowIntegrityError("initial feed sequence must be 1 or an explicit fault")
            if prior and capture_sequence <= prior["capture_sequence"]:
                raise ShadowIntegrityError("out-of-order feed event")
            if prior and capture_sequence != prior["capture_sequence"] + 1:
                raise ShadowIntegrityError("non-contiguous feed sequence")
            if prior:
                prior_at = datetime.fromisoformat(prior["observed_at"].replace("Z", "+00:00"))
                if observed_at < prior_at and event_type != "FeedFault":
                    raise ShadowIntegrityError("feed observed_at regressed")
            self.connection.execute(
                "INSERT INTO feed_events VALUES(?,?,?,?,?,?,?)",
                (
                    event_id,
                    feed_id,
                    capture_sequence,
                    digest,
                    rendered,
                    event_type,
                    utc_text(observed_at),
                ),
            )
            self.connection.execute(
                "INSERT INTO feed_cursors VALUES(?,?,?,?) ON CONFLICT(feed_id) DO UPDATE SET "
                "capture_sequence=excluded.capture_sequence,event_id=excluded.event_id,"
                "observed_at=excluded.observed_at",
                (feed_id, capture_sequence, event_id, utc_text(observed_at)),
            )
            self._journal(
                "feed_event",
                {
                    "event_id": event_id,
                    "feed_id": feed_id,
                    "capture_sequence": capture_sequence,
                    "event_type": event_type,
                    "observed_at": utc_text(observed_at),
                    "sha256": digest,
                },
                observed_at,
            )
            return True

    def record_decision(
        self,
        *,
        decision_id: str,
        decision_key: str,
        status: str,
        payload: Mapping[str, Any],
        at: datetime,
    ) -> bool:
        digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
        with self.transaction():
            self._assert_lease()
            existing = self.connection.execute(
                "SELECT decision_id,payload_sha256,status FROM decisions WHERE decision_key=?",
                (decision_key,),
            ).fetchone()
            if existing:
                if (
                    existing["decision_id"] != decision_id
                    or existing["payload_sha256"] != digest
                    or existing["status"] != status
                ):
                    raise ShadowIntegrityError("decision key reused with conflicting payload")
                return False
            self.connection.execute(
                "INSERT INTO decisions VALUES(?,?,?,?,?,?)",
                (decision_id, decision_key, digest, canonical_json(payload), status, utc_text(at)),
            )
            self._journal(
                "decision",
                {"decision_id": decision_id, "status": status, "payload_sha256": digest},
                at,
            )
            return True

    def decision_by_key(self, decision_key: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM decisions WHERE decision_key=?", (decision_key,)
        ).fetchone()
        if row is None:
            return None
        value = dict(row)
        value["payload"] = json.loads(value.pop("payload_json"))
        return value

    def record_rejection(
        self,
        *,
        rejection_id: str,
        decision_id: str,
        reason: str,
        payload: Mapping[str, Any],
        at: datetime,
    ) -> None:
        with self.transaction():
            self._assert_lease()
            existing = self.connection.execute(
                "SELECT reason,payload_json FROM rejections WHERE rejection_id=?",
                (rejection_id,),
            ).fetchone()
            rendered = canonical_json(payload)
            if existing:
                if tuple(existing) != (reason, rendered):
                    raise ShadowIntegrityError("rejection id reused with conflicting evidence")
                return
            self.connection.execute(
                "INSERT INTO rejections VALUES(?,?,?,?,?)",
                (rejection_id, decision_id, reason, rendered, utc_text(at)),
            )
            self._journal(
                "risk_rejected",
                {"rejection_id": rejection_id, "decision_id": decision_id, "reason": reason},
                at,
            )

    def rejection(self, rejection_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM rejections WHERE rejection_id=?", (rejection_id,)
        ).fetchone()
        return dict(row) if row else None

    def submit_order(self, order: ShadowOrder, *, queue_ahead_micros: int = 0) -> bool:
        if (
            isinstance(queue_ahead_micros, bool)
            or not isinstance(queue_ahead_micros, int)
            or queue_ahead_micros < 0
        ):
            raise ValueError("queue_ahead_micros must be a non-negative integer")
        payload = {
            "client_order_id": order.client_order_id,
            "decision_id": order.decision_id,
            "market_id": order.market_id,
            "side": order.side.value,
            "order_type": order.order_type.value,
            "quantity_micros": order.quantity_micros,
            "limit_price_nanos": order.limit_price_nanos,
            "reduce_only": order.reduce_only,
            "created_at": utc_text(order.created_at),
            "queue_ahead_micros": queue_ahead_micros,
        }
        digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
        with self.transaction():
            self._assert_lease()
            existing = self.connection.execute(
                "SELECT payload_sha256 FROM intents WHERE client_order_id=?",
                (order.client_order_id,),
            ).fetchone()
            if existing:
                if existing["payload_sha256"] != digest:
                    raise ShadowIntegrityError("client order id reused with conflicting intent")
                return False
            self.connection.execute(
                "INSERT INTO intents VALUES(?,?,?,?,?)",
                (
                    order.client_order_id,
                    order.decision_id,
                    digest,
                    canonical_json(payload),
                    utc_text(order.created_at),
                ),
            )
            self.connection.execute(
                "INSERT INTO orders VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    order.client_order_id,
                    order.decision_id,
                    order.market_id,
                    order.side.value,
                    order.order_type.value,
                    order.quantity_micros,
                    order.quantity_micros,
                    order.limit_price_nanos,
                    int(order.reduce_only),
                    "open",
                    utc_text(order.created_at),
                    queue_ahead_micros,
                ),
            )
            self._journal("order_opened", payload, order.created_at)
            return True

    def apply_fill(self, fill: ShadowFill) -> bool:
        with self.transaction():
            self._assert_lease()
            return self._apply_fill_locked(fill)

    def trade_application(self, source_event_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM trade_applications WHERE source_event_id=?",
            (source_event_id,),
        ).fetchone()
        return dict(row) if row else None

    def apply_trade_plan(
        self,
        *,
        source_event_id: str,
        queue_changes: Mapping[str, int],
        fills: Sequence[ShadowFill],
        at: datetime,
    ) -> bool:
        if not isinstance(source_event_id, str) or not source_event_id.strip():
            raise ValueError("trade plan source_event_id must be non-empty")
        normalized_queues: dict[str, int] = {}
        for client_order_id, quantity in queue_changes.items():
            if not isinstance(client_order_id, str) or not client_order_id.strip():
                raise ValueError("trade plan order ids must be non-empty")
            if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 0:
                raise ValueError("trade plan queue quantities must be non-negative integers")
            normalized_queues[client_order_id] = quantity
        plan = {
            "source_event_id": source_event_id,
            "queue_changes": dict(sorted(normalized_queues.items())),
            "fills": [_fill_identity(fill) for fill in fills],
            "applied_at": utc_text(at),
        }
        rendered = canonical_json(plan)
        digest = hashlib.sha256(rendered.encode("utf-8")).hexdigest()
        with self.transaction():
            self._assert_lease()
            existing = self.connection.execute(
                "SELECT plan_sha256,plan_json FROM trade_applications WHERE source_event_id=?",
                (source_event_id,),
            ).fetchone()
            if existing:
                if tuple(existing) != (digest, rendered):
                    raise ShadowIntegrityError(
                        "trade event reused with conflicting allocation plan"
                    )
                return False
            source = self.connection.execute(
                "SELECT event_type,payload_json,observed_at FROM feed_events WHERE event_id=?",
                (source_event_id,),
            ).fetchone()
            if source is None or source["event_type"] != "TradePrint":
                raise ShadowIntegrityError("trade plan source must be a durable TradePrint")
            for client_order_id, quantity in normalized_queues.items():
                order = self.connection.execute(
                    "SELECT status FROM orders WHERE client_order_id=?", (client_order_id,)
                ).fetchone()
                if order is None or order["status"] != "open":
                    raise ShadowIntegrityError("trade plan queue change references non-open order")
                self.connection.execute(
                    "UPDATE orders SET queue_ahead_micros=? WHERE client_order_id=?",
                    (quantity, client_order_id),
                )
            for fill in fills:
                if fill.source_event_id != source_event_id:
                    raise ShadowIntegrityError("trade fill source disagrees with allocation plan")
                self._apply_fill_locked(fill)
            self.connection.execute(
                "INSERT INTO trade_applications VALUES(?,?,?,?)",
                (source_event_id, digest, rendered, utc_text(at)),
            )
            self._journal(
                "trade_applied",
                {"source_event_id": source_event_id, "plan_sha256": digest},
                at,
            )
            return True

    def _apply_fill_locked(self, fill: ShadowFill) -> bool:
        existing = self.connection.execute(
            "SELECT * FROM fills WHERE fill_id=?", (fill.fill_id,)
        ).fetchone()
        if existing:
            payload = _fill_payload(fill, existing["application_sequence"])
            digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
            if existing["payload_sha256"] != digest:
                raise ShadowIntegrityError("fill id reused with conflicting fill")
            return False
        order = self.connection.execute(
            "SELECT remaining_micros,side,market_id,status,created_at FROM orders "
            "WHERE client_order_id=?",
            (fill.client_order_id,),
        ).fetchone()
        if not order or order["status"] != "open":
            raise ShadowIntegrityError("fill references missing or closed order")
        if order["side"] != fill.side.value or order["market_id"] != fill.market_id:
            raise ShadowIntegrityError("fill identity disagrees with order")
        if fill.quantity_micros > order["remaining_micros"]:
            raise ShadowIntegrityError("fill quantity exceeds remaining order")
        created_at = datetime.fromisoformat(order["created_at"].replace("Z", "+00:00"))
        if fill.filled_at < created_at:
            raise ShadowIntegrityError("fill predates order creation")
        self._validate_fill_source_locked(fill)
        application_sequence = self.connection.execute(
            "SELECT COALESCE(MAX(application_sequence),0)+1 FROM fills"
        ).fetchone()[0]
        payload = _fill_payload(fill, application_sequence)
        digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
        self.connection.execute(
            "INSERT INTO fills VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                fill.fill_id,
                fill.client_order_id,
                fill.market_id,
                fill.side.value,
                fill.quantity_micros,
                fill.price_nanos,
                fill.source_event_id,
                utc_text(fill.filled_at),
                fill.fee_cash_micros,
                digest,
                application_sequence,
            ),
        )
        remaining = order["remaining_micros"] - fill.quantity_micros
        self.connection.execute(
            "UPDATE orders SET remaining_micros=?,status=? WHERE client_order_id=?",
            (remaining, "filled" if remaining == 0 else "open", fill.client_order_id),
        )
        position = self.connection.execute(
            "SELECT * FROM positions WHERE market_id=?", (fill.market_id,)
        ).fetchone()
        values = _apply_accounting(dict(position) if position else None, fill)
        self.connection.execute(
            "INSERT INTO positions VALUES(?,?,?,?,?,?) ON CONFLICT(market_id) DO UPDATE SET "
            "quantity_micros=excluded.quantity_micros,"
            "avg_entry_price_nanos=excluded.avg_entry_price_nanos,"
            "realized_pnl_cash_micros=excluded.realized_pnl_cash_micros,"
            "fees_cash_micros=excluded.fees_cash_micros,"
            "mark_price_nanos=excluded.mark_price_nanos",
            (fill.market_id, *values),
        )
        self._journal("fill", payload, fill.filled_at)
        return True

    def _validate_fill_source_locked(self, fill: ShadowFill) -> None:
        source_id = fill.source_event_id.split(":", 1)[0]
        source = self.connection.execute(
            "SELECT event_type,payload_json,observed_at FROM feed_events WHERE event_id=?",
            (source_id,),
        ).fetchone()
        if source is None:
            raise ShadowIntegrityError("fill source event is not durable")
        expected_type = "BookObservation" if ":depth:" in fill.source_event_id else "TradePrint"
        if source["event_type"] != expected_type:
            raise ShadowIntegrityError("fill source event has an invalid type")
        source_payload = json.loads(source["payload_json"])
        if source_payload.get("market_id") != fill.market_id:
            raise ShadowIntegrityError("fill source market disagrees with fill")
        source_at = datetime.fromisoformat(source["observed_at"].replace("Z", "+00:00"))
        if source_at > fill.filled_at:
            raise ShadowIntegrityError("fill predates its durable source event")

    def set_queue_ahead(self, client_order_id: str, quantity_micros: int) -> None:
        if (
            isinstance(quantity_micros, bool)
            or not isinstance(quantity_micros, int)
            or quantity_micros < 0
        ):
            raise ValueError("queue_ahead_micros must be a non-negative integer")
        with self.transaction():
            self._assert_lease()
            self.connection.execute(
                "UPDATE orders SET queue_ahead_micros=? WHERE client_order_id=? AND status='open'",
                (max(0, quantity_micros), client_order_id),
            )

    def positions(self) -> dict[str, int]:
        return {
            row["market_id"]: row["quantity_micros"]
            for row in self.connection.execute("SELECT * FROM positions")
        }

    def position_details(self) -> dict[str, dict[str, int]]:
        return {
            row["market_id"]: dict(row)
            for row in self.connection.execute("SELECT * FROM positions")
        }

    def reservations(self) -> dict[str, tuple[int, int]]:
        result: dict[str, tuple[int, int]] = {}
        rows = self.connection.execute(
            "SELECT market_id,side,SUM(remaining_micros) quantity FROM orders "
            "WHERE status='open' GROUP BY market_id,side"
        )
        for row in rows:
            buys, sells = result.get(row["market_id"], (0, 0))
            if row["side"] == "buy":
                buys = row["quantity"]
            else:
                sells = row["quantity"]
            result[row["market_id"]] = (buys, sells)
        return result

    def reservation_exposure(self) -> dict[str, int]:
        result: dict[str, int] = {}
        rows = self.connection.execute(
            "SELECT market_id,side,remaining_micros,limit_price_nanos,order_type "
            "FROM orders WHERE status='open'"
        )
        for row in rows:
            if row["side"] == "buy":
                price = row["limit_price_nanos"] if row["order_type"] == "limit" else 1_000_000_000
                numerator = row["remaining_micros"] * price
            else:
                price = row["limit_price_nanos"] if row["order_type"] == "limit" else 0
                numerator = row["remaining_micros"] * (1_000_000_000 - price)
            exposure = (numerator + 999_999_999) // 1_000_000_000
            result[row["market_id"]] = result.get(row["market_id"], 0) + exposure
        return result

    def open_orders(self, market_id: str | None = None) -> list[sqlite3.Row]:
        if market_id is None:
            return list(
                self.connection.execute(
                    "SELECT * FROM orders WHERE status='open' ORDER BY created_at,client_order_id"
                )
            )
        return list(
            self.connection.execute(
                "SELECT * FROM orders WHERE status='open' AND market_id=? ORDER BY created_at,client_order_id",
                (market_id,),
            )
        )

    def feed_cursor(self, feed_id: str = "default") -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM feed_cursors WHERE feed_id=?", (feed_id,)
        ).fetchone()
        return dict(row) if row else None

    def cancel_order(self, client_order_id: str, *, at: datetime, reason: str) -> bool:
        with self.transaction():
            self._assert_lease()
            changed = self.connection.execute(
                "UPDATE orders SET status='canceled' WHERE client_order_id=? AND status='open'",
                (client_order_id,),
            ).rowcount
            if changed:
                self._journal(
                    "order_canceled",
                    {"client_order_id": client_order_id, "reason": reason},
                    at,
                )
            return bool(changed)

    def cancel_all(self, *, at: datetime, reason: str) -> int:
        with self.transaction():
            self._assert_lease()
            rows = list(
                self.connection.execute(
                    "SELECT client_order_id FROM orders WHERE status='open' ORDER BY client_order_id"
                )
            )
            for row in rows:
                self.connection.execute(
                    "UPDATE orders SET status='canceled' WHERE client_order_id=?",
                    (row["client_order_id"],),
                )
                self._journal(
                    "order_canceled",
                    {"client_order_id": row["client_order_id"], "reason": reason},
                    at,
                )
            return len(rows)

    def latch_breaker(self, *, reason: str, detail: str, at: datetime) -> None:
        with self.transaction():
            self._assert_lease()
            self.connection.execute(
                "INSERT INTO risk_state VALUES(1,1,?,?,?) ON CONFLICT(singleton) DO UPDATE SET "
                "breaker_active=1,breaker_reason=excluded.breaker_reason,"
                "breaker_detail=excluded.breaker_detail,updated_at=excluded.updated_at",
                (reason, detail, utc_text(at)),
            )
            rows = list(
                self.connection.execute("SELECT client_order_id FROM orders WHERE status='open'")
            )
            self.connection.execute("UPDATE orders SET status='canceled' WHERE status='open'")
            for row in rows:
                self._journal(
                    "order_canceled",
                    {"client_order_id": row["client_order_id"], "reason": reason},
                    at,
                )
            self._journal("breaker_latched", {"reason": reason, "detail": detail}, at)

    def breaker(self) -> dict[str, Any]:
        row = self.connection.execute("SELECT * FROM risk_state WHERE singleton=1").fetchone()
        return (
            dict(row)
            if row
            else {"breaker_active": 0, "breaker_reason": None, "breaker_detail": None}
        )

    def reset_breaker(self, *, at: datetime, freshness_seconds: int, reason: str) -> None:
        if not reason.strip():
            raise ValueError("reset reason must be non-empty")
        self.reconcile()
        cursors = list(
            self.connection.execute("SELECT observed_at FROM feed_cursors ORDER BY feed_id")
        )
        if not cursors:
            raise ShadowIntegrityError("cannot reset before a reconciled feed cursor exists")
        for cursor in cursors:
            age = (
                at - datetime.fromisoformat(cursor["observed_at"].replace("Z", "+00:00"))
            ).total_seconds()
            if age < 0 or age > freshness_seconds:
                raise ShadowIntegrityError("cannot reset without fresh reconciled feed cursors")
        with self.transaction():
            self._assert_lease()
            self.connection.execute(
                "UPDATE risk_state SET breaker_active=0,breaker_reason=NULL,breaker_detail=NULL,updated_at=? WHERE singleton=1",
                (utc_text(at),),
            )
            self._journal("breaker_reset", {"explicit": True, "reason": reason}, at)

    def reconcile(self) -> None:
        self._assert_lease()
        if self.connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ShadowIntegrityError("SQLite integrity check failed")
        if list(self.connection.execute("PRAGMA foreign_key_check")):
            raise ShadowIntegrityError("SQLite foreign-key check failed")
        for feed in self.connection.execute("SELECT * FROM feed_events"):
            digest = hashlib.sha256(feed["payload_json"].encode("utf-8")).hexdigest()
            if digest != feed["payload_sha256"]:
                raise ShadowIntegrityError("feed payload digest mismatch")
            journal_payload = {
                "event_id": feed["event_id"],
                "feed_id": feed["feed_id"],
                "capture_sequence": feed["capture_sequence"],
                "event_type": feed["event_type"],
                "observed_at": feed["observed_at"],
                "sha256": digest,
            }
            if not self._journal_matches("feed_event", journal_payload):
                raise ShadowIntegrityError("feed event disagrees with authoritative journal")
        for decision in self.connection.execute("SELECT * FROM decisions"):
            digest = hashlib.sha256(decision["payload_json"].encode("utf-8")).hexdigest()
            if digest != decision["payload_sha256"]:
                raise ShadowIntegrityError("decision payload digest mismatch")
            journal_payload = {
                "decision_id": decision["decision_id"],
                "status": decision["status"],
                "payload_sha256": digest,
            }
            if not self._journal_matches("decision", journal_payload):
                raise ShadowIntegrityError("decision disagrees with authoritative journal")
        for intent in self.connection.execute("SELECT * FROM intents"):
            if (
                hashlib.sha256(intent["payload_json"].encode("utf-8")).hexdigest()
                != intent["payload_sha256"]
            ):
                raise ShadowIntegrityError("intent payload digest mismatch")
            payload = json.loads(intent["payload_json"])
            order = self.connection.execute(
                "SELECT * FROM orders WHERE client_order_id=?", (intent["client_order_id"],)
            ).fetchone()
            if order is None:
                raise ShadowIntegrityError("intent has no order projection")
            for field in (
                "client_order_id",
                "decision_id",
                "market_id",
                "side",
                "order_type",
                "quantity_micros",
                "limit_price_nanos",
                "created_at",
            ):
                if order[field] != payload[field]:
                    raise ShadowIntegrityError(f"order projection contradicts intent: {field}")
            if bool(order["reduce_only"]) != bool(payload["reduce_only"]):
                raise ShadowIntegrityError("order projection contradicts intent: reduce_only")
            if not self._journal_matches("order_opened", payload):
                raise ShadowIntegrityError("intent disagrees with authoritative journal")
        for application in self.connection.execute("SELECT * FROM trade_applications"):
            digest = hashlib.sha256(application["plan_json"].encode("utf-8")).hexdigest()
            if digest != application["plan_sha256"]:
                raise ShadowIntegrityError("trade allocation plan digest mismatch")
            if not self._journal_matches(
                "trade_applied",
                {
                    "source_event_id": application["source_event_id"],
                    "plan_sha256": digest,
                },
            ):
                raise ShadowIntegrityError("trade allocation disagrees with journal")
        order_totals: dict[str, int] = {}
        rebuilt: dict[str, tuple[int, int, int, int, int]] = {}
        fills = self.connection.execute("SELECT * FROM fills ORDER BY application_sequence")
        for expected_sequence, row in enumerate(fills, start=1):
            if row["application_sequence"] != expected_sequence:
                raise ShadowIntegrityError("fill application sequence is not canonical")
            fill = ShadowFill(
                fill_id=row["fill_id"],
                client_order_id=row["client_order_id"],
                market_id=row["market_id"],
                side=ShadowSide(row["side"]),
                quantity_micros=row["quantity_micros"],
                price_nanos=row["price_nanos"],
                source_event_id=row["source_event_id"],
                filled_at=datetime.fromisoformat(row["filled_at"].replace("Z", "+00:00")),
                fee_cash_micros=row["fee_cash_micros"],
            )
            payload = _fill_payload(fill, expected_sequence)
            digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
            if digest != row["payload_sha256"]:
                raise ShadowIntegrityError("fill payload digest mismatch")
            if not self._journal_matches("fill", payload):
                raise ShadowIntegrityError("fill disagrees with authoritative journal")
            self._validate_fill_source_locked(fill)
            order = self.connection.execute(
                "SELECT market_id,side,quantity_micros FROM orders WHERE client_order_id=?",
                (row["client_order_id"],),
            ).fetchone()
            if not order or order["market_id"] != row["market_id"] or order["side"] != row["side"]:
                raise ShadowIntegrityError("authoritative fill contradicts its order")
            order_totals[row["client_order_id"]] = (
                order_totals.get(row["client_order_id"], 0) + row["quantity_micros"]
            )
            if order_totals[row["client_order_id"]] > order["quantity_micros"]:
                raise ShadowIntegrityError("authoritative fills exceed order quantity")
            prior_tuple = rebuilt.get(row["market_id"])
            prior = (
                None
                if prior_tuple is None
                else {
                    "quantity_micros": prior_tuple[0],
                    "avg_entry_price_nanos": prior_tuple[1],
                    "realized_pnl_cash_micros": prior_tuple[2],
                    "fees_cash_micros": prior_tuple[3],
                    "mark_price_nanos": prior_tuple[4],
                }
            )
            values = _apply_accounting(prior, fill)
            rebuilt[row["market_id"]] = values
        with self.transaction():
            self._assert_lease()
            self.connection.execute("DELETE FROM positions")
            for market_id, values in sorted(rebuilt.items()):
                self.connection.execute(
                    "INSERT INTO positions VALUES(?,?,?,?,?,?)", (market_id, *values)
                )
            for row in self.connection.execute(
                "SELECT client_order_id,quantity_micros FROM orders"
            ):
                filled = order_totals.get(row["client_order_id"], 0)
                remaining = row["quantity_micros"] - filled
                self.connection.execute(
                    "UPDATE orders SET remaining_micros=?,status=CASE "
                    "WHEN status='canceled' THEN 'canceled' WHEN ?=0 THEN 'filled' ELSE 'open' END "
                    "WHERE client_order_id=?",
                    (remaining, remaining, row["client_order_id"]),
                )
        bad = self.connection.execute(
            "SELECT COUNT(*) FROM orders WHERE remaining_micros<0 OR remaining_micros>quantity_micros"
        ).fetchone()[0]
        if bad:
            raise ShadowIntegrityError("order projection has invalid remaining quantity")

    def reconcile_startup(self) -> None:
        self.reconcile()

    def _journal_matches(self, event_type: str, payload: Mapping[str, Any]) -> bool:
        event_id = stable_id(event_type, payload)
        row = self.connection.execute(
            "SELECT payload_json FROM state_events WHERE event_id=? AND event_type=?",
            (event_id, event_type),
        ).fetchone()
        return bool(row and row["payload_json"] == canonical_json(payload))

    def canonical_export(self) -> dict[str, Any]:
        tables = (
            "runs",
            "run_episodes",
            "feed_events",
            "feed_cursors",
            "decisions",
            "rejections",
            "trade_applications",
            "intents",
            "orders",
            "fills",
            "positions",
            "risk_state",
            "state_events",
        )
        ordering = {
            "runs": "run_id",
            "run_episodes": "run_id,episode_number",
            "feed_events": "feed_id,capture_sequence,event_id",
            "feed_cursors": "feed_id",
            "decisions": "decision_id",
            "rejections": "rejection_id",
            "trade_applications": "source_event_id",
            "intents": "client_order_id",
            "orders": "client_order_id",
            "fills": "fill_id",
            "positions": "market_id",
            "risk_state": "singleton",
            "state_events": "sequence,event_id",
        }
        export: dict[str, Any] = {"schema_version": 1}
        self.connection.execute("BEGIN")
        try:
            for table in tables:
                rows = [
                    dict(row)
                    for row in self.connection.execute(
                        f"SELECT * FROM {table} ORDER BY {ordering[table]}"
                    )
                ]
                export[table] = rows
        except Exception:
            self.connection.execute("ROLLBACK")
            raise
        else:
            self.connection.execute("COMMIT")
        return export

    def state_sha256(self) -> str:
        evidence = self.canonical_export()
        evidence.pop("runs", None)
        evidence.pop("run_episodes", None)
        evidence["state_events"] = [
            row
            for row in evidence["state_events"]
            if row["event_type"] not in {"run_started", "run_ended"}
        ]
        for sequence, row in enumerate(evidence["state_events"], start=1):
            row["sequence"] = sequence
        return hashlib.sha256(canonical_json(evidence).encode("utf-8")).hexdigest()

    def status(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "breaker": self.breaker(),
            "positions": self.positions(),
            "open_orders": [dict(row) for row in self.open_orders()],
            "state_sha256": self.state_sha256(),
        }


def _round_cash(numerator: int) -> int:
    return int(
        (Decimal(numerator) / Decimal(1_000_000_000)).quantize(
            Decimal("1"), rounding=ROUND_HALF_EVEN
        )
    )


def _fill_identity(fill: ShadowFill) -> dict[str, Any]:
    return {
        "fill_id": fill.fill_id,
        "client_order_id": fill.client_order_id,
        "market_id": fill.market_id,
        "side": fill.side.value,
        "quantity_micros": fill.quantity_micros,
        "price_nanos": fill.price_nanos,
        "source_event_id": fill.source_event_id,
        "filled_at": utc_text(fill.filled_at),
        "fee_cash_micros": fill.fee_cash_micros,
    }


def _fill_payload(fill: ShadowFill, application_sequence: int) -> dict[str, Any]:
    return {**_fill_identity(fill), "application_sequence": application_sequence}


def _apply_accounting(
    prior: Mapping[str, Any] | None, fill: ShadowFill
) -> tuple[int, int, int, int, int]:
    """Apply signed open/add/reduce/close/reversal accounting deterministically."""

    old_quantity = int(prior["quantity_micros"]) if prior else 0
    old_average = int(prior["avg_entry_price_nanos"]) if prior else 0
    realized = int(prior["realized_pnl_cash_micros"]) if prior else 0
    fees = int(prior["fees_cash_micros"]) if prior else 0
    delta = fill.quantity_micros * fill.side.sign
    new_quantity = old_quantity + delta

    if old_quantity == 0 or (old_quantity > 0) == (delta > 0):
        total = abs(old_quantity) + abs(delta)
        average = (abs(old_quantity) * old_average + abs(delta) * fill.price_nanos) // total
    else:
        closed = min(abs(old_quantity), abs(delta))
        realized += _round_cash(
            closed * (fill.price_nanos - old_average) * (1 if old_quantity > 0 else -1)
        )
        if new_quantity == 0:
            average = 0
        elif (new_quantity > 0) == (old_quantity > 0):
            average = old_average
        else:
            average = fill.price_nanos

    fees += fill.fee_cash_micros
    realized -= fill.fee_cash_micros
    return new_quantity, average, realized, fees, fill.price_nanos
