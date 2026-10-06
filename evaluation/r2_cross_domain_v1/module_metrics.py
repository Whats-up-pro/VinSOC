"""Reference annotations explain errors; they never change end-to-end EX.

Empty/empty item sets have NA precision/recall/F1 and exact set success. One
reference alternative is selected by joint typed-item F1 (stable first tie),
then used for every metric. Annotation matching is diagnostic, not a proof of
SQL equivalence. Provenance precision needs a verified DB context.
"""
import json

import duckdb

from .data import _quote
from .tools import witness_id


POLICY = {"version": "module_metrics_v2", "empty_set": "NA_rates_exact_set_success",
          "alternative": "max_joint_item_f1_stable_first", "coverage": "stage_present_over_all_cases",
          "numeric_constraints_are_stored_values": False,
          "predicate_scope": "Typed literal/operator mappings; Boolean structure and semantic equivalence are separate execution diagnostics"}


def _key(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _items(link, reference=False):
    values = link.get("stored_values" if reference else "grounded_values", [])
    supporting = {item.get('evidence_id') for item in link.get('constraints', []) if item.get('kind') == 'domain_predicate'}
    stored = [{"table": value.get("table"), "column": value.get("column"), "operator": value.get("operator", "="),
               "value": value.get("value")} for value in values if reference or value.get('evidence_id') not in supporting]
    constraints = [{key: value for key, value in constraint.items() if key not in ("evidence_id", "value_type")}
                   for constraint in link.get("constraints", [])]
    return {"tables": {_key(value) for value in link.get("tables", [])},
            "columns": {_key(value) for value in link.get("columns", [])},
            "relationships": {_key(value) for value in link.get("relationships", [])},
            "predicates": {_key(value) for value in stored + constraints}}


def item_metric(predicted, required):
    correct, npred, nref = len(predicted & required), len(predicted), len(required)
    precision, recall = correct / npred if npred else None, correct / nref if nref else None
    f1 = 2 * correct / (npred+nref) if npred+nref else None
    return {"correct": correct, "predicted": npred, "required": nref,
            "precision": precision, "recall": recall, "f1": f1}


def _joint(items):
    return {(kind, value) for kind, values in items.items() for value in values}


def _witness_precision(values, trajectory, context):
    catalog = {table["name"]: {column["name"]: column["duckdb_type"] for column in table["columns"]}
               for table in context.identity["schema"]}
    issued = {value.get("evidence_id"): value for event in trajectory if event.get("tool") == "value_search"
              for value in event.get("result", {}).get("matches", []) + event.get("result", {}).get("domain_witnesses", [])}
    correct = 0
    with duckdb.connect(str(context.snapshot_path), read_only=True, config={"enable_external_access": False, "threads": 1}) as connection:
        for value in values:
            witness = issued.get(value.get("evidence_id"))
            if not witness or any(value.get(key) != witness.get(key) for key in ("table", "column", "value")):
                continue
            table, column = witness.get("table"), witness.get("column")
            if (witness.get("database_id") != context.database_id
                or witness.get("snapshot_identity") != context.identity["logical_sha256"]
                or witness.get("type") != catalog.get(table, {}).get(column)
                or witness.get("evidence_id") != witness_id(witness)):
                continue
            # A self-consistent hash is not proof that the value exists. Verify
            # stored VARCHAR values, with bound parameters, on the actual DB.
            if witness["type"] != "VARCHAR" or not isinstance(witness.get("value"), str):
                continue
            row = connection.execute(f"SELECT 1 FROM {_quote(table)} WHERE {_quote(column)}=? LIMIT 1", [witness["value"]]).fetchone()
            correct += int(row is not None)
    return {"correct": correct, "total": len(values), "precision": correct / len(values) if values else None}


def score_modules(reference_case, record, context=None):
    link = record.get("linked_schema")
    result = {"policy": POLICY, "selected_alternative": None, "schema_linker": None, "value_grounding": None}
    if not isinstance(link, dict):
        return result
    predicted = _items(link)
    alternatives = [_items(alternative, reference=True) for alternative in reference_case.accepted_links]
    if not alternatives:
        raise ValueError("REFERENCE_ALTERNATIVES_MISSING")
    index = max(range(len(alternatives)), key=lambda i: item_metric(_joint(predicted), _joint(alternatives[i]))["f1"] or 0)
    required = alternatives[index]
    result["selected_alternative"] = index
    schema = {kind: item_metric(predicted[kind], required[kind]) for kind in ("tables", "columns", "relationships")}
    permitted = {_key(value) for value in (context.identity["relationships"] if context is not None else reference_case.accepted_links[index].get("relationships", []))}
    schema.update({"case_success": all(predicted[kind] == required[kind] for kind in ("tables", "columns", "relationships")),
                   "valid_relationship_path": predicted["relationships"] <= permitted})
    witness = _witness_precision(link.get("grounded_values", []), record.get("trajectory", []), context) if context is not None else None
    result.update({"schema_linker": schema, "value_grounding": {
        "predicates": item_metric(predicted["predicates"], required["predicates"]),
        "case_success": predicted["predicates"] == required["predicates"], "witness_precision": witness,
        "provenance_status": "VERIFIED_CONTEXT" if context is not None else "CONTEXT_UNAVAILABLE",
        "unsupported_literal_rate": {"unsupported": witness["total"]-witness["correct"], "total": witness["total"],
                                     "rate": 1-witness["precision"] if witness["precision"] is not None else None} if witness is not None else None}})
    return result


def aggregate_module_metrics(records):
    result = {}
    for stage in ("schema_linker", "value_grounding"):
        available = [record[stage] for record in records if record.get(stage) is not None]
        result[stage] = {"coverage": {"available": len(available), "total": len(records)},
                         "case_success": {"correct": sum(item["case_success"] for item in available), "total": len(available)}}
        kinds = ("tables", "columns", "relationships") if stage == "schema_linker" else ("predicates",)
        for kind in kinds:
            counts = {key: sum(item[kind][key] for item in available) for key in ("correct", "predicted", "required")}
            correct, npred, nref = counts.values()
            result[stage][kind] = {**counts, "precision": correct/npred if npred else None,
                                  "recall": correct/nref if nref else None, "f1": 2*correct/(npred+nref) if npred+nref else None}
    return result
