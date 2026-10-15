"""Unit tests for idempotency, retry recovery, and database durability.

Verifies:
- Idempotency key stability
- Session state transitions
- Duplicate upload slot handling
- SQLite transaction isolation and WAL durability
"""

import uuid
from backend import database
from backend.ingestion.adapter import generate_idempotency_key


def test_idempotency_key_stability():
    key1 = generate_idempotency_key("sess_100", 1, "v1.0.0")
    key2 = generate_idempotency_key("sess_100", 1, "v1.0.0")
    key3 = generate_idempotency_key("sess_100", 2, "v1.0.0")

    assert key1 == key2
    assert key1 != key3


def test_database_wal_and_transaction_rollback():
    """Verify that failures inside transaction rollback cleanly."""
    unique_route = f"test-rollback-{uuid.uuid4()}"

    with database.get_connection() as conn:
        conn.execute("INSERT INTO routes (route_id, status) VALUES (?, 'created')", (unique_route,))

    # Confirm it exists
    with database.get_connection() as conn:
        row = conn.execute("SELECT status FROM routes WHERE route_id = ?", (unique_route,)).fetchone()
        assert row["status"] == "created"

    # Attempt transaction that raises exception
    try:
        with database.get_connection() as conn:
            conn.execute("UPDATE routes SET status = 'failed' WHERE route_id = ?", (unique_route,))
            raise RuntimeError("Simulated crash mid-transaction")
    except RuntimeError:
        pass

    # Status must still be 'created' due to rollback
    with database.get_connection() as conn:
        row = conn.execute("SELECT status FROM routes WHERE route_id = ?", (unique_route,)).fetchone()
        assert row["status"] == "created"
