"""
R1 Tool Calling Evaluation - Argument Normalization

Normalizes tool call arguments before comparison.
"""
from __future__ import annotations

import re
from ipaddress import ip_address, IPv4Address, IPv6Address
from typing import Any, Dict, List, Optional, Tuple, Union


def normalize_ip(value: Any) -> Optional[str]:
    """
    Normalize IP addresses to canonical form.

    Rules:
    - Strip leading zeros (001.002.003.004 -> 1.2.3.4)
    - Convert to lowercase for IPv6
    - Return None if invalid
    """
    if not isinstance(value, str):
        return None

    try:
        # First try direct parse
        ip = ip_address(value.strip())
        return str(ip)
    except ValueError:
        # Try with leading zeros stripped manually
        try:
            parts = value.strip().split(".")
            if len(parts) == 4:
                # Strip leading zeros from each octet
                normalized = ".".join(str(int(p)) for p in parts)
                ip = ip_address(normalized)
                return str(ip)
        except (ValueError, TypeError):
            pass
        return None


def normalize_domain(value: Any) -> Optional[str]:
    """
    Normalize domain names.

    Rules:
    - Lowercase
    - Strip trailing dot
    - Strip protocol prefix if present (https://, http://)
    - Keep path if present
    """
    if not isinstance(value, str):
        return None

    domain = value.strip()

    # Strip protocol (before lowercasing to handle mixed case)
    for proto in ("https://", "http://"):
        if domain.lower().startswith(proto):
            domain = domain[len(proto):]
            break

    domain = domain.lower()

    # Strip trailing dot
    if domain.endswith("."):
        domain = domain[:-1]

    # Strip path/query if present (just domain normalization)
    for char in "/?#":
        if char in domain:
            domain = domain.split(char)[0]

    # Basic validation - no spaces and reasonable length
    if not domain or " " in domain or len(domain) > 253:
        return None

    return domain


def normalize_hash(value: Any) -> Optional[str]:
    """
    Normalize file hashes.

    Rules:
    - Lowercase hex
    - Strip whitespace
    - Validate hex format
    """
    if not isinstance(value, str):
        return None

    hash_val = value.strip().lower()

    # Validate: must be hex only (a-f0-9)
    if not re.match(r"^[a-f0-9]+$", hash_val):
        return None

    length = len(hash_val)
    if length not in (32, 40, 64):  # MD5, SHA1, SHA256
        return None

    return hash_val


def normalize_url(value: Any) -> Optional[str]:
    """
    Normalize URLs.

    Rules:
    - Lowercase scheme (http, https)
    - Strip credentials if present
    - Keep host lowercase
    """
    if not isinstance(value, str):
        return None

    url = value.strip()

    # Basic validation
    if not url.startswith(("http://", "https://")):
        return None

    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)

        # Reconstruct with lowercase scheme
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()

        # Strip credentials if present
        if "@" in netloc:
            netloc = netloc.split("@", 1)[1]

        normalized = f"{scheme}://{netloc}{parsed.path}"
        if parsed.query:
            normalized += f"?{parsed.query}"

        return normalized
    except Exception:
        return None


def normalize_hostname(value: Any) -> Optional[str]:
    """
    Normalize hostnames.

    Rules:
    - Uppercase to lowercase
    - Strip whitespace
    - Keep dots and hyphens
    """
    if not isinstance(value, str):
        return None

    hostname = value.strip().lower()

    # Basic validation - alphanumeric, dots, hyphens, underscores
    if not re.match(r"^[a-z0-9.\-_]+$", hostname):
        return None

    return hostname


def normalize_indicator(value: Any, indicator_type: str) -> Tuple[Optional[str], str]:
    """
    Normalize an indicator value based on its type.

    Returns:
        (normalized_value, normalized_type) or (None, type) if invalid
    """
    if not isinstance(value, str):
        return None, indicator_type

    # Detect type if not provided
    if not indicator_type or indicator_type == "unknown":
        indicator_type = detect_indicator_type(value)

    value = value.strip()

    if indicator_type == "ipv4":
        normalized = normalize_ip(value)
        if normalized:
            return normalized, "ipv4"

    elif indicator_type == "domain":
        normalized = normalize_domain(value)
        if normalized:
            return normalized, "domain"

    elif indicator_type == "hash":
        normalized = normalize_hash(value)
        if normalized:
            # Detect specific hash type
            length = len(normalized)
            hash_type = {32: "md5", 40: "sha1", 64: "sha256"}.get(length, "hash")
            return normalized, hash_type

    elif indicator_type == "url":
        normalized = normalize_url(value)
        if normalized:
            return normalized, "url"

    elif indicator_type == "hostname":
        normalized = normalize_hostname(value)
        if normalized:
            return normalized, "hostname"

    # Return original if no normalization applicable
    return value, indicator_type


