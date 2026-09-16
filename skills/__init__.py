"""
SOC Investigation Skills Package

This package contains the three investigation skills:
- CTI Enrichment
- Network Investigation
- Endpoint Investigation

All skills are read-only and return schema-validated results.
"""
from skills.base import BaseSkill, SkillContract, SkillResult
from skills.cti_skill import CTISkill, check_ip_reputation
from skills.network_skill import NetworkSkill, investigate_network
from skills.endpoint_skill import EndpointSkill, investigate_endpoint

__all__ = [
    "BaseSkill",
    "SkillResult",
    "SkillContract",
    "CTISkill",
    "check_ip_reputation",
    "NetworkSkill",
    "investigate_network",
    "EndpointSkill",
    "investigate_endpoint",
]
