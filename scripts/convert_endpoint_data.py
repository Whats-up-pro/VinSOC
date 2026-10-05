"""
Convert synthetic endpoint data to DuckDB schema for VinSOC endpoint skill.
"""
import json
import hashlib
import os
import sys
from datetime import datetime, timezone

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import duckdb

from vinsoc_data.duckdb_store import SocSnapshotBuilder


def load_synthetic_data(json_path: str = "data/endpoint_synthetic.json") -> dict:
    """Load synthetic endpoint data from JSON."""
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def create_combined_snapshot(
    network_parquet: str = "data/full.parquet",
    endpoint_json: str = "data/endpoint_synthetic.json",
    output_path: str = "data/combined_sinsoc.duckdb",
):
    """
    Create a combined DuckDB snapshot with both network flows and endpoint telemetry.
    Uses SocSnapshotBuilder for proper schema and provenance.
    """
    endpoint_data = load_synthetic_data(endpoint_json)
    events = endpoint_data["process_events"]

    # Create snapshot with proper schema
    builder = SocSnapshotBuilder(output_path)
    builder.create_empty_snapshot()

    # Register synthetic data provenance
    builder.register_provenance(
        dataset_id="synthetic_endpoint_v1",
        source_name="Synthetic Endpoint Data (VinSOC Test)",
        source_url="internal://synthetic_generation",
        retrieved_at=datetime.now(timezone.utc).isoformat(),
        file_sha256=hashlib.sha256(json.dumps(endpoint_data, sort_keys=True).encode()).hexdigest(),
        license_note="Synthetic data for testing - no external source",
    )

    # Insert endpoint data (insert_rows already validates source_dataset matches)
    # Note: insert_rows expects source_dataset in each row already
    endpoint_rows = []
    for event in events:
        endpoint_rows.append({
            "source_dataset": "synthetic_endpoint_v1",  # Must match registered dataset
            "source_row_id": str(event["source_row_id"]),
            "event_time": datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00")),
            "host": event["host"],
            "event_id": event["event_id"],
            "parent_image": event["parent_image"],
            "parent_pid": event["parent_pid"],
            "image": event["image"],
            "process_id": event["child_pid"],
            "command_line": event["command_line"],
        })

    inserted = builder.insert_rows(
        "sysmon_process_events",
        endpoint_rows,
        source_dataset="synthetic_endpoint_v1",
    )
    print(f"Inserted {inserted} endpoint events")

    # Attach network data if available
    if os.path.exists(network_parquet):
        conn = duckdb.connect(output_path)
        try:
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS network_flows AS
                SELECT * FROM read_parquet('{network_parquet}')
            """)
            network_count = conn.execute("SELECT COUNT(*) FROM network_flows").fetchone()[0]
            print(f"Network flows: {network_count}")
        except Exception as e:
            print(f"Note: Could not attach network data: {e}")
        finally:
            conn.close()

    return output_path


def create_simple_endpoint_snapshot(
    endpoint_json: str = "data/endpoint_synthetic.json",
    output_path: str = "data/endpoint_only.duckdb",
):
    """
    Create a simple endpoint-only DuckDB snapshot.
    Uses the same schema as DuckDBEndpointRepository expects.
    """
    endpoint_data = load_synthetic_data(endpoint_json)
    events = endpoint_data["process_events"]

    conn = duckdb.connect(output_path)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS sysmon_process_events (
            event_id INTEGER,
            event_time TIMESTAMP,
            host VARCHAR,
            parent_image VARCHAR,
            parent_pid INTEGER,
            image VARCHAR,
            process_id INTEGER,
            command_line VARCHAR,
            source_dataset VARCHAR,
            source_row_id BIGINT,
            suspicious BOOLEAN,
            technique VARCHAR,
            reason VARCHAR
        )
    """)

    for event in events:
        conn.execute(
            """
            INSERT INTO sysmon_process_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                event["event_id"],
                datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00")),
                event["host"],
                event["parent_image"],
                event["parent_pid"],
                event["image"],
                event["child_pid"],
                event["command_line"],
                event["source_dataset"],
                event["source_row_id"],
                event.get("suspicious", False),
                event.get("technique", None),
                event.get("reason", None),
            ],
        )

    count = conn.execute("SELECT COUNT(*) FROM sysmon_process_events").fetchone()[0]
    conn.close()
    return count


def verify_snapshot(path: str = "data/combined_sinsoc.duckdb"):
    """Verify the created snapshot."""
    conn = duckdb.connect(path)

    print("\n=== Snapshot Verification ===")

    print("\n--- Network Flows ---")
    try:
        result = conn.execute("SELECT COUNT(*) FROM network_flows").fetchone()
        print(f"Total flows: {result[0]}")
    except Exception as e:
        print(f"No network_flows table: {e}")

    print("\n--- Endpoint Events (Sysmon) ---")
    try:
        result = conn.execute("SELECT COUNT(*) FROM sysmon_process_events").fetchone()
        print(f"Total process events: {result[0]}")

        result = conn.execute("""
            SELECT MIN(event_time), MAX(event_time)
            FROM sysmon_process_events
        """).fetchone()
        print(f"Time range: {result[0]} to {result[1]}")

        print("\n--- Events by Host ---")
        result = conn.execute("""
            SELECT host, COUNT(*) as count
            FROM sysmon_process_events
            GROUP BY host
            ORDER BY count DESC
        """).fetchall()
        for row in result:
            print(f"  {row[0]}: {row[1]} events")
    except Exception as e:
        print(f"No sysmon_process_events table: {e}")

    conn.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Convert synthetic endpoint data to DuckDB")
    parser.add_argument("--data", default="data/endpoint_synthetic.json", help="Input JSON file")
    parser.add_argument("--output", default="data/combined_sinsoc.duckdb", help="Output DuckDB file")
    parser.add_argument("--network", default="data/full.parquet", help="Network flows parquet")
    parser.add_argument("--verify", action="store_true", help="Verify existing snapshot")
    parser.add_argument("--simple", action="store_true", help="Create simple endpoint-only snapshot")

    args = parser.parse_args()

    if args.verify:
        verify_snapshot(args.output)
    elif args.simple:
        count = create_simple_endpoint_snapshot(args.data, args.output)
        print(f"Created simple snapshot with {count} events")
        verify_snapshot(args.output)
    else:
        create_combined_snapshot(
            network_parquet=args.network,
            endpoint_json=args.data,
            output_path=args.output,
        )
        verify_snapshot(args.output)