def detect_indicator_type(value: str) -> str:
    """
    Auto-detect indicator type from value format.
    """
    if not value or not isinstance(value, str):
        return "unknown"

    value = value.strip()

    # IPv4
    if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", value):
        try:
            ip_address(value)
            return "ipv4"
        except ValueError:
            pass

    # URL
    if value.startswith(("http://", "https://")):
        return "url"

    # Hash
    if re.match(r"^[a-fA-F0-9]{32,64}$", value):
        return "hash"

    # Domain-like
    if re.match(r"^[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?)+$", value):
        return "domain"

    # Hostname (no dots, alphanumeric + dash/underscore)
    if re.match(r"^[a-zA-Z0-9][a-zA-Z0-9\-_]*$", value):
        return "hostname"

    return "unknown"


def normalize_time_range(time_range: Any) -> Optional[Dict[str, str]]:
    """
    Normalize time range to UTC ISO format.
    """
    if not isinstance(time_range, dict):
        return None

    result = {}

    for key in ("start", "end"):
        value = time_range.get(key)
        if not value:
            continue

        if isinstance(value, str):
            result[key] = value.strip()

    if "start" not in result and "end" not in result:
        return None

    return result


def normalize_arguments(
    tool: str,
    arguments: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Normalize all arguments for a tool call.

    Returns normalized arguments dict.
    """
    normalized = {}

    for key, value in arguments.items():
        if value is None:
            continue

        if key == "indicator":
            norm_value, norm_type = normalize_indicator(value, arguments.get("indicator_type"))
            normalized[key] = norm_value
            # Also normalize indicator_type if present
            if "indicator_type" in arguments:
                normalized["indicator_type"] = norm_type

        elif key == "indicator_type":
            if isinstance(value, str) and value in ("ipv4", "domain", "hash", "url", "hostname"):
                normalized[key] = value

        elif key == "host":
            normalized[key] = normalize_hostname(value)

        elif key == "time_range":
            norm_tr = normalize_time_range(value)
            if norm_tr:
                normalized[key] = norm_tr

        elif key == "domain":
            normalized[key] = normalize_domain(value)

        elif key == "hash":
            normalized[key] = normalize_hash(value)

        elif key == "url":
            normalized[key] = normalize_url(value)

        else:
            # Pass through unknown arguments as-is
            normalized[key] = value

    return normalized


def compare_values(expected: Any, predicted: Any, is_critical: bool = False) -> bool:
    """
    Compare two values for equality after normalization.

    For critical arguments, must be exact match.
    For non-critical, some tolerance may be allowed.
    """
    # Handle None
    if expected is None and predicted is None:
        return True
    if expected is None or predicted is None:
        return False

    # Direct comparison for simple types
    if isinstance(expected, (str, int, float, bool)):
        if expected == predicted:
            return True

    # Normalize and compare strings
    if isinstance(expected, str) and isinstance(predicted, str):
        exp_stripped = expected.strip()
        pred_stripped = predicted.strip()

        # Try IP
        norm_exp = normalize_ip(exp_stripped)
        norm_pred = normalize_ip(pred_stripped)
        if norm_exp is not None and norm_pred is not None:
            return norm_exp == norm_pred

        # Try domain
        norm_exp = normalize_domain(exp_stripped)
        norm_pred = normalize_domain(pred_stripped)
        if norm_exp is not None and norm_pred is not None:
            return norm_exp == norm_pred

        # Try hash (case insensitive)
        if re.match(r"^[a-f0-9]{32,64}$", exp_stripped.lower()) and re.match(r"^[a-f0-9]{32,64}$", pred_stripped.lower()):
            return exp_stripped.lower() == pred_stripped.lower()

        # Direct lowercase comparison
        return exp_stripped.lower() == pred_stripped.lower()

    # Lists - order insensitive comparison
    if isinstance(expected, list) and isinstance(predicted, list):
        if len(expected) != len(predicted):
            return False
        return set(str(e).lower() for e in expected) == set(str(p).lower() for p in predicted)

    return expected == predicted
