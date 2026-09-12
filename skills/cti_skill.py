"""
CTI Enrichment Skill

Enriches Indicators of Compromise (IOCs) with threat intelligence:
- IPv4 addresses
- Domain names
- File hashes (MD5, SHA1, SHA256)

This skill is read-only. It queries CTI sources but does not modify anything.
"""
import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from skills.base import BaseSkill, SkillResult


class CTISkill(BaseSkill):
    """
    Cyber Threat Intelligence enrichment skill.

    Takes an IOC and returns reputation, related actors, malware, and MITRE ATT&CK mappings.
    """

    skill_name = "cti_enrichment"
    skill_version = "1.0.0"

    def __init__(self, mock_data: Optional[Dict[str, Any]] = None):
        """
        Initialize CTI skill.

        Args:
            mock_data: Optional dict for testing. If provided, used instead of real CTI lookup.
        """
        super().__init__()
        self.mock_data = mock_data or {}

    def validate_input(self, **kwargs) -> tuple[bool, Optional[str]]:
        """Validate IOC input parameters."""
        if "indicator" not in kwargs:
            return False, "Missing required parameter: indicator"

        indicator = kwargs["indicator"]
        indicator_type = kwargs.get("indicator_type", self._detect_indicator_type(indicator))

        # Validate IOC type
        valid_types = ["ipv4", "domain", "hash", "url"]
        if indicator_type not in valid_types:
            return False, f"Invalid indicator_type: {indicator_type}. Must be one of {valid_types}"

        # Validate IOC format
        if indicator_type == "ipv4" and not self._is_valid_ipv4(indicator):
            return False, f"Invalid IPv4 format: {indicator}"

        if indicator_type == "domain" and not self._is_valid_domain(indicator):
            return False, f"Invalid domain format: {indicator}"

        if indicator_type == "hash":
            if not self._is_valid_hash(indicator):
                return False, f"Invalid hash format: {indicator}"

        if indicator_type == "url" and not self._is_valid_url(indicator):
            return False, f"Invalid URL format: {indicator}"

        return True, None

    def _detect_indicator_type(self, indicator: str) -> str:
        """Detect IOC type from format."""
        if self._is_valid_ipv4(indicator):
            return "ipv4"
        if self._is_valid_domain(indicator):
            return "domain"
        if self._is_valid_hash(indicator):
            return "hash"
        if self._is_valid_url(indicator):
            return "url"
        return "unknown"

    def _is_valid_ipv4(self, ip: str) -> bool:
        """Validate IPv4 address format."""
        pattern = r"^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$"
        return bool(re.match(pattern, ip))

    def _is_valid_domain(self, domain: str) -> bool:
        """Validate domain name format."""
        pattern = r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$"
        return bool(re.match(pattern, domain))

    def _is_valid_hash(self, hash_val: str) -> bool:
        """Validate hash format (MD5, SHA1, SHA256)."""
        patterns = {
            "md5": r"^[a-fA-F0-9]{32}$",
            "sha1": r"^[a-fA-F0-9]{40}$",
            "sha256": r"^[a-fA-F0-9]{64}$",
        }
        return any(re.match(p, hash_val) for p in patterns.values())

    def _is_valid_url(self, url: str) -> bool:
        """Validate URL format."""
        pattern = r"^https?://[^\s/$.?#].[^\s]*$"
        return bool(re.match(pattern, url))

    def _execute(self, **kwargs) -> SkillResult:
        """
        Execute CTI enrichment.

        Args:
            indicator: The IOC to enrich
            indicator_type: Optional type override (auto-detected if not provided)

        Returns:
            SkillResult with CTI data
        """
        indicator = kwargs["indicator"]
        indicator_type = kwargs.get("indicator_type") or self._detect_indicator_type(indicator)

        # Check mock data first
        if self.mock_data:
            return self._build_result_from_mock(indicator, indicator_type)

        # In production, this would call external CTI APIs
        # For MVP, we use the mock data approach
        return SkillResult(
            success=False,
            error="No CTI data source configured. Use mock_data parameter for testing."
        )

    def _build_result_from_mock(self, indicator: str, indicator_type: str) -> SkillResult:
        """Build result from mock data."""
        evidence_id = f"cti_{uuid.uuid4().hex[:8]}"

        # Get mock data for this indicator
        mock_result = self.mock_data.get(indicator, self.mock_data.get("*", {}))

        if not mock_result:
            # Default unknown result
            return SkillResult(
                success=True,
                data={
                    "indicator": indicator,
                    "indicator_type": indicator_type,
                    "reputation": "unknown",
                    "confidence": "low",
                    "related_actors": [],
                    "related_malware": [],
                    "mitre_techniques": [],
                    "sources": [],
                    "observed_evidence": [
                        {"type": "lookup_status", "value": "not_found", "context": "No CTI data available for this indicator"}
                    ]
                },
                evidence_ids=[evidence_id]
            )

        return SkillResult(
            success=True,
            data={
                "indicator": indicator,
                "indicator_type": indicator_type,
                "reputation": mock_result.get("reputation", "unknown"),
                "confidence": mock_result.get("confidence", "low"),
                "related_actors": mock_result.get("related_actors", []),
                "related_malware": mock_result.get("related_malware", []),
                "mitre_techniques": mock_result.get("mitre_techniques", []),
                "sources": mock_result.get("sources", []),
                "observed_evidence": mock_result.get("observed_evidence", [])
            },
            evidence_ids=[evidence_id]
        )


# Convenience function for direct skill execution
def check_ip_reputation(
    indicator: str,
    indicator_type: Optional[str] = None,
    mock_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Check reputation of an indicator.

    Args:
        indicator: The IOC to check
        indicator_type: Optional type (auto-detected if not provided)
        mock_data: Optional mock data for testing

    Returns:
        Dict with CTI result
    """
    skill = CTISkill(mock_data=mock_data)
    result = skill.execute(indicator=indicator, indicator_type=indicator_type)

    if not result.success:
        raise ValueError(result.error)

    return result.data


def check_domain_reputation(
    domain: str,
    mock_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Check reputation of a domain."""
    return check_ip_reputation(
        indicator=domain,
        indicator_type="domain",
        mock_data=mock_data
    )


def check_hash_reputation(
    hash_val: str,
    mock_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Check reputation of a file hash."""
    return check_ip_reputation(
        indicator=hash_val,
        indicator_type="hash",
        mock_data=mock_data
    )
