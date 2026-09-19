"""
CTI Enrichment Skill

Enriches Indicators of Compromise (IOCs) with threat intelligence:
- IPv4 addresses
- Domain names
- File hashes (MD5, SHA1, SHA256)

This skill is read-only. It queries CTI sources but does not modify anything.

Data Sources:
- ThreatFox IOC feed (default): data/cti_lookup.json
- Mock data for testing
- External CTI APIs (future)
"""
import json
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from skills.base import BaseSkill, SkillContract, SkillResult

logger = logging.getLogger(__name__)


class CTISkill(BaseSkill):
    """
    Cyber Threat Intelligence enrichment skill.

    Takes an IOC and returns reputation, related actors, malware, and MITRE ATT&CK mappings.
    """

    skill_name = "cti_enrichment"
    skill_version = "1.1.0"  # Updated to 1.1.0 for ThreatFox support

    def __init__(
        self,
        mock_data: Optional[Dict[str, Any]] = None,
        threatfox_path: Optional[str] = None,
        threatfox_data: Optional[Dict[str, Any]] = None,
        auto_load_threatfox: bool = True,
    ):
        """
        Initialize CTI skill.

        Args:
            mock_data: Optional dict for testing. If provided, used as CTI lookup source.
            threatfox_path: Optional path to ThreatFox JSON lookup file.
                           If not provided and auto_load_threatfox is True,
                           defaults to data/cti_lookup.json if it exists.
            threatfox_data: Optional pre-loaded ThreatFox data dict.
                           Takes precedence over threatfox_path if both provided.
            auto_load_threatfox: If True, auto-load from default path if no source
                                is explicitly configured. Set to False for testing.
        """
        super().__init__()
        # Empty dict {} is treated as "no source configured", not empty source
        self.mock_data = mock_data if mock_data not in (None, {}) else {}
        self._mock_source_configured = mock_data not in (None, {})

        # Track if user explicitly passed mock_data (even if empty)
        self._user_provided_mock_data = mock_data is not None

        # ThreatFox data loading
        self.threatfox_data: Dict[str, Any] = {}
        self._threatfox_source_configured = False
        if threatfox_data is not None:
            if isinstance(threatfox_data, dict) and all(
                isinstance(record, dict) for record in threatfox_data.values()
            ):
                self.threatfox_data = threatfox_data
                self._threatfox_source_configured = True
                logger.info(f"Loaded {len(self.threatfox_data):,} IOCs from provided ThreatFox data")
            else:
                logger.error("Provided ThreatFox data must be a mapping")
        elif threatfox_path is not None:
            self._load_threatfox(threatfox_path)
        elif auto_load_threatfox and not self._user_provided_mock_data:
            # Only auto-load from default path if:
            # 1. auto_load_threatfox is True AND
            # 2. user did NOT explicitly provide mock_data
            # This prevents silent data loading when user passes mock_data={}
            default_path = Path("data/cti_lookup.json")
            if default_path.exists():
                self._load_threatfox(str(default_path))

    def _load_threatfox(self, path: str) -> None:
        """Load ThreatFox IOC data from JSON file."""
        logger.info(f"Loading ThreatFox data from {path}...")
        try:
            with open(path, "r", encoding="utf-8") as f:
                loaded_data = json.load(f)
            if not isinstance(loaded_data, dict) or not all(
                isinstance(record, dict) for record in loaded_data.values()
            ):
                logger.error("ThreatFox JSON data must map IOCs to mappings")
                self.threatfox_data = {}
                self._threatfox_source_configured = False
                return
            self.threatfox_data = loaded_data
            self._threatfox_source_configured = True
            logger.info(f"Loaded {len(self.threatfox_data):,} IOCs from ThreatFox")
        except FileNotFoundError:
            logger.warning(f"ThreatFox file not found: {path}")
            self.threatfox_data = {}
            self._threatfox_source_configured = False
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse ThreatFox JSON: {e}")
            self.threatfox_data = {}
            self._threatfox_source_configured = False
        except UnicodeDecodeError as e:
            logger.error(f"Failed to decode ThreatFox JSON: {e}")
            self.threatfox_data = {}
            self._threatfox_source_configured = False
        except OSError as e:
            logger.error(f"Failed to read ThreatFox JSON: {e}")
            self.threatfox_data = {}
            self._threatfox_source_configured = False

    def _lookup_threatfox(self, indicator: str) -> Optional[Dict[str, Any]]:
        """
        Look up IOC in ThreatFox data.

        Args:
            indicator: The IOC to look up

        Returns:
            ThreatFox entry if found, None otherwise
        """
        # Direct match
        if indicator in self.threatfox_data:
            return self.threatfox_data[indicator]

        # For URLs, also try without protocol
        if indicator.startswith(("http://", "https://")):
            stripped = indicator.split("://", 1)[1]
            if stripped in self.threatfox_data:
                return self.threatfox_data[stripped]

        # For ip:port format, also try just the IP
        if ":ip:port" in indicator or "." in indicator:
            parts = indicator.replace("ip:port://", "").rsplit(":", 1)
            if len(parts) == 2 and parts[1].isdigit():
                ip_part = parts[0]
                if ip_part in self.threatfox_data:
                    return self.threatfox_data[ip_part]

        return None

    def validate_input(self, **kwargs) -> tuple[bool, Optional[str]]:
        """Validate IOC input parameters."""
        if "indicator" not in kwargs:
            return False, "Missing required parameter: indicator"

        indicator = kwargs["indicator"]
        if not isinstance(indicator, str):
            return False, "Indicator must be a string"
        # Use provided type or auto-detect (don't use None explicitly provided)
        provided_type = kwargs.get("indicator_type")
        indicator_type = provided_type if provided_type else self._detect_indicator_type(indicator)

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
        # Use provided type or auto-detect
        provided_type = kwargs.get("indicator_type")
        indicator_type = provided_type if provided_type else self._detect_indicator_type(indicator)

        # Priority: mock_data > threatfox_data > error
        if self._mock_source_configured:
            return self._build_result_from_mock(indicator, indicator_type)

        # Check ThreatFox data
        if self._threatfox_source_configured:
            return self._build_result_from_threatfox(indicator, indicator_type)

        # No data source configured
        return SkillResult(
            success=False,
            error="No CTI data source configured. Use mock_data or threatfox_path parameter."
        )

    def _build_result_from_threatfox(
        self, indicator: str, indicator_type: str
    ) -> SkillResult:
        """
        Build CTI result from ThreatFox data.

        Args:
            indicator: The IOC value
            indicator_type: The IOC type

        Returns:
            SkillResult with CTI data from ThreatFox
        """
        evidence_id = f"cti_{uuid.uuid4().hex[:8]}"

        # Look up in ThreatFox
        threatfox_entry = self._lookup_threatfox(indicator)

        if not threatfox_entry:
            # Not found in ThreatFox - return unknown
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
                        {
                            "type": "lookup_status",
                            "value": "not_found",
                            "context": "IOC not found in ThreatFox database",
                        }
                    ],
                },
                evidence_ids=[evidence_id],
            )

        # Return data from ThreatFox
        return SkillResult(
            success=True,
            data={
                "indicator": indicator,
                "indicator_type": indicator_type,
                "reputation": threatfox_entry.get("reputation", "malicious"),
                "confidence": threatfox_entry.get("confidence", "high"),
                "related_actors": threatfox_entry.get("related_actors", []),
                "related_malware": threatfox_entry.get("related_malware", []),
                "mitre_techniques": threatfox_entry.get("mitre_techniques", []),
                "sources": threatfox_entry.get("sources", []),
                "observed_evidence": threatfox_entry.get("observed_evidence", []),
            },
            evidence_ids=[evidence_id],
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

        # Return data from mock
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

    def validate_output(self, data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Validate CTI output against schema."""
        from skills.validators import validate_cti_result
        return validate_cti_result(data)

    def get_contract(self) -> SkillContract:
        """Return CTI skill contract."""
        return SkillContract(
            skill_name=self.skill_name,
            version=self.skill_version,
            required_inputs=["indicator"],
            output_schema="CTIResult",
            lifecycle_stage="investigate",
            read_only=True,
        )


# Convenience functions for direct skill execution
def check_ip_reputation(
    indicator: str,
    indicator_type: Optional[str] = None,
    mock_data: Optional[Dict[str, Any]] = None,
    threatfox_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Check reputation of an indicator.

    Args:
        indicator: The IOC to check
        indicator_type: Optional type (auto-detected if not provided)
        mock_data: Optional mock data for testing
        threatfox_path: Optional path to ThreatFox JSON file

    Returns:
        Dict with CTI result
    """
    skill = CTISkill(mock_data=mock_data, threatfox_path=threatfox_path)
    result = skill.execute(indicator=indicator, indicator_type=indicator_type)

    if not result.success:
        raise ValueError(result.error)

    return result.data


def check_domain_reputation(
    domain: str,
    mock_data: Optional[Dict[str, Any]] = None,
    threatfox_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Check reputation of a domain."""
    return check_ip_reputation(
        indicator=domain,
        indicator_type="domain",
        mock_data=mock_data,
        threatfox_path=threatfox_path,
    )


def check_hash_reputation(
    hash_val: str,
    mock_data: Optional[Dict[str, Any]] = None,
    threatfox_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Check reputation of a file hash."""
    return check_ip_reputation(
        indicator=hash_val,
        indicator_type="hash",
        mock_data=mock_data,
        threatfox_path=threatfox_path,
    )
