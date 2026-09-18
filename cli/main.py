#!/usr/bin/env python3
"""
SOC Investigation CLI

Command-line interface for conducting AI-assisted SOC investigations.
"""
import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.orchestrator import InvestigationOrchestrator
from agent.hitl import (
    HumanDecision,
    ScriptedHumanReviewGate,
    TRIAGE_CLOSE,
    TRIAGE_CONTINUE,
    REVIEW_APPROVE,
    REVIEW_REQUEST_MORE_EVIDENCE,
    REVIEW_ESCALATE,
    REVIEW_REJECT,
)
from agent.provider import (
    DEFAULT_OPENROUTER_FREE_MODEL,
    LLMProvider,
    MockProvider,
    create_provider,
)
from skills.cti_skill import CTISkill
from skills.endpoint_skill import EndpointSkill
from skills.network_skill import NetworkSkill

console = Console()


class ConsoleHumanReviewGate:
    """Interactive analyst checkpoints for direct CLI investigations."""

    def _choice(self, prompt: str, allowed):
        allowed_upper = {item.upper(): item for item in allowed}
        while True:
            value = console.input(prompt).strip().upper()
            if value in allowed_upper:
                return allowed_upper[value]
            console.print(f"[yellow]Choose one of: {', '.join(allowed)}[/yellow]")

    def review_triage(self, indicator, indicator_type, context, triage):
        console.print("\n[bold yellow]Human Review Gate — Benign Triage[/bold yellow]")
        console.print(f"Indicator: {indicator} ({indicator_type})")
        console.print(f"Machine recommendation: {triage.verdict} / confidence={triage.confidence}")
        decision = self._choice(
            "Decision [CLOSE/CONTINUE]: ",
            [TRIAGE_CLOSE, TRIAGE_CONTINUE],
        )
        rationale = console.input("Rationale (optional): ").strip()
        return HumanDecision(decision=decision, rationale=rationale, analyst="cli-analyst")

    def review_final(self, case):
        console.print("\n[bold yellow]Human Review Gate — Final Assessment[/bold yellow]")
        console.print(f"Risk: {case.risk_level} | Confidence: {case.confidence}")
        console.print(f"Assessment: {case.final_assessment[:600]}")
        decision = self._choice(
            "Decision [APPROVE/REQUEST_MORE_EVIDENCE/ESCALATE/REJECT]: ",
            [REVIEW_APPROVE, REVIEW_REQUEST_MORE_EVIDENCE, REVIEW_ESCALATE, REVIEW_REJECT],
        )
        rationale = console.input("Rationale (optional): ").strip()
        feedback = ""
        if decision == REVIEW_REQUEST_MORE_EVIDENCE:
            feedback = console.input("What additional evidence should the agent collect? ").strip()
        return HumanDecision(
            decision=decision,
            rationale=rationale,
            feedback=feedback,
            analyst="cli-analyst",
        )


def load_scenario(scenario_path: str) -> Dict[str, Any]:
    """Load a scenario from JSON file."""
    path = Path(scenario_path)
    if not path.exists():
        # Try relative to scenarios directory
        path = Path(__file__).parent.parent / "scenarios" / scenario_path

    if not path.exists():
        raise FileNotFoundError(f"Scenario not found: {scenario_path}")

    with open(path) as f:
        return json.load(f)


def load_scenario_test_data(scenario: Dict[str, Any]) -> Dict[str, Any]:
    """Extract test data from scenario for skills."""
    test_data = scenario.get("test_data", {})
    indicator = scenario.get("initial_indicator", {}).get("value")
    cti_response = test_data.get("cti_response")
    network_response = test_data.get("network_data")
    endpoint_response = test_data.get("endpoint_data")
    endpoint_host = endpoint_response.get("host") if endpoint_response else None
    return {
        "cti_mock_data": {indicator: cti_response} if indicator and cti_response else {},
        "network_mock_data": {indicator: network_response} if indicator and network_response else {},
        "endpoint_mock_data": {endpoint_host: endpoint_response} if endpoint_host and endpoint_response else {},
    }


