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
from rich.syntax import Syntax
from rich.markdown import Markdown

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.orchestrator import InvestigationOrchestrator
from agent.provider import create_provider, MockProvider
from skills.cti_skill import CTISkill
from skills.network_skill import NetworkSkill
from skills.endpoint_skill import EndpointSkill


console = Console()


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
    return {
        "cti_mock_data": scenario.get("test_data", {}).get("cti_response", {}),
        "network_mock_data": scenario.get("test_data", {}),
        "endpoint_mock_data": scenario.get("test_data", {}).get("endpoint_data", {})
    }


def run_investigation(
    indicator: str,
    indicator_type: str,
    context: Optional[str] = None,
    provider: str = "mock",
    model: str = "gpt-4o",
    api_key: Optional[str] = None,
    test_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Run an investigation and return results."""
    # Create LLM provider
    if provider == "mock":
        llm_provider = MockProvider(model="test")
        # Add mock responses
        llm_provider.add_response("CTI", "I'll enrich this indicator with threat intelligence.")
        llm_provider.add_response("benign", "The indicator appears benign. Let me check if further investigation is needed.")
        llm_provider.add_response("malicious", "This indicator is malicious. I should investigate further with network and endpoint tools.")
    else:
        llm_provider = create_provider(provider, model, api_key)

    # Create orchestrator
    orchestrator = InvestigationOrchestrator(
        provider=llm_provider,
        cti_mock_data=test_data.get("cti_mock_data") if test_data else None,
        network_mock_data=test_data.get("network_mock_data") if test_data else None,
        endpoint_mock_data=test_data.get("endpoint_mock_data") if test_data else None
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


def run_scenario(scenario_path: str, provider: str = "mock", model: str = "gpt-4o"):
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

    console.print(f"\n[cyan]Running investigation...[/cyan]\n")

    # Run investigation
    case = run_investigation(
        indicator=indicator.get("value"),
        indicator_type=indicator.get("type", "ipv4"),
        context=indicator.get("context"),
        provider=provider,
        model=model,
        test_data=test_data
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
    api_key: Optional[str]
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
        api_key=api_key
    )

    display_case(case)


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
    cti_skill = CTISkill()
    result = cti_skill.execute(indicator="185.220.101.45")
    console.print(f"[green]Success:[/green] {result.success}")
    if result.data:
        console.print(f"[green]Reputation:[/green] {result.data.get('reputation')}")

    console.print("\n[cyan]Testing Network Skill[/cyan]")
    network_skill = NetworkSkill()
    result = network_skill.execute(
        indicator="10.0.0.25",
        mock_data={
            "connections": [
                {"timestamp": "2024-01-15T10:00:00Z", "dst": "10.0.1.1", "dst_port": 22, "protocol": "TCP", "action": "DROP", "bytes_out": 0},
                {"timestamp": "2024-01-15T10:00:01Z", "dst": "10.0.1.2", "dst_port": 22, "protocol": "TCP", "action": "DROP", "bytes_out": 0},
            ]
        }
    )
    console.print(f"[green]Success:[/green] {result.success}")
    if result.data:
        console.print(f"[green]Total connections:[/green] {result.data.get('total_connections')}")

    console.print("\n[cyan]Testing Endpoint Skill[/cyan]")
    endpoint_skill = EndpointSkill()
    result = endpoint_skill.execute(
        host="WS001",
        mock_data={
            "process_tree": [
                {"parent": "winword.exe", "parent_pid": 2048, "child": "powershell.exe", "child_pid": 4096}
            ]
        }
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
    investigate_parser.add_argument("--provider", "-p", default="mock", choices=["openai", "gemini", "mock"], help="LLM provider")
    investigate_parser.add_argument("--model", "-m", default="gpt-4o", help="Model name")
    investigate_parser.add_argument("--api-key", help="API key (or set env var)")

    # Scenario command
    scenario_parser = subparsers.add_parser("scenario", help="Run a predefined scenario")
    scenario_parser.add_argument("scenario", help="Scenario ID or path (e.g., case_001)")
    scenario_parser.add_argument("--provider", "-p", default="mock", choices=["openai", "gemini", "mock"], help="LLM provider")
    scenario_parser.add_argument("--model", "-m", default="gpt-4o", help="Model name")

    # List scenarios command
    subparsers.add_parser("list", help="List available scenarios")

    # Test command
    subparsers.add_parser("test", help="Test skill functionality")

    args = parser.parse_args()

    if args.command == "investigate":
        run_direct_investigation(
            indicator=args.indicator,
            indicator_type=args.type,
            context=args.context,
            provider=args.provider,
            model=args.model,
            api_key=args.api_key
        )
    elif args.command == "scenario":
        run_scenario(args.scenario, args.provider, args.model)
    elif args.command == "list":
        list_scenarios()
    elif args.command == "test":
        test_skills()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
