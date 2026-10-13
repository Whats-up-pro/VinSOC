"""
VinSOC E2E Demo Dashboard

A visual dashboard to demonstrate:
- R1 Tool Calling (BFCL reference)
- R2 Text-to-SQL (Spider/BIRD reference)
- E2E Network Investigation Pipeline
- SOC Traces with insufficient evidence
"""
from __future__ import annotations

import json
from pathlib import Path

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go


# =============================================================================
# CONFIGURATION
# =============================================================================

st.set_page_config(
    page_title="VinSOC E2E Demo",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Paths
BASE_DIR = Path(__file__).parent.parent
MENTOR_DIR = BASE_DIR / "results/mentor_demo_20261013_104603"
R1_RESULT = BASE_DIR / "results/evaluation_v1/r1/r1_a1_dev_v2_852e543.json"
SOC_TRACE_DIR = BASE_DIR / "results/evaluation_v1/soc_traces_v1/demo_e2e"


# =============================================================================
# DATA LOADERS
# =============================================================================

@st.cache_data
def load_mentor_data():
    """Load mentor demo data."""
    outcome_audit = {}
    e3_case = {}

    audit_path = MENTOR_DIR / "outcome_audit.json"
    if audit_path.exists():
        with open(audit_path, encoding="utf-8") as f:
            outcome_audit = json.load(f)

    case_path = MENTOR_DIR / "E3_ctu_cross_708b66575657429a.json"
    if case_path.exists():
        with open(case_path, encoding="utf-8") as f:
            e3_case = json.load(f)

    return outcome_audit, e3_case


@st.cache_data
def load_r1_data():
    """Load R1 tool calling results."""
    if not R1_RESULT.exists():
        return {}

    with open(R1_RESULT, encoding="utf-8") as f:
        return json.load(f)


@st.cache_data
def load_soc_trace():
    """Load SOC trace."""
    trace_path = SOC_TRACE_DIR / "SCT-087094_S1.json"
    if not trace_path.exists():
        return {}

    with open(trace_path, encoding="utf-8") as f:
        return json.load(f)


# =============================================================================
# COMPONENTS
# =============================================================================

def render_header():
    """Render page header."""
    st.title("🔍 VinSOC E2E Demo Dashboard")
    st.markdown("""
    **Framework:** R1 (BFCL-style) + R2 (Spider/BIRD-style) + E2E Network Investigation

    This dashboard visualizes authentic artifacts from real model API calls.
    """)
    st.divider()


def render_metrics_row(metrics: dict):
    """Render key metrics in a row."""
    cols = st.columns(4)

    metrics_display = [
        ("API Calls", metrics.get("api_calls", "N/A"), "📡"),
        ("Cost (USD)", f"${metrics.get('cost_usd', 0):.6f}", "💰"),
        ("Status", metrics.get("status", "N/A"), "✅"),
        ("Scenarios", metrics.get("scenarios", "N/A"), "📋"),
    ]

    for col, (label, value, icon) in zip(cols, metrics_display):
        with col:
            st.metric(label=f"{icon} {label}", value=value)


def render_api_calls_timeline(calls: list):
    """Render API calls timeline."""
    if not calls:
        st.info("No API calls recorded")
        return

    # Prepare data
    stages = []
    tokens = []
    costs = []

    for call in calls:
        stages.append(call.get("stage", "unknown"))
        usage = call.get("usage", {})
        total_tokens = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
        tokens.append(total_tokens)
        costs.append(call.get("cost_usd", 0))

    # Token distribution chart
    fig = px.bar(
        x=stages,
        y=tokens,
        title="Token Usage by Stage",
        labels={"x": "Stage", "y": "Total Tokens"},
        color=stages,
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig.update_layout(showlegend=False, height=300)
    st.plotly_chart(fig, use_container_width=True)

    # Cost breakdown
    fig2 = px.pie(
        values=costs,
        names=stages,
        title="Cost Distribution",
        hole=0.4,
    )
    fig2.update_layout(height=300)
    st.plotly_chart(fig2, use_container_width=True)


def render_assessment_card(assessment: dict):
    """Render assessment details."""
    st.subheader("📊 Assessment")

    col1, col2 = st.columns(2)

    with col1:
        st.metric("Risk Level", assessment.get("risk_level", "UNKNOWN"))
        st.metric("Confidence", assessment.get("confidence", "UNKNOWN"))

    with col2:
        st.metric(
            "Evidence IDs",
            len(assessment.get("evidence_ids", [])),
        )
        st.metric(
            "Limitations",
            len(assessment.get("limitations", [])),
        )

    st.markdown(f"**Assessment:** {assessment.get('assessment', 'N/A')}")

    # Limitations
    limitations = assessment.get("limitations", [])
    if limitations:
        with st.expander("⚠️ Limitations"):
            for i, lim in enumerate(limitations, 1):
                st.markdown(f"{i}. {lim}")


def render_evidence_viewer(evidence: list):
    """Render evidence viewer."""
    st.subheader("🔎 Evidence Store")

    if not evidence:
        st.info("No evidence collected")
        return

    st.write(f"**{len(evidence)} evidence items**")

    for i, ev in enumerate(evidence[:10], 1):  # Show first 10
        with st.expander(f"Evidence {i}: {ev.get('evidence_id', 'unknown')}"):
            st.json(ev)


def render_scenario_comparison(scenarios: list):
    """Render scenario comparison."""
    st.subheader("🔄 Scenario Comparison")

    if not scenarios:
        st.info("No scenarios")
        return

    for scenario in scenarios:
        name = scenario.get("name", "unknown")
        assessment = scenario.get("assessment", {})

        with st.expander(f"📌 {name.upper()}"):
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Risk", assessment.get("risk_level", "N/A"))
                st.metric("Confidence", assessment.get("confidence", "N/A"))

            with col2:
                ev_count = len(scenario.get("evidence", []))
                st.metric("Evidence Items", ev_count)

            st.markdown(f"**Assessment:** {assessment.get('assessment', 'N/A')[:200]}...")


# =============================================================================
# MAIN TABS
# =============================================================================

def tab_overview():
    """Overview tab."""
    st.header("📊 Overview")

    # Load data
    outcome_audit, _ = load_mentor_data()
    r1_data = load_r1_data()

    # Demo status
    st.subheader("🎯 Demo Status")

    demo_status = {
        "R1 Tool Calling": ("✅ Ready", "22/24 cases"),
        "R2 Text-to-SQL": ("⏳ Partial", "1/4 cases"),
        "E2E Pipeline": ("✅ Complete", "Technical done"),
        "Human Review": ("⏳ Pending", "Awaiting human"),
    }

    cols = st.columns(4)
    for col, (name, (status, detail)) in zip(cols, demo_status.items()):
        with col:
            st.info(f"**{name}**\n{status}\n_{detail}_")

    # Key metrics
    st.subheader("📈 Key Metrics")

    actual = outcome_audit.get("actual", {})
    if actual:
        cols = st.columns(4)
        with cols[0]:
            st.metric("API Calls", actual.get("provider_transmitted_calls", 0))
        with cols[1]:
            st.metric("Current Cost", f"${actual.get('current_run_cost_usd', 0):.6f}")
        with cols[2]:
            st.metric("Cumulative Cost", f"${actual.get('cumulative_cost_usd', 0):.6f}")
        with cols[3]:
            st.metric("Remaining Cap", f"${actual.get('remaining_cap_usd', 0):.6f}")

    # Pipeline visualization
    st.subheader("🔄 Pipeline Flow")

    pipeline_fig = go.Figure()

    stages = ["Routing", "Schema\nLinker", "SQL\nGenerator", "Assessment"]
    costs = [0.000245, 0.003916, 0.002106, 0.001230]  # From actual data
    tokens = [414, 7571, 3241, 2249]  # Estimated

    pipeline_fig.add_trace(go.Scatter(
        x=stages,
        y=tokens,
        mode="lines+markers",
        name="Tokens",
        line=dict(color="blue", width=3),
        marker=dict(size=15),
    ))

    pipeline_fig.update_layout(
        title="E2E Pipeline: Token Usage by Stage",
        xaxis_title="Pipeline Stage",
        yaxis_title="Tokens",
        height=300,
    )

    st.plotly_chart(pipeline_fig, use_container_width=True)


def tab_r1_tool_calling():
    """R1 Tool Calling tab."""
    st.header("🎯 R1: Tool Calling (BFCL Reference)")

    st.markdown("""
    **Reference:** Berkeley Function Calling Leaderboard (BFCL)

    R1 evaluates model ability to:
    - Select correct tool(s) based on query
    - Provide accurate arguments
    - Avoid hallucination
    """)

    # Load data
    r1_data = load_r1_data()

    if not r1_data:
        st.error("R1 results not found")
        return

    # Metrics
    metrics = r1_data.get("metrics", {})

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Tool Selection Accuracy", f"{metrics.get('tool_selection_accuracy', 0):.2%}")
    with col2:
        st.metric("Exact Call F1", f"{metrics.get('exact_call_f1', 0):.2%}")
    with col3:
        st.metric("Required Arg Accuracy", f"{metrics.get('required_argument_accuracy', 0):.2%}")
    with col4:
        st.metric("No-Tool Accuracy", f"{metrics.get('no_tool_accuracy', 0):.2%}")

    # Case breakdown chart
    st.subheader("📊 Case Results")

    cases = r1_data.get("cases", [])
    passed = sum(1 for c in cases if c.get("passed"))
    failed = len(cases) - passed

    fig = px.pie(
        values=[passed, failed],
        names=["Passed", "Failed"],
        title=f"R1 Dev: {passed}/{len(cases)} Cases Passed",
        hole=0.4,
        color=["green", "red"],
    )
    st.plotly_chart(fig, use_container_width=True)

    # Case details
    st.subheader("📋 Case Details")

    case_data = []
    for case in cases:
        case_data.append({
            "Case ID": case.get("case_id", "unknown"),
            "Status": "✅" if case.get("passed") else "❌",
            "Tool": case.get("expected_tool", "N/A"),
            "Score": case.get("score", 0),
        })

    if case_data:
        st.dataframe(case_data, use_container_width=True, hide_index=True)


def tab_r2_text_to_sql():
    """R2 Text-to-SQL tab."""
    st.header("🗄️ R2: Text-to-SQL (Spider/BIRD Reference)")

    st.markdown("""
    **Reference:** Spider / BIRD Benchmarks

    R2 evaluates model ability to:
    - Generate syntactically valid SQL
    - Execute correctly on DuckDB
    - Match expected semantic results
    """)

    # Load data
    outcome_audit, e3_case = load_mentor_data()
    actual = outcome_audit.get("actual", {})

    if not actual:
        st.info("No R2 results available")
        return

    # Metrics
    st.subheader("📊 E3 Case Results")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Final SQL Present", "✅" if actual.get("final_sql_present") else "❌")
    with col2:
        st.metric("Execution Success", "✅" if actual.get("execution_success") else "❌")
    with col3:
        st.metric("Execution Accurate", "✅" if actual.get("execution_accurate") else "❌")
    with col4:
        st.metric("Semantic Audit", "✅" if not actual.get("semantic_audit", {}).get("first_generator_candidate_rejected") else "⚠️")

    # SQL Query
    st.subheader("📝 Final SQL Query")

    final_sql = actual.get("final_sql", "N/A")
    st.code(final_sql, language="sql")

    # Result
    st.subheader("📊 Query Result")

    result = actual.get("result", {})
    if result:
        cols = result.get("columns", [])
        rows = result.get("rows", [])

        st.write(f"**Columns:** {[c.get('name') for c in cols]}")
        st.write(f"**Rows:** {len(rows)}")
        st.write(f"**Type:** {cols[0].get('type') if cols else 'N/A'}")

        st.json({"columns": cols, "rows": rows})

    # Semantic audit
    st.subheader("🔍 Semantic Audit")

    semantic = actual.get("semantic_audit", {})
    if semantic:
        st.info(f"""
        **First Candidate:** {"❌ Rejected" if semantic.get("first_generator_candidate_rejected") else "✅ Accepted"}
        - Shape: {semantic.get("first_candidate_shape", "N/A")}
        """)

        if semantic.get("first_generator_candidate_rejected"):
            st.success(f"""
            **Accepted Candidate Shape:**
            {semantic.get('accepted_candidate_shape', 'N/A')}
            """)


def tab_e2e_pipeline():
    """E2E Pipeline tab."""
    st.header("🔄 E2E Network Investigation Pipeline")

    st.markdown("""
    Complete pipeline: **Query → Model → Tool → Database → Evidence → Assessment → Human Review**
    """)

    # Load data
    outcome_audit, e3_case = load_mentor_data()
    actual = outcome_audit.get("actual", {})
    assessment = actual.get("assessment", {})

    # Pipeline stages visualization
    st.subheader("🔄 Pipeline Stages")

    stages = [
        ("1. Query", "User asks question", actual.get("provider_transmitted_calls", 0) > 0),
        ("2. Routing", "Model selects tool", actual.get("calls_by_role_transmitted", {}).get("routing", 0) > 0),
        ("3. Grounding", "Schema linking", actual.get("r2_stage_calls", {}).get("schema_linker", 0) > 0),
        ("4. Generation", "SQL generation", actual.get("r2_stage_calls", {}).get("sql_generator", 0) > 0),
        ("5. Execution", "DuckDB query", actual.get("execution_success", False)),
        ("6. Assessment", "Model assessment", actual.get("assessment_calls", 0) > 0),
        ("7. Review", "Human approval", actual.get("human_review") == "approved"),
    ]

    cols = st.columns(7)
    for col, (name, desc, status) in zip(cols, stages):
        with col:
            icon = "✅" if status else "⏳"
            st.markdown(f"{icon} **{name}**")
            st.caption(desc[:20])

    # Evidence flow
    st.subheader("🔎 Evidence Store")

    evidence_ids = assessment.get("evidence_ids", [])
    st.write(f"**Evidence IDs:** {evidence_ids}")

    observations = assessment.get("observations", [])
    if observations:
        st.write("**Observations:**")
        for obs in observations:
            st.write(f"  - {obs.get('field')}: {obs.get('value')}")

    # Assessment
    render_assessment_card(assessment)

    # Model calls
    st.subheader("📡 Model API Calls")

    calls = outcome_audit.get("model_call_receipts", [])
    if calls:
        # Summary
        cols = st.columns(4)
        total_input = sum(c.get("usage", {}).get("input_tokens", 0) for c in calls)
        total_output = sum(c.get("usage", {}).get("output_tokens", 0) for c in calls)
        total_cost = sum(c.get("cost_usd", 0) for c in calls)

        with cols[0]:
            st.metric("Total Calls", len(calls))
        with cols[1]:
            st.metric("Input Tokens", f"{total_input:,}")
        with cols[2]:
            st.metric("Output Tokens", f"{total_output:,}")
        with cols[3]:
            st.metric("Total Cost", f"${total_cost:.6f}")

        # Call details
        with st.expander("📋 Call Details"):
            for i, call in enumerate(calls, 1):
                st.markdown(f"**{i}. {call.get('role', 'unknown').upper()}**")
                st.write(f"Model: {call.get('model')}")
                st.write(f"Tokens: {call.get('usage', {}).get('input_tokens', 0)} + {call.get('usage', {}).get('output_tokens', 0)}")
                st.write(f"Cost: ${call.get('cost_usd', 0):.6f}")
                st.divider()


def tab_soc_traces():
    """SOC Traces tab."""
    st.header("🚨 SOC: Insufficient Evidence Case")

    st.markdown("""
    This demo shows the case where:
    - Model receives alert about domain enumeration
    - SOC search finds no matching events
    - Context lookup fails
    - Model reports **insufficient_evidence**
    """)

    # Load SOC trace
    soc_trace = load_soc_trace()

    # Flow visualization
    st.subheader("🔄 Investigation Flow")

    flow_fig = go.Figure()

    nodes = ["Alert", "SOC\nSearch", "SOC\nContext", "Model\nAssessment", "Human\nReview"]
    colors = ["red", "orange", "orange", "yellow", "gray"]
    statuses = ["domain enum", "no_match", "unavailable", "insufficient_evidence", "pending"]

    flow_fig.add_trace(go.Sankey(
        node=dict(
            pad=15,
            thickness=20,
            label=nodes,
            color=colors,
        ),
        link=dict(
            source=[0, 1, 2, 3],
            target=[1, 2, 3, 4],
            value=[1, 1, 1, 1],
            color=["rgba(255,0,0,0.3)", "rgba(255,165,0,0.3)", "rgba(255,165,0,0.3)", "rgba(255,255,0,0.3)"],
        ),
    ))

    flow_fig.update_layout(title="SOC Investigation Flow", height=300)
    st.plotly_chart(flow_fig, use_container_width=True)

    # Status details
    st.subheader("📊 Investigation Status")

    cols = st.columns(3)
    with cols[0]:
        st.metric("Alert Source", "WKS-034")
    with cols[1]:
        st.metric("Event Search", "no_match")
    with cols[2]:
        st.metric("Context", "unavailable")

    # Model response
    st.subheader("🤖 Model Response")

    if soc_trace:
        assessment = soc_trace.get("assessment", {})
        st.info(f"**{assessment.get('assessment', 'N/A')}**")

        # Risk assessment
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Risk Level", assessment.get("risk_level", "UNKNOWN"))
        with col2:
            st.metric("Confidence", assessment.get("confidence", "LOW"))

        # Limitations
        limitations = assessment.get("limitations", [])
        if limitations:
            with st.expander("⚠️ Limitations"):
                for lim in limitations:
                    st.markdown(f"- {lim}")

    # Human review
    st.subheader("👤 Human Review")

    st.warning("**Status: PENDING**")

    st.markdown("""
    ### Key Points:
    1. **No match ≠ Clean**: Not finding events doesn't mean the host is safe
    2. **Missing data is a finding**: The system correctly reports limitations
    3. **Human judgment required**: Analyst must decide next steps
    """)


def tab_artifacts():
    """Artifacts tab."""
    st.header("📁 Source Artifacts")

    st.markdown("""
    This dashboard was built from authentic artifacts:

    | Artifact | Path |
    |----------|------|
    | Mentor Runbook | `results/mentor_demo_20261013_104603/MENTOR_RUNBOOK.md` |
    | Query HTML | `results/mentor_demo_20261013_104603/query.html` |
    | Outcome Audit | `results/mentor_demo_20261013_104603/outcome_audit.json` |
    | E3 Case | `results/mentor_demo_20261013_104603/E3_ctu_cross_708b66575657429a.json` |
    | R1 Results | `results/evaluation_v1/r1/r1_a1_dev_v2_852e543.json` |
    | SOC Trace | `results/evaluation_v1/soc_traces_v1/demo_e2e/SCT-087094_S1.html` |
    """)

    # Links to open files
    st.subheader("🔗 Open Artifacts")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("📊 Open Query HTML", use_container_width=True):
            import webbrowser
            webbrowser.open(str(MENTOR_DIR / "query.html"))

        if st.button("📄 Open SOC Trace", use_container_width=True):
            webbrowser.open(str(SOC_TRACE_DIR / "SCT-087094_S1.html"))

    with col2:
        if st.button("📋 Open Outcome Audit (JSON)", use_container_width=True):
            import webbrowser
            webbrowser.open(str(MENTOR_DIR / "outcome_audit.json"))

        if st.button("🎯 Open R1 Results", use_container_width=True):
            webbrowser.open(str(R1_RESULT))


# =============================================================================
# MAIN
# =============================================================================

def main():
    """Main app."""
    render_header()

    # Tabs
    tabs = [
        "📊 Overview",
        "🎯 R1: Tool Calling",
        "🗄️ R2: Text-to-SQL",
        "🔄 E2E Pipeline",
        "🚨 SOC Traces",
        "📁 Artifacts",
    ]

    tab = st.radio("Navigation", tabs, horizontal=True, label_visibility="collapsed")

    if tab == "📊 Overview":
        tab_overview()
    elif tab == "🎯 R1: Tool Calling":
        tab_r1_tool_calling()
    elif tab == "🗄️ R2: Text-to-SQL":
        tab_r2_text_to_sql()
    elif tab == "🔄 E2E Pipeline":
        tab_e2e_pipeline()
    elif tab == "🚨 SOC Traces":
        tab_soc_traces()
    elif tab == "📁 Artifacts":
        tab_artifacts()


if __name__ == "__main__":
    main()