def run_investigation(
    indicator: str,
    indicator_type: str,
    context: Optional[str] = None,
    provider: str = "mock",
    model: str = "gpt-4o",
    api_key: Optional[str] = None,
    test_data: Optional[Dict[str, Any]] = None,
    fallback_model: Optional[str] = DEFAULT_OPENROUTER_FREE_MODEL,
    run_mode: str = "evaluation",
    monthly_budget_usd: Optional[float] = None,
    budget_ledger_path: str = ".vinsoc/openai_budget.json",
    duckdb_snapshot_path: Optional[str] = None,
    human_review_gate=None,
) -> Dict[str, Any]:
    """Run an investigation and return results."""
    # Create LLM provider
    llm_provider: LLMProvider
    if provider == "mock":
        llm_provider = MockProvider(model="test")
        # Add mock responses
        llm_provider.add_response("CTI", "I'll enrich this indicator with threat intelligence.")
        llm_provider.add_response("benign", "The indicator appears benign. Let me check if further investigation is needed.")
        llm_provider.add_response("malicious", "This indicator is malicious. I should investigate further with network and endpoint tools.")
    else:
        provider_options: Dict[str, Any] = {}
        if provider == "routed":
            provider_options = {
                "fallback_model": fallback_model,
                "mode": run_mode,
                "monthly_budget_usd": monthly_budget_usd,
                "budget_ledger_path": budget_ledger_path,
                "free_only": True,
            }
        llm_provider = create_provider(provider, model, api_key, **provider_options)

    # Create orchestrator
    orchestrator = InvestigationOrchestrator(
        provider=llm_provider,
        cti_mock_data=test_data.get("cti_mock_data") if test_data else None,
        network_mock_data=test_data.get("network_mock_data") if test_data else None,
        endpoint_mock_data=test_data.get("endpoint_mock_data") if test_data else None,
        duckdb_snapshot_path=duckdb_snapshot_path,
        human_review_gate=human_review_gate,
    )

    # Run investigation
    case = orchestrator.investigate(
        indicator=indicator,
        indicator_type=indicator_type,
        context=context
    )

    return case.to_dict()


def display_case(case: Dict[str, Any]):
    """Display investigation case in rich format."""
    # Header
    console.print(Panel.fit(
        f"[bold cyan]Investigation Case:[/bold cyan] {case['case_id']}",
        border_style="cyan"
    ))

    # Initial indicator
    indicator = case.get("initial_indicator", {})
    console.print(f"\n[bold]Initial Indicator:[/bold] {indicator.get('value')} ({indicator.get('type', 'unknown')})")
    if indicator.get('context'):
        console.print(f"[bold]Context:[/bold] {indicator['context']}")

    # Tool trace
    console.print("\n[bold cyan]Investigation Timeline[/bold cyan]")
    tool_trace = case.get("tool_trace", [])
    if tool_trace:
        table = Table(show_header=True, header_style="bold")
        table.add_column("Tool", style="cyan")
        table.add_column("Arguments", style="green")
        table.add_column("Summary", style="yellow")

        for tc in tool_trace:
            args_str = json.dumps(tc.get("arguments", {}))[:50]
            table.add_row(
                tc.get("tool", ""),
                f"{args_str}..." if len(args_str) >= 50 else args_str,
                tc.get("result_summary", "")
            )
        console.print(table)
    else:
        console.print("[yellow]No tools called[/yellow]")

    # Evidence summary
    console.print("\n[bold cyan]Evidence Collected[/bold cyan]")
    evidence = case.get("evidence", [])
    console.print(f"[green]Total evidence items:[/green] {len(evidence)}")

    # Show evidence from each tool
    for tool in ["cti_enrichment", "network_investigation", "endpoint_investigation"]:
        tool_evidence = [e for e in evidence if e.get("source_tool") == tool]
        if tool_evidence:
            console.print(f"  [cyan]{tool}:[/cyan] {len(tool_evidence)} items")

    # Hypotheses
    console.print("\n[bold cyan]Hypotheses[/bold cyan]")
    hypotheses = case.get("hypotheses", [])
    for h in hypotheses:
        conf_color = {"LOW": "yellow", "MEDIUM": "blue", "HIGH": "red"}.get(h.get("confidence", "LOW"), "white")
        console.print(f"  [{conf_color}]{h.get('confidence')}[/{conf_color}] {h.get('description')}")

    # Final assessment
    console.print("\n[bold cyan]Final Assessment[/bold cyan]")
    console.print(f"[bold]Risk Level:[/bold] [red]{case.get('risk_level', 'UNKNOWN')}[/red]")
    console.print(f"[bold]Confidence:[/bold] {case.get('confidence', 'UNKNOWN')}")
    console.print(f"\n{case.get('final_assessment', 'No assessment provided.')[:500]}")

    # Limitations
    limitations = case.get("limitations", [])
    if limitations:
        console.print("\n[bold yellow]Limitations[/bold yellow]")
        for lim in limitations:
            console.print(f"  - {lim}")

    # Metadata
    metadata = case.get("metadata", {})
    if metadata:
        console.print(f"\n[dim]Investigation completed in {metadata.get('investigation_duration_seconds', 0):.2f}s[/dim]")


