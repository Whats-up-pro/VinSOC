"""
Endpoint Investigation Skill

Analyzes endpoint telemetry for suspicious process relationships:
- Parent-child process chains
- LOLBin usage patterns
- Suspicious spawning relationships

This skill is read-only. It queries logs but does not modify anything.
"""
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set

from skills.base import BaseSkill, SkillContract, SkillResult


class EndpointSkill(BaseSkill):
    """
    Endpoint investigation skill for analyzing process relationships.
    """

    skill_name = "endpoint_investigation"
    skill_version = "1.0.0"

    # Suspicious process relationship patterns
    SUSPICIOUS_PATTERNS = [
        # Parent -> Child patterns
        {"parent": "winword.exe", "child": "powershell.exe", "reason": "Office spawning PowerShell", "technique": "T1059.001"},
        {"parent": "winword.exe", "child": "cmd.exe", "reason": "Office spawning CMD", "technique": "T1059.003"},
        {"parent": "excel.exe", "child": "powershell.exe", "reason": "Excel spawning PowerShell", "technique": "T1059.001"},
        {"parent": "excel.exe", "child": "cmd.exe", "reason": "Excel spawning CMD", "technique": "T1059.003"},
        {"parent": "outlook.exe", "child": "powershell.exe", "reason": "Email client spawning PowerShell", "technique": "T1059.001"},
        {"parent": "outlook.exe", "child": "cmd.exe", "reason": "Email client spawning CMD", "technique": "T1059.003"},
        {"parent": "chrome.exe", "child": "powershell.exe", "reason": "Browser spawning PowerShell", "technique": "T1059.001"},
        {"parent": "firefox.exe", "child": "powershell.exe", "reason": "Browser spawning PowerShell", "technique": "T1059.001"},
        {"parent": "msedge.exe", "child": "powershell.exe", "reason": "Browser spawning PowerShell", "technique": "T1059.001"},
        {"parent": "powershell.exe", "child": "cmd.exe", "reason": "PowerShell spawning CMD", "technique": "T1059.003"},
        {"parent": "powershell.exe", "child": "certutil.exe", "reason": "PowerShell using certutil (LOLBin)", "technique": "T1105"},
        {"parent": "powershell.exe", "child": "bitsadmin.exe", "reason": "PowerShell using bitsadmin (LOLBin)", "technique": "T1105"},
        {"parent": "powershell.exe", "child": "curl.exe", "reason": "PowerShell using curl (LOLBin)", "technique": "T1105"},
        {"parent": "powershell.exe", "child": "wget.exe", "reason": "PowerShell using wget (LOLBin)", "technique": "T1105"},
        {"parent": "cmd.exe", "child": "powershell.exe", "reason": "CMD spawning PowerShell", "technique": "T1059.001"},
        {"parent": "cmd.exe", "child": "certutil.exe", "reason": "CMD using certutil (LOLBin)", "technique": "T1105"},
        {"parent": "rundll32.exe", "child": "cmd.exe", "reason": "Rundll32 spawning CMD", "technique": "T1059.003"},
        {"parent": "rundll32.exe", "child": "powershell.exe", "reason": "Rundll32 spawning PowerShell", "technique": "T1059.001"},
        {"parent": "mshta.exe", "child": "powershell.exe", "reason": "Mshta spawning PowerShell", "technique": "T1059.001"},
        {"parent": "mshta.exe", "child": "cmd.exe", "reason": "Mshta spawning CMD", "technique": "T1059.003"},
        {"parent": "wscript.exe", "child": "powershell.exe", "reason": "WScript spawning PowerShell", "technique": "T1059.001"},
        {"parent": "cscript.exe", "child": "powershell.exe", "reason": "CScript spawning PowerShell", "technique": "T1059.001"},
        {"parent": "regsvr32.exe", "child": "powershell.exe", "reason": "Regsvr32 spawning PowerShell (Squiblydoo)", "technique": "T1218.010"},
        {"parent": "svchost.exe", "child": "cmd.exe", "reason": "Svchost spawning CMD (unusual)", "technique": "T1059.003"},
        {"parent": "services.exe", "child": "cmd.exe", "reason": "Services spawning CMD", "technique": "T1059.003"},
        {"parent": "services.exe", "child": "powershell.exe", "reason": "Services spawning PowerShell", "technique": "T1059.001"},
        {"parent": "svchost.exe", "child": "wmiex.exe", "reason": "Svchost spawning WMI (possible lateral movement)", "technique": "T1047"},
        {"parent": "wmiex.exe", "child": "cmd.exe", "reason": "WMI spawning CMD (possible lateral movement)", "technique": "T1047"},
        {"parent": "winrar.exe", "child": "cmd.exe", "reason": "Archive tool spawning CMD", "technique": "T1059.003"},
        {"parent": "winrar.exe", "child": "firefox.exe", "reason": "Archive tool interacting with browser", "technique": "T1560"},
        # Ransomware precursors
        {"parent": "cmd.exe", "child": "vssadmin.exe", "reason": "Volume shadow copy deletion (ransomware precursor)", "technique": "T1490"},
        {"parent": "cmd.exe", "child": "bcdedit.exe", "reason": "Boot configuration modification", "technique": "T1562.001"},
        # Reconnaissance
        {"parent": "cmd.exe", "child": "whoami.exe", "reason": "Reconnaissance command", "technique": "T1033"},
        {"parent": "cmd.exe", "child": "net.exe", "reason": "Reconnaissance command", "technique": "T1016"},
    ]

    # LOLBin detection
    LOLBIN_COMMANDS = {
        "certutil.exe", "bitsadmin.exe", "curl.exe", "wget.exe",
        "powershell.exe", "cmd.exe", "mshta.exe", "regsvr32.exe",
        "rundll32.exe", "wscript.exe", "cscript.exe"
    }

    def __init__(self, mock_data: Optional[Dict[str, Any]] = None):
        """
        Initialize Endpoint skill.

        Args:
            mock_data: Optional dict for testing.
        """
        super().__init__()
        self.mock_data = mock_data or {}

    def validate_input(self, **kwargs) -> tuple[bool, Optional[str]]:
        """Validate endpoint investigation parameters."""
        if "host" not in kwargs:
            return False, "Missing required parameter: host"

        host = kwargs["host"]
        if not isinstance(host, str) or len(host) == 0:
            return False, "host must be a non-empty string"

        # Optional time range validation
        if "time_range" in kwargs:
            time_range = kwargs["time_range"]
            if not isinstance(time_range, dict):
                return False, "time_range must be a dict with start and end"
            if "start" not in time_range or "end" not in time_range:
                return False, "time_range must have start and end"

        return True, None

    def _execute(self, **kwargs) -> SkillResult:
        """
        Execute endpoint investigation.

        Args:
            host: The hostname/identifier to investigate
            time_range: Optional dict with start/end timestamps

        Returns:
            SkillResult with process analysis
        """
        host = kwargs.get("host")
        time_range = kwargs.get("time_range")
        evidence_id = f"ep_{uuid.uuid4().hex[:8]}"

        # Check mock data
        if self.mock_data:
            mock_result = self.mock_data.get(host, self.mock_data.get("*", {}))
            if mock_result:
                return self._build_result_from_mock(host, mock_result, time_range, evidence_id)

        # Default empty result
        return self._build_empty_result(host, time_range, evidence_id)

    def _build_result_from_mock(
        self,
        host: str,
        mock_data: Dict[str, Any],
        time_range: Optional[Dict[str, Any]],
        evidence_id: str
    ) -> SkillResult:
        """Build result from mock data."""
        process_tree = mock_data.get("process_tree", [])
        observed_evidence = mock_data.get("observed_evidence", [])

        # Detect suspicious relationships
        suspicious = self._detect_suspicious_relationships(process_tree)

        return SkillResult(
            success=True,
            data={
                "host": host,
                "query_time_range": time_range or self._default_time_range(),
                "process_tree": process_tree,
                "suspicious_relationships": suspicious,
                "observed_evidence": observed_evidence or [
                    {"type": "process_count", "value": len(process_tree), "context": "Process relationships analyzed"}
                ]
            },
            evidence_ids=[evidence_id]
        )

    def _build_empty_result(
        self,
        host: str,
        time_range: Optional[Dict[str, Any]],
        evidence_id: str
    ) -> SkillResult:
        """Build empty result when no data available."""
        return SkillResult(
            success=True,
            data={
                "host": host,
                "query_time_range": time_range or self._default_time_range(),
                "process_tree": [],
                "suspicious_relationships": [],
                "observed_evidence": [
                    {"type": "lookup_status", "value": "no_data", "context": "No endpoint telemetry found for this host"}
                ]
            },
            evidence_ids=[evidence_id]
        )

    def _default_time_range(self) -> Dict[str, str]:
        """Generate default time range (last 24 hours)."""
        now = datetime.utcnow()
        return {
            "start": (now - timedelta(hours=24)).isoformat(),
            "end": now.isoformat()
        }

    def _detect_suspicious_relationships(
        self,
        process_tree: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Detect suspicious process relationships."""
        suspicious = []

        # Build lookup for quick matching
        process_map: Dict[str, Set[str]] = {}
        for rel in process_tree:
            parent = rel.get("parent", "").lower()
            child = rel.get("child", "").lower()
            if parent not in process_map:
                process_map[parent] = set()
            process_map[parent].add(child)

        # Check each relationship against patterns
        for rel in process_tree:
            parent = rel.get("parent", "").lower()
            child = rel.get("child", "").lower()

            for pattern in self.SUSPICIOUS_PATTERNS:
                if pattern["parent"].lower() == parent and pattern["child"].lower() == child:
                    suspicious.append({
                        "parent": rel.get("parent"),
                        "child": rel.get("child"),
                        "suspicious": True,
                        "suspicious_reasons": [pattern["reason"]],
                        "mitre_technique": pattern["technique"]
                    })
                    break

        # Additional heuristic: suspicious if parent is common app and child is LOLBin
        for rel in process_tree:
            parent = rel.get("parent", "").lower()
            child = rel.get("child", "").lower()

            # Skip if already flagged
            already_flagged = any(
                s["parent"].lower() == parent and s["child"].lower() == child
                for s in suspicious
            )
            if already_flagged:
                continue

            # Heuristic: common apps shouldn't spawn LOLBins directly
            common_apps = {"winword.exe", "excel.exe", "powerpnt.exe", "outlook.exe",
                         "chrome.exe", "firefox.exe", "msedge.exe"}
            if parent in common_apps and child in self.LOLBIN_COMMANDS:
                suspicious.append({
                    "parent": rel.get("parent"),
                    "child": rel.get("child"),
                    "suspicious": True,
                    "suspicious_reasons": [f"Common application spawning system tool (LOLBin)"],
                    "mitre_technique": "T1059"
                })

            # Heuristic: scripted download/execution chains
            if parent == "powershell.exe" and child in {"rundll32.exe", "mshta.exe"}:
                suspicious.append({
                    "parent": rel.get("parent"),
                    "child": rel.get("child"),
                    "suspicious": True,
                    "suspicious_reasons": ["Script interpreter spawning execution proxy binary"],
                    "mitre_technique": "T1218",
                })

            # Heuristic: known ransomware executable launch
            if "lockbit" in child or "ransom" in child:
                suspicious.append({
                    "parent": rel.get("parent"),
                    "child": rel.get("child"),
                    "suspicious": True,
                    "suspicious_reasons": ["Potential ransomware execution chain"],
                    "mitre_technique": "T1486",
                })

        return suspicious

    def validate_output(self, data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Validate endpoint output against schema."""
        from skills.validators import validate_endpoint_result
        return validate_endpoint_result(data)

    def get_contract(self) -> SkillContract:
        """Return endpoint skill contract."""
        return SkillContract(
            skill_name=self.skill_name,
            version=self.skill_version,
            required_inputs=["host"],
            output_schema="EndpointResult",
            lifecycle_stage="investigate",
            read_only=True,
        )


# Convenience function
def investigate_endpoint(
    host: str,
    time_range: Optional[Dict[str, str]] = None,
    mock_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Investigate endpoint telemetry for a host.

    Args:
        host: The hostname/identifier to investigate
        time_range: Optional dict with start/end timestamps
        mock_data: Optional mock data for testing

    Returns:
        Dict with endpoint analysis
    """
    skill = EndpointSkill(mock_data=mock_data)
    result = skill.execute(host=host, time_range=time_range)

    if not result.success:
        raise ValueError(result.error)

    return result.data
