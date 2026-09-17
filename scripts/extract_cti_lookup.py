#!/usr/bin/env python3
"""
Extract CTI lookup table from ThreatFox CSV data.

Converts ThreatFox IOC dump into a JSON lookup table for CTI skill.
"""
import json
import pandas as pd
from pathlib import Path


def map_confidence(level: int) -> str:
    """Map ThreatFox confidence (0-100) to CTI confidence levels."""
    if pd.isna(level):
        return "low"
    if level < 34:
        return "low"
    elif level < 67:
        return "medium"
    else:
        return "high"


def map_ioc_type(ioc_type: str) -> str:
    """Map ThreatFox ioc_type to CTI indicator_type."""
    mapping = {
        "ip:port": "ipv4",      # Treat ip:port as ipv4 type
        "ipv4": "ipv4",
        "ipv6": "ipv6",
        "domain": "domain",
        "url": "url",
        "md5_hash": "hash",
        "sha1_hash": "hash",
        "sha256_hash": "hash",
    }
    return mapping.get(ioc_type, "unknown")


def extract_ip_from_ioc(ioc_value: str, ioc_type: str) -> str:
    """
    Extract base IP from IOC value for lookup.

    For ip:port format, return just the IP part.
    For URLs, return the full URL (will be normalized later).
    """
    if ioc_type == "ip:port" and ":" in ioc_value:
        # Extract IP part (before the port)
        return ioc_value.rsplit(":", 1)[0]
    return ioc_value


def extract_cti_lookup(
    csv_path: str = "data/threatfox_clean.csv",
    output_path: str = "data/cti_lookup.json",
) -> dict:
    """
    Extract CTI lookup table from ThreatFox CSV.

    Args:
        csv_path: Path to cleaned ThreatFox CSV
        output_path: Path to output JSON file

    Returns:
        Dict mapping IOC values to CTI data
    """
    print(f"Reading {csv_path}...")
    df = pd.read_csv(csv_path, comment="#", skip_blank_lines=True)

    print(f"Processing {len(df):,} IOCs...")

    cti_lookup = {}

    for _, row in df.iterrows():
        ioc_value = str(row["ioc_value"]).strip()
        ioc_type = str(row["ioc_type"]).strip()

        # Extract lookup key (IP without port for ip:port type)
        lookup_key = extract_ip_from_ioc(ioc_value, ioc_type)

        # Extract relevant data
        entry = {
            "indicator": lookup_key,
            "indicator_type": map_ioc_type(ioc_type),
            "original_ioc": ioc_value,  # Original with port if applicable
            "reputation": "malicious",  # All ThreatFox IOCs are malicious
            "confidence": map_confidence(row.get("confidence_level")),
            "threat_type": str(row.get("threat_type", "")).strip() or None,
            "related_malware": [
                str(row.get("malware_printable", "")).strip()
            ]
            if pd.notna(row.get("malware_printable"))
            else [],
            "related_actors": [],
            "mitre_techniques": [],
            "sources": [
                {
                    "name": "ThreatFox",
                    "last_updated": str(row.get("last_seen_utc", "")).strip(),
                    "reference": str(row.get("reference", "")).strip()
                    if pd.notna(row.get("reference"))
                    else None,
                }
            ],
            "observed_evidence": [
                {"type": "threatfox_ioc_id", "value": str(row.get("ioc_id", "")), "context": "ThreatFox IOC identifier"},
                {"type": "tags", "value": str(row.get("tags", "")), "context": "ThreatFox tags"},
            ],
            # Raw fields for debugging
            "_raw": {
                "ioc_id": str(row.get("ioc_id", "")),
                "ioc_type": ioc_type,
                "first_seen": str(row.get("first_seen_utc", "")),
                "last_seen": str(row.get("last_seen_utc", "")),
                "confidence_level": int(row.get("confidence_level", 0)) if pd.notna(row.get("confidence_level")) else 0,
                "malware_alias": str(row.get("malware_alias", "")),
                "reporter": str(row.get("reporter", "")),
            },
        }

        # Remove None values from sources
        entry["sources"] = [s for s in entry["sources"] if s.get("reference")]

        cti_lookup[lookup_key] = entry

    print(f"Built lookup for {len(cti_lookup):,} unique IOCs")

    # Save to JSON
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    print(f"Writing {output_path}...")
    with open(output, "w", encoding="utf-8") as f:
        json.dump(cti_lookup, f, indent=2, ensure_ascii=False)

    size_mb = output.stat().st_size / (1024 * 1024)
    print(f"Saved {size_mb:.2f} MB to {output_path}")

    # Print statistics
    print("\nStatistics:")
    print(f"  Total IOCs: {len(cti_lookup):,}")

    type_counts = {}
    for entry in cti_lookup.values():
        t = entry["indicator_type"]
        type_counts[t] = type_counts.get(t, 0) + 1
    print("  By type:")
    for t, count in sorted(type_counts.items()):
        print(f"    {t}: {count:,}")

    return cti_lookup


def create_sample_set(cti_lookup: dict, output_path: str = "data/threatfox_samples.json", n: int = 100):
    """Create a small sample set for quick testing."""
    import random

    samples = random.sample(list(cti_lookup.items()), min(n, len(cti_lookup)))
    sample_dict = dict(samples)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(sample_dict, f, indent=2)

    print(f"\nCreated sample set with {len(sample_dict)} IOCs at {output_path}")
    return sample_dict


if __name__ == "__main__":
    import sys

    csv_path = sys.argv[1] if len(sys.argv) > 1 else "data/threatfox_clean.csv"
    output_path = sys.argv[2] if len(sys.argv) > 2 else "data/cti_lookup.json"

    cti_lookup = extract_cti_lookup(csv_path, output_path)

    # Create sample set for quick testing
    create_sample_set(cti_lookup, n=50)