def run_scenario(
    scenario_path: str,
    provider: str = "mock",
    model: str = "gpt-4o",
    fallback_model: Optional[str] = DEFAULT_OPENROUTER_FREE_MODEL,
    run_mode: str = "evaluation",
    monthly_budget_usd: Optional[float] = None,
    budget_ledger_path: str = ".vinsoc/openai_budget.json",
):
    """Run a predefined scenario."""
    console.print(f"\n[cyan]Loading scenario:[/cyan] {scenario_path}")

    scenario = load_scenario(scenario_path)

    # Display scenario info
    console.print(f"[yellow]Category:[/yellow] {scenario.get('category', 'unknown')}")
    console.print(f"[yellow]Label:[/yellow] {scenario.get('label', 'unknown')}")

    ground_truth = scenario.get("ground_truth", {})
    console.print(f"[yellow]Expected verdict:[/yellow] {ground_truth.get('verdict', 'unknown')}")

    # Load test data
    test_data = load_scenario_test_data(scenario)

    # Get indicator
    indicator = scenario.get("initial_indicator", {})

    console.print("\n[cyan]Running investigation...[/cyan]\n")

    # Run investigation
    case = run_investigation(
        indicator=indicator.get("value"),
        indicator_type=indicator.get("type", "ipv4"),
        context=indicator.get("context"),
        provider=provider,
        model=model,
        test_data=test_data,
        fallback_model=fallback_model,
        run_mode=run_mode,
        monthly_budget_usd=monthly_budget_usd,
        budget_ledger_path=budget_ledger_path,
        human_review_gate=ScriptedHumanReviewGate(),
    )

    # Display results
    display_case(case)

    # Compare with ground truth
    console.print("\n[bold cyan]Ground Truth Comparison[/bold cyan]")
    expected_risk = ground_truth.get("expected_risk", "UNKNOWN")
    actual_risk = case.get("risk_level", "UNKNOWN")

    match = "✓" if expected_risk == actual_risk else "✗"
    console.print(f"[{'green' if expected_risk == actual_risk else 'red'}] {match}[/] Expected risk: {expected_risk}, Actual: {actual_risk}")


def run_direct_investigation(
    indicator: str,
    indicator_type: str,
    context: Optional[str],
    provider: str,
    model: str,
    api_key: Optional[str],
    fallback_model: Optional[str],
    run_mode: str,
    monthly_budget_usd: Optional[float],
    budget_ledger_path: str,
    duckdb_snapshot_path: Optional[str],
):
    """Run a direct investigation on an indicator."""
    console.print(f"\n[cyan]Investigating:[/cyan] {indicator} ({indicator_type})")
    if context:
        console.print(f"[cyan]Context:[/cyan] {context}")

    console.print(f"[cyan]Using provider:[/cyan] {provider}/{model}")
    console.print("\n[cyan]Running investigation...[/cyan]\n")

    case = run_investigation(
        indicator=indicator,
        indicator_type=indicator_type,
        context=context,
        provider=provider,
        model=model,
        api_key=api_key,
        fallback_model=fallback_model,
        run_mode=run_mode,
        monthly_budget_usd=monthly_budget_usd,
        budget_ledger_path=budget_ledger_path,
        duckdb_snapshot_path=duckdb_snapshot_path,
        human_review_gate=ConsoleHumanReviewGate(),
    )

    display_case(case)


