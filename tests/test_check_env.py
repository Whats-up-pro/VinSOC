from __future__ import annotations

import pytest

from scripts.check_env import check_env, resolve_openai_key


@pytest.mark.parametrize(
    ("process_value", "dotenv_value", "expected_source", "expected_key"),
    [
        (None, "dotenv-secret", "dotenv", "dotenv-secret"),
        ("process-secret", None, "process_environment", "process-secret"),
        ("same-secret", "same-secret", "both_same", "same-secret"),
        (None, None, "missing", None),
        ("process-secret", "dotenv-secret", "conflicting_key_sources", None),
    ],
)
def test_resolve_openai_key_reports_only_source_label(
    process_value, dotenv_value, expected_source, expected_key
):
    process_env = {} if process_value is None else {"OPENAI_API_KEY": process_value}
    dotenv_env = {} if dotenv_value is None else {"OPENAI_API_KEY": dotenv_value}

    resolution = resolve_openai_key(process_env, dotenv_env)

    assert resolution.source == expected_source
    assert resolution.key == expected_key


def test_check_env_rejects_conflicting_sources_without_exposing_values(capsys):
    process_secret = "PROCESS_SECRET_MUST_NOT_LEAK"
    dotenv_secret = "DOTENV_SECRET_MUST_NOT_LEAK"

    result = check_env(
        process_env={"OPENAI_API_KEY": process_secret},
        dotenv_env={"OPENAI_API_KEY": dotenv_secret},
    )

    output = capsys.readouterr().out
    assert result == 1
    assert "OPENAI_API_KEY source: conflicting_key_sources" in output
    assert process_secret not in output
    assert dotenv_secret not in output
    assert "prefix" not in output.lower()
    assert "fingerprint" not in output.lower()
