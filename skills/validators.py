"""
Schema Validators

Validates skill outputs against JSON schemas.
"""
import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import jsonschema


class SchemaValidator:
    """Validates skill outputs against predefined JSON schemas."""

    def __init__(self, schema_dir: Optional[str] = None):
        """
        Initialize validator with schema directory.

        Args:
            schema_dir: Path to schemas directory. Defaults to ./schemas
        """
        if schema_dir is None:
            schema_dir = Path(__file__).parent.parent / "schemas"
        else:
            schema_dir = Path(schema_dir)

        self.schemas: Dict[str, Dict[str, Any]] = {}
        self._load_schemas(schema_dir)

    def _load_schemas(self, schema_dir: Path) -> None:
        """Load all JSON schemas from directory."""
        if not schema_dir.exists():
            return

        for schema_file in schema_dir.glob("*.json"):
            try:
                with open(schema_file) as f:
                    schema = json.load(f)
                    title = schema.get("title", schema_file.stem)
                    self.schemas[title] = schema
            except Exception as e:
                print(f"Warning: Could not load schema {schema_file}: {e}")

    def validate(
        self,
        data: Dict[str, Any],
        schema_name: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate data against a schema.

        Args:
            data: Data to validate
            schema_name: Name of schema (e.g., "CTIResult")

        Returns:
            tuple: (is_valid, error_message)
        """
        if schema_name not in self.schemas:
            return False, f"Unknown schema: {schema_name}"

        schema = self.schemas[schema_name]

        try:
            jsonschema.validate(instance=data, schema=schema)
            return True, None
        except jsonschema.ValidationError as e:
            return False, str(e)
        except jsonschema.SchemaError as e:
            return False, f"Schema error: {e}"

    def validate_cti_result(self, data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate CTIResult schema."""
        return self.validate(data, "CTIResult")

    def validate_network_result(self, data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate NetworkResult schema."""
        return self.validate(data, "NetworkResult")

    def validate_endpoint_result(self, data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate EndpointResult schema."""
        return self.validate(data, "EndpointResult")

    def validate_investigation_case(self, data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate InvestigationCase schema."""
        return self.validate(data, "InvestigationCase")


# Singleton instance
_validator: Optional[SchemaValidator] = None


def get_validator() -> SchemaValidator:
    """Get singleton validator instance."""
    global _validator
    if _validator is None:
        _validator = SchemaValidator()
    return _validator


def validate_cti_result(data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Validate CTI result data."""
    return get_validator().validate_cti_result(data)


def validate_network_result(data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Validate Network result data."""
    return get_validator().validate_network_result(data)


def validate_endpoint_result(data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Validate Endpoint result data."""
    return get_validator().validate_endpoint_result(data)


def validate_investigation_case(data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Validate InvestigationCase data."""
    return get_validator().validate_investigation_case(data)
