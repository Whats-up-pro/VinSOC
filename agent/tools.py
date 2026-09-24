"""
Tool Definitions for Investigation Agent

Defines the three investigation skills as callable tools
with their input/output schemas for LLM function calling.
"""
from typing import Any, Dict, List
from dataclasses import dataclass
from enum import Enum


class ToolName(Enum):
    """Available investigation tools."""
    CTI_ENRICHMENT = "cti_enrichment"
    NETWORK_INVESTIGATION = "network_investigation"
    ENDPOINT_INVESTIGATION = "endpoint_investigation"


@dataclass
class InvestigationTool:
    """Definition of an investigation tool for LLM use."""
    name: str
    description: str
    input_schema: Dict[str, Any]
    output_schema_description: str


def sanitize_tool_arguments_for_execution(
    tool_name: str,
    arguments: Dict[str, Any],
) -> Dict[str, Any]:
    """Restore omitted-field semantics for nullable strict-schema arguments."""
    del tool_name
    return {key: value for key, value in arguments.items() if value is not None}


def get_tool_schemas() -> List[Dict[str, Any]]:
    """
    Get tool schemas for LLM function calling.

    These schemas define the interface contract between the agent
    and the investigation skills.
    """
    return [
        {
            "type": "function",
            "function": {
                "name": "cti_enrichment",
                "strict": True,
                "description": """Enrich an Indicator of Compromise (IOC) with Cyber Threat Intelligence.

Use this tool to get threat intelligence about:
- IPv4 addresses
- Domain names
- File hashes (MD5, SHA1, SHA256)

The tool returns:
- Reputation (benign/suspicious/malicious/unknown)
- Related threat actors (if known)
- Related malware families (if known)
- MITRE ATT&CK techniques
- Source attribution

Note: Do not call this tool for endpoint hostname or process context.""",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "indicator": {
                            "type": "string",
                            "description": "The IOC value to investigate (IP, domain, or hash)"
                        },
                        "indicator_type": {
                            "type": ["string", "null"],
                            "enum": ["ipv4", "domain", "hash", "url", None],
                            "description": "The type of IOC. Auto-detected if not provided."
                        }
                    },
                    "required": ["indicator", "indicator_type"],
                    "additionalProperties": False
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "network_investigation",
                "strict": True,
                "description": """Investigate flow telemetry for an IPv4 address.

Use this tool to analyze:
- Connection frequency and patterns
- Unique destinations and ports contacted
- Failed vs successful connection ratios
- Periodicity candidates (beaconing patterns)
- Scan candidates (port scanning patterns)
- Transfer metrics (large data transfers)
- Service fanout (admin service reachability)

This tool analyzes IP-based network logs and IDS/firewall telemetry.
Domain-only lookup is unavailable with current flow telemetry; obtain a
concrete IPv4 address before calling this tool.
When a frozen DuckDB snapshot is configured, the tool uses its internal,
read-only domain query layer. Do not send SQL in this tool call.""",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "indicator": {
                            "type": "string",
                            "description": "IPv4 address to investigate; domain-only lookup is unavailable",
                            "pattern": "^[0-9]{1,3}(\\.[0-9]{1,3}){3}$"
                        },
                        "indicator_type": {
                            "type": ["string", "null"],
                            "enum": ["ipv4", None],
                            "description": "IPv4 or null for automatic IPv4 validation; domains are unsupported."
                        },
                        "time_range": {
                            "type": ["object", "null"],
                            "properties": {
                                "start": {"type": "string", "description": "Start time in ISO8601 format"},
                                "end": {"type": "string", "description": "End time in ISO8601 format"}
                            },
                            "required": ["start", "end"],
                            "additionalProperties": False,
                            "description": "Optional time range for the investigation. Defaults to last 24 hours."
                        }
                    },
                    "required": ["indicator", "indicator_type", "time_range"],
                    "additionalProperties": False
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "endpoint_investigation",
                "strict": True,
                "description": """Investigate endpoint telemetry for suspicious process relationships.

Use this tool to analyze:
- Parent-child process chains
- Suspicious application spawning (e.g., Word spawning PowerShell)
- LOLBin usage patterns
- MITRE ATT&CK technique indicators

This tool analyzes endpoint detection and response (EDR) data.
When a frozen DuckDB snapshot is configured, the tool uses its internal,
read-only domain query layer. Do not send SQL in this tool call.
Call this when process relationships are relevant to the investigation.""",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "host": {
                            "type": "string",
                            "description": "The hostname or identifier of the endpoint to investigate"
                        },
                        "time_range": {
                            "type": ["object", "null"],
                            "properties": {
                                "start": {"type": "string", "description": "Start time in ISO8601 format"},
                                "end": {"type": "string", "description": "End time in ISO8601 format"}
                            },
                            "required": ["start", "end"],
                            "additionalProperties": False,
                            "description": "Optional time range for the investigation. Defaults to last 24 hours."
                        }
                    },
                    "required": ["host", "time_range"],
                    "additionalProperties": False
                }
            }
        }
    ]


def get_tool_definitions() -> Dict[str, InvestigationTool]:
    """Get tool definitions as structured objects."""
    schemas = get_tool_schemas()
    tools = {}

    for schema in schemas:
        func = schema["function"]
        tools[func["name"]] = InvestigationTool(
            name=func["name"],
            description=func["description"],
            input_schema=func["parameters"],
            output_schema_description=f"Returns a JSON object with analysis results for {func['name']}"
        )

    return tools
