from jsonschema.validators import Draft202012Validator

from agent.tools import get_tool_schemas


def _assert_strict_object(schema):
    schema_type = schema["type"]
    assert schema_type == "object" or (
        isinstance(schema_type, list) and "object" in schema_type
    )
    assert schema["additionalProperties"] is False
    assert set(schema.get("properties", {})) == set(schema.get("required", []))

    for property_schema in schema.get("properties", {}).values():
        property_type = property_schema.get("type")
        if property_type == "object" or (
            isinstance(property_type, list) and "object" in property_type
        ):
            _assert_strict_object(property_schema)


def test_production_tool_schemas_are_strict_compatible():
    schemas = get_tool_schemas()

    for tool in schemas:
        function = tool["function"]
        parameters = function["parameters"]

        assert function["strict"] is True
        Draft202012Validator.check_schema(parameters)
        _assert_strict_object(parameters)


def test_optional_business_fields_are_required_but_nullable():
    schemas = {
        tool["function"]["name"]: tool["function"]["parameters"]
        for tool in get_tool_schemas()
    }

    cti = schemas["cti_enrichment"]["properties"]
    assert cti["indicator"]["type"] == "string"
    assert cti["indicator_type"]["type"] == ["string", "null"]
    assert None in cti["indicator_type"]["enum"]

    network = schemas["network_investigation"]["properties"]
    assert network["indicator"]["type"] == "string"
    assert network["indicator_type"]["type"] == ["string", "null"]
    assert None in network["indicator_type"]["enum"]
    assert network["time_range"]["type"] == ["object", "null"]

    endpoint = schemas["endpoint_investigation"]["properties"]
    assert endpoint["host"]["type"] == "string"
    assert endpoint["time_range"]["type"] == ["object", "null"]

    for properties in (network, endpoint):
        time_range = properties["time_range"]
        assert time_range["required"] == ["start", "end"]
        assert time_range["properties"]["start"]["type"] == "string"
        assert time_range["properties"]["end"]["type"] == "string"