def run_benchmark(limit: Optional[int] = None):
    """Compare fixed pipeline vs evidence-driven orchestration across scenarios."""
    from tests.benchmark_runner import run_benchmark_suite

    summary = run_benchmark_suite(limit=limit)
    console.print("\n[bold cyan]Benchmark Summary[/bold cyan]")
    console.print(f"Scenarios: {summary['scenarios']}")
    console.print(f"Evidence-driven match: {summary['evidence_driven_match_rate']:.2%}")
    console.print(f"Fixed pipeline match: {summary['fixed_pipeline_match_rate']:.2%}")
    console.print(f"Evidence-driven avg tools: {summary['evidence_driven_avg_tools']:.2f}")
    console.print(f"Fixed pipeline avg tools: {summary['fixed_pipeline_avg_tools']:.2f}")


def list_scenarios():
    """List available scenarios."""
    scenarios_dir = Path(__file__).parent.parent / "scenarios"

    if not scenarios_dir.exists():
        console.print("[red]No scenarios directory found[/red]")
        return

    scenarios = sorted(scenarios_dir.glob("case_*.json"))

    table = Table(title="Available Scenarios", show_header=True)
    table.add_column("Case ID", style="cyan")
    table.add_column("Category", style="yellow")
    table.add_column("Label", style="green")

    for scenario_file in scenarios:
        with open(scenario_file) as f:
            data = json.load(f)
            table.add_row(
                data.get("case_id", scenario_file.stem),
                data.get("category", "unknown"),
                data.get("label", "unknown")[:50]
            )

    console.print(table)
    console.print(f"\n[dim]Total: {len(scenarios)} scenarios[/dim]")


