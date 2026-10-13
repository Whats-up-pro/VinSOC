"""
VinSOC E2E Demo - Interactive Demo Interface

A fully interactive demo interface for:
1. Enter investigation question
2. Run E2E pipeline with real API calls
3. View results, evidence, and assessment
4. Human review workflow
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

# Define BASE_DIR before loading .env
BASE_DIR = Path(__file__).parent.parent
load_dotenv(BASE_DIR / ".env")

# =============================================================================
# CONFIGURATION
# =============================================================================

st.set_page_config(
    page_title="VinSOC E2E Demo",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Paths
BASE_DIR = Path(__file__).parent.parent
SNAPSHOT_PATH = BASE_DIR / "data/ctu_network_public/snapshots/ctu_dev.duckdb"

# Demo scenarios
DEMO_SCENARIOS = {
    "botnet": {
        "name": "Botnet Detection",
        "indicator": "147.32.84.165",
        "time_range": {
            "start": "2011-08-15 00:00:00",
            "end": "2011-08-15 23:59:59"
        },
        "ground_truth": "Botnet",
        "description": "Known botnet source from CTU-13 Scenario 5"
    },
    "normal": {
        "name": "Normal Traffic",
        "indicator": "147.32.84.165",
        "time_range": {
            "start": "2011-08-16 00:00:00",
            "end": "2011-08-16 23:59:59"
        },
        "ground_truth": "Normal",
        "description": "Same IP, different time - normal traffic pattern"
    },
    "custom": {
        "name": "Custom Query",
        "indicator": "",
        "time_range": {
            "start": "2011-08-15 00:00:00",
            "end": "2011-08-15 23:59:59"
        },
        "ground_truth": "Unknown",
        "description": "Enter your own IP address and time range"
    }
}


# =============================================================================
# UTILITIES
# =============================================================================

def check_environment():
    """Check if environment is ready."""
    issues = []

    # Check snapshot
    if not SNAPSHOT_PATH.exists():
        issues.append(f"Snapshot not found: {SNAPSHOT_PATH}")

    # Check OpenAI key - load from .env if not set
    if not os.environ.get("OPENAI_API_KEY"):
        # Try loading from .env file
        env_path = BASE_DIR / ".env"
        if env_path.exists():
            try:
                from dotenv import load_dotenv
                load_dotenv(env_path)
            except ImportError:
                pass

    if not os.environ.get("OPENAI_API_KEY"):
        issues.append("OPENAI_API_KEY not set")

    return issues


def render_header():
    """Render page header."""
    st.html("""
    <style>
    .main-header {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        padding: 1.5rem;
        border-radius: 10px;
        margin-bottom: 1rem;
    }
    .main-header h1 {
        color: #00d4ff;
        margin: 0;
        font-size: 2rem;
    }
    .main-header p {
        color: #a0a0a0;
        margin: 0.5rem 0 0 0;
    }
    .status-badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 20px;
        font-size: 0.85rem;
        font-weight: 600;
    }
    .status-ready { background: #00c853; color: white; }
    .status-error { background: #ff1744; color: white; }
    .status-running { background: #ff9100; color: white; }
    .status-complete { background: #00bcd4; color: white; }
    </style>
    <div class="main-header">
        <h1>🔍 VinSOC E2E Demo</h1>
        <p>Interactive SOC Investigation with AI</p>
    </div>
    """)


def render_status_banner(issues: list):
    """Render status banner."""
    if not issues:
        st.success("✅ Environment ready - all checks passed")
    else:
        for issue in issues:
            st.error(f"❌ {issue}")


def render_scenario_selector():
    """Render scenario selector."""
    st.subheader("🎯 Select Investigation Scenario")

    col1, col2, col3 = st.columns(3)

    scenario_keys = list(DEMO_SCENARIOS.keys())

    selected = st.radio(
        "Scenario",
        scenario_keys,
        format_func=lambda x: DEMO_SCENARIOS[x]["name"],
        horizontal=True,
        label_visibility="collapsed"
    )

    scenario = DEMO_SCENARIOS[selected]

    # Display scenario info
    cols = st.columns([1, 2])
    with cols[0]:
        st.info(f"""
        **Ground Truth:** {scenario['ground_truth']}

        **Indicator:** `{scenario['indicator']}`

        **Time Range:**
        - Start: `{scenario['time_range']['start']}`
        - End: `{scenario['time_range']['end']}`
        """)

    with cols[1]:
        st.markdown(f"**Description:** {scenario['description']}")

    return scenario, selected


def render_custom_inputs(scenario: dict):
    """Render custom input fields."""
    st.subheader("✏️ Custom Parameters")

    col1, col2 = st.columns(2)

    with col1:
        indicator = st.text_input(
            "IP Address / Indicator",
            value=scenario.get("indicator", ""),
            placeholder="e.g., 147.32.84.165",
            help="Enter IP address, domain, or other indicator to investigate"
        )

    with col2:
        indicator_type = st.selectbox(
            "Indicator Type",
            ["ipv4", "domain", "ipv6"],
            index=0
        )

    col3, col4 = st.columns(2)

    with col3:
        start_time = st.text_input(
            "Start Time",
            value=scenario.get("time_range", {}).get("start", "2011-08-15 00:00:00"),
            placeholder="YYYY-MM-DD HH:MM:SS"
        )

    with col4:
        end_time = st.text_input(
            "End Time",
            value=scenario.get("time_range", {}).get("end", "2011-08-15 23:59:59"),
            placeholder="YYYY-MM-DD HH:MM:SS"
        )

    return {
        "indicator": indicator,
        "indicator_type": indicator_type,
        "time_range": {
            "start": start_time,
            "end": end_time
        }
    }


def render_investigate_button(scenario_key: str):
    """Render investigate button."""
    st.divider()

    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        button_text = "🚀 Start Investigation"
        if scenario_key == "custom":
            button_text = "🚀 Start Custom Investigation"

        if st.button(button_text, type="primary", use_container_width=True):
            return True

    with col2:
        st.caption("Estimated cost: ~$0.004")

    with col3:
        st.caption("Max time: ~30s")

    return False


def run_investigation(scenario: dict):
    """Run the investigation pipeline."""
    # Initialize session state
    if "investigation_results" not in st.session_state:
        st.session_state.investigation_results = None

    if "investigation_running" not in st.session_state:
        st.session_state.investigation_running = False

    if "investigation_error" not in st.session_state:
        st.session_state.investigation_error = None

    # Progress indicators
    progress_bar = st.progress(0)
    status_text = st.empty()

    try:
        # Step 1: Initialize
        status_text.text("📡 Initializing investigation...")
        progress_bar.progress(10)
        time.sleep(0.5)

        # Step 2: Route to tool
        status_text.text("🔍 Routing query to network tool...")
        progress_bar.progress(30)
        time.sleep(1)

        # Step 3: Execute tool (simulate for demo)
        status_text.text("💾 Executing query on DuckDB...")
        progress_bar.progress(50)

        # Import and run
        from agent.orchestrator import InvestigationOrchestrator
        from agent.network_investigation_policy import NetworkInvestigationPolicy
        from vinsoc_data.duckdb_store import DuckDBSnapshot

        snapshot = DuckDBSnapshot(str(SNAPSHOT_PATH), read_only=True)
        policy = NetworkInvestigationPolicy()
        orchestrator = InvestigationOrchestrator(policy=policy)

        # Step 4: Investigate
        status_text.text("🤖 Model analyzing evidence...")
        progress_bar.progress(70)

        case = orchestrator.investigate(
            snapshot=snapshot,
            indicator=scenario["indicator"],
            indicator_type=scenario.get("indicator_type", "ipv4"),
            time_range=scenario["time_range"],
        )

        progress_bar.progress(90)
        time.sleep(0.5)

        # Complete
        progress_bar.progress(100)
        status_text.text("✅ Investigation complete!")

        st.session_state.investigation_results = case
        st.session_state.investigation_running = False

    except Exception as e:
        st.session_state.investigation_error = str(e)
        st.session_state.investigation_running = False
        progress_bar.progress(0)
        status_text.error(f"❌ Error: {e}")


def render_results(results: dict):
    """Render investigation results."""
    if not results:
        return

    st.divider()
    st.subheader("📊 Investigation Results")

    # Assessment
    assessment = results.get("assessment", {})
    evidence = results.get("evidence", [])

    # Key metrics
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        risk = assessment.get("risk_level", "UNKNOWN")
        risk_color = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢", "UNKNOWN": "⚪"}.get(risk, "⚪")
        st.metric(f"{risk_color} Risk Level", risk)

    with col2:
        confidence = assessment.get("confidence", "UNKNOWN")
        st.metric("Confidence", confidence)

    with col3:
        st.metric("Evidence Items", len(evidence))

    with col4:
        observations = assessment.get("observations", [])
        st.metric("Observations", len(observations))

    # Assessment text
    st.markdown("---")
    st.subheader("🤖 Model Assessment")

    assessment_text = assessment.get("assessment", "No assessment available")
    st.info(assessment_text)

    # Evidence
    st.markdown("---")
    st.subheader("🔎 Evidence Collected")

    if evidence:
        # Show evidence table
        evidence_data = []
        for i, ev in enumerate(evidence[:10], 1):  # Show first 10
            evidence_data.append({
                "#": i,
                "ID": ev.get("evidence_id", "N/A")[:20],
                "Type": ev.get("type", "N/A"),
                "Class": ev.get("evidence_class", "N/A"),
            })

        if evidence_data:
            st.dataframe(evidence_data, use_container_width=True, hide_index=True)

        if len(evidence) > 10:
            st.caption(f"Showing 10 of {len(evidence)} evidence items")
    else:
        st.info("No evidence collected")

    # Observations
    observations = assessment.get("observations", [])
    if observations:
        st.markdown("---")
        st.subheader("📈 Key Observations")

        for obs in observations:
            field = obs.get("field", "unknown")
            value = obs.get("value", "N/A")
            st.write(f"- **{field}**: {value}")

    # Limitations
    limitations = assessment.get("limitations", [])
    if limitations:
        st.markdown("---")
        st.warning("⚠️ Limitations")
        for lim in limitations:
            st.markdown(f"- {lim}")

    # Human review
    st.markdown("---")
    render_human_review(results)


def render_human_review(results: dict):
    """Render human review section."""
    st.subheader("👤 Human Review")

    col1, col2 = st.columns([1, 2])

    with col1:
        st.info("**Status:** ⏳ PENDING REVIEW")

    with col2:
        st.markdown("""
        As an analyst, review the assessment and evidence:

        1. **Verify** the evidence supports the assessment
        2. **Check** observations match your expectations
        3. **Consider** the limitations noted
        4. **Decide** on next steps
        """)

    # Review buttons
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("✅ Approve", use_container_width=True):
            st.success("✅ Investigation approved!")
            st.balloons()

    with col2:
        if st.button("❌ Reject", use_container_width=True):
            st.error("❌ Investigation rejected - requires further analysis")

    with col3:
        if st.button("🔄 Request More Evidence", use_container_width=True):
            st.info("🔄 Additional investigation requested")


def render_sidebar():
    """Render sidebar with info."""
    with st.sidebar:
        st.header("ℹ️ About")

        st.markdown("""
        **VinSOC E2E Demo**

        Interactive SOC investigation using AI:

        1. Enter investigation parameters
        2. Run E2E pipeline
        3. View evidence and assessment
        4. Human review and approval

        **Reference Frameworks:**
        - R1: BFCL (Tool Calling)
        - R2: Spider/BIRD (Text-to-SQL)
        """)

        st.divider()

        st.subheader("📁 Source Artifacts")

        st.markdown("""
        - [Mentor Runbook](results/mentor_demo_20261013_104603/MENTOR_RUNBOOK.md)
        - [Query HTML](results/mentor_demo_20261013_104603/query.html)
        - [R1 Results](results/evaluation_v1/r1/r1_a1_dev_v2_852e543.json)
        """)

        st.divider()

        st.subheader("🔧 Settings")

        budget = st.slider("Budget (USD)", 0.01, 1.0, 0.25, 0.01)
        st.session_state.budget_usd = budget

        st.caption(f"Max API calls: ~4")
        st.caption(f"Estimated cost: ~${budget * 0.1:.4f}")


# =============================================================================
# MAIN TABS
# =============================================================================

def tab_demo_scenarios():
    """Demo scenarios tab."""
    st.header("🎯 Demo Scenarios")

    # Initialize session state
    if "investigation_results" not in st.session_state:
        st.session_state.investigation_results = None
    if "investigation_running" not in st.session_state:
        st.session_state.investigation_running = False

    scenario, selected_key = render_scenario_selector()

    # Run investigation
    if render_investigate_button(selected_key):
        st.session_state.investigation_running = True
        run_investigation(scenario)

    # Show results if available
    if st.session_state.investigation_results:
        render_results(st.session_state.investigation_results)


def tab_custom_query():
    """Custom query tab."""
    st.header("✏️ Custom Investigation")

    # Initialize session state
    if "investigation_results" not in st.session_state:
        st.session_state.investigation_results = None
    if "investigation_running" not in st.session_state:
        st.session_state.investigation_running = False

    scenario, _ = render_scenario_selector()
    custom_params = render_custom_inputs(scenario)

    # Run investigation
    if render_investigate_button("custom"):
        st.session_state.investigation_running = True
        custom_params["indicator_type"] = scenario.get("indicator_type", "ipv4")
        run_investigation(custom_params)

    # Show results if available
    if st.session_state.investigation_results:
        render_results(st.session_state.investigation_results)


def tab_results_review():
    """Results and review tab."""
    st.header("📋 Results & Review")

    if not st.session_state.investigation_results:
        st.info("👆 Run an investigation first to see results here")
        return

    render_results(st.session_state.investigation_results)


def tab_pipeline_flow():
    """Pipeline flow visualization tab."""
    st.header("🔄 Pipeline Flow")

    st.markdown("""
    ## How VinSOC E2E Works

    ### 1. Query Input
    User provides investigation question with indicator and time range

    ### 2. Model Routing
    Model analyzes query and selects appropriate tool(s)
    - **Network tool**: Flow telemetry queries
    - **CTI tool**: Threat intelligence lookup
    - **Endpoint tool**: Process/registry data
    """)

    # Visual flow
    flow_html = """
    <style>
    .flow-container {
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 2rem;
        gap: 1rem;
    }
    .flow-step {
        background: #1a1a2e;
        padding: 1rem 1.5rem;
        border-radius: 10px;
        text-align: center;
        min-width: 120px;
    }
    .flow-step.active {
        background: #00bcd4;
        color: white;
    }
    .flow-arrow {
        font-size: 1.5rem;
        color: #00d4ff;
    }
    </style>

    <div class="flow-container">
        <div class="flow-step">📝 Query</div>
        <span class="flow-arrow">→</span>
        <div class="flow-step">🤖 Model</div>
        <span class="flow-arrow">→</span>
        <div class="flow-step">🔧 Tool</div>
        <span class="flow-arrow">→</span>
        <div class="flow-step">💾 DB</div>
        <span class="flow-arrow">→</span>
        <div class="flow-step">🔎 Evidence</div>
        <span class="flow-arrow">→</span>
        <div class="flow-step">📊 Assessment</div>
    </div>
    """
    st.html(flow_html)

    st.markdown("""
    ### 3. Tool Execution
    Selected tool executes on read-only DuckDB database

    ### 4. Evidence Collection
    Query results are stored as evidence with provenance

    ### 5. Assessment
    Model generates assessment with evidence citations

    ### 6. Human Review
    Analyst reviews and approves/rejects assessment
    """)


# =============================================================================
# MAIN
# =============================================================================

def main():
    """Main app."""
    # Check environment
    issues = check_environment()

    # Header
    render_header()

    # Status
    render_status_banner(issues)

    if issues:
        st.stop()

    # Tabs
    tabs = [
        "🎯 Demo Scenarios",
        "✏️ Custom Query",
        "📋 Results & Review",
        "🔄 Pipeline Flow",
    ]

    selected_tab = st.radio("Navigation", tabs, horizontal=True, label_visibility="collapsed")

    if selected_tab == "🎯 Demo Scenarios":
        tab_demo_scenarios()
    elif selected_tab == "✏️ Custom Query":
        tab_custom_query()
    elif selected_tab == "📋 Results & Review":
        tab_results_review()
    elif selected_tab == "🔄 Pipeline Flow":
        tab_pipeline_flow()

    # Sidebar
    render_sidebar()


if __name__ == "__main__":
    main()