def test_skills():
    """Test individual skills."""
    console.print("\n[cyan]Testing CTI Skill[/cyan]")
    cti_skill = CTISkill(mock_data={
        "185.220.101.45": {"reputation": "malicious", "confidence": "high"}
    })
    result = cti_skill.execute(indicator="185.220.101.45")
    console.print(f"[green]Success:[/green] {result.success}")
    if result.data:
        console.print(f"[green]Reputation:[/green] {result.data.get('reputation')}")

    console.print("\n[cyan]Testing Network Skill[/cyan]")
    network_skill = NetworkSkill(mock_data={
        "10.0.0.25": {
            "connections": [
                {"timestamp": "2024-01-15T10:00:00Z", "dst": "10.0.1.1", "dst_port": 22, "protocol": "TCP", "action": "DROP", "bytes_out": 0},
                {"timestamp": "2024-01-15T10:00:01Z", "dst": "10.0.1.2", "dst_port": 22, "protocol": "TCP", "action": "DROP", "bytes_out": 0},
                {"timestamp": "2024-01-15T10:00:02Z", "dst": "10.0.1.3", "dst_port": 22, "protocol": "TCP", "action": "DROP", "bytes_out": 0},
            ]
        }
    })
    result = network_skill.execute(
        indicator="10.0.0.25",
        indicator_type="ipv4"
    )
    console.print(f"[green]Success:[/green] {result.success}")
    if result.data:
        console.print(f"[green]Total connections:[/green] {result.data.get('total_connections')}")

    console.print("\n[cyan]Testing Endpoint Skill[/cyan]")
    endpoint_skill = EndpointSkill(mock_data={
        "WS001": {
            "process_tree": [
                {"parent": "winword.exe", "parent_pid": 2048, "child": "powershell.exe", "child_pid": 4096}
            ]
        }
    })
    result = endpoint_skill.execute(
        host="WS001"
    )
    console.print(f"[green]Success:[/green] {result.success}")
    if result.data:
        console.print(f"[green]Suspicious:[/green] {len(result.data.get('suspicious_relationships', []))}")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="SOC Investigation CLI - AI-assisted security incident investigation"
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Investigate command
    investigate_parser = subparsers.add_parser("investigate", help="Investigate an indicator")
    investigate_parser.add_argument("indicator", help="IOC to investigate (IP, domain, hash, hostname)")
    investigate_parser.add_argument("--type", "-t", default="ipv4", choices=["ipv4", "domain", "hash", "hostname"], help="Indicator type")
    investigate_parser.add_argument("--context", "-c", help="Investigation context")
    investigate_parser.add_argument(
        "--provider",
        "-p",
        default="mock",
        choices=["openai", "openrouter", "routed", "mock"],
        help="LLM provider",
    )
    investigate_parser.add_argument("--model", "-m", default="gpt-4o", help="Model name")
    investigate_parser.add_argument("--api-key", help="API key (or set env var)")
    investigate_parser.add_argument(
        "--fallback-model",
        default=DEFAULT_OPENROUTER_FREE_MODEL,
        help="Pinned OpenRouter :free model for routed mode",
    )
    investigate_parser.add_argument(
        "--run-mode",
        choices=["evaluation", "development", "demo"],
        default="evaluation",
        help="Evaluation disables fallback; development/demo allow controlled fallback",
    )
    investigate_parser.add_argument("--monthly-budget-usd", type=float)
    investigate_parser.add_argument(
        "--budget-ledger",
        default=".vinsoc/openai_budget.json",
        help="Persistent monthly OpenAI cost ledger",
    )
    investigate_parser.add_argument(
        "--duckdb-snapshot",
        help="Path to a frozen, public-data DuckDB snapshot for read-only network and endpoint lookups",
    )

    # Scenario command
    scenario_parser = subparsers.add_parser("scenario", help="Run a predefined scenario")
    scenario_parser.add_argument("scenario", help="Scenario ID or path (e.g., case_001)")
    scenario_parser.add_argument(
        "--provider",
        "-p",
        default="mock",
        choices=["openai", "openrouter", "routed", "mock"],
        help="LLM provider",
    )
    scenario_parser.add_argument("--model", "-m", default="gpt-4o", help="Model name")
    scenario_parser.add_argument(
        "--fallback-model",
        default=DEFAULT_OPENROUTER_FREE_MODEL,
        help="Pinned OpenRouter :free model for routed mode",
    )
    scenario_parser.add_argument(
        "--run-mode",
        choices=["evaluation", "development", "demo"],
        default="evaluation",
    )
    scenario_parser.add_argument("--monthly-budget-usd", type=float)
    scenario_parser.add_argument(
        "--budget-ledger",
        default=".vinsoc/openai_budget.json",
    )

    # List scenarios command
    subparsers.add_parser("list", help="List available scenarios")

    # Test command
    subparsers.add_parser("test", help="Test skill functionality")

    # Benchmark command
    benchmark_parser = subparsers.add_parser("benchmark", help="Compare evidence-driven vs fixed pipeline")
    benchmark_parser.add_argument("--limit", type=int, default=None, help="Optional number of scenarios to run")

    args = parser.parse_args()

    if args.command == "investigate":
        run_direct_investigation(
            indicator=args.indicator,
            indicator_type=args.type,
            context=args.context,
            provider=args.provider,
            model=args.model,
            api_key=args.api_key,
            fallback_model=args.fallback_model,
            run_mode=args.run_mode,
            monthly_budget_usd=args.monthly_budget_usd,
            budget_ledger_path=args.budget_ledger,
            duckdb_snapshot_path=args.duckdb_snapshot,
        )
    elif args.command == "scenario":
        run_scenario(
            args.scenario,
            args.provider,
            args.model,
            args.fallback_model,
            args.run_mode,
            args.monthly_budget_usd,
            args.budget_ledger,
        )
    elif args.command == "list":
        list_scenarios()
    elif args.command == "test":
        test_skills()
    elif args.command == "benchmark":
        run_benchmark(limit=args.limit)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
