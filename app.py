"""
app.py — ogcorrosion.org Integrated Integrity Digital Twin (AIV Framework)
==========================================================================
Streamlit enterprise dashboard for SLB Ahmadi Innovation Valley & KOC
technical steering committee demonstration.

Run:
    streamlit run app.py

Petroleum engineering audit trail:
  - All calculations delegate to physics.py (modular, unit-tested)
  - Sidebar grouped per AIV digital twin input taxonomy
  - Nodal network follows KOC gathering centre flow path
"""

from __future__ import annotations

import streamlit as st

from data_provider import (
    PROFILE_KEYS,
    apply_profile,
    get_csv_template_bytes,
    merge_profile_with_upload,
    parse_laboratory_csv,
    resolve_field_search,
)
from physics import (
    ChemistryControls,
    HealthStatus,
    LabFluidTraits,
    PhysicalInspection,
    ScadaInputs,
    run_full_assessment,
)

# ---------------------------------------------------------------------------
# Page config & dark industrial theme
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="ogcorrosion.org | Integrated Integrity Digital Twin",
    page_icon="🛢️",
    layout="wide",
    initial_sidebar_state="expanded",
)

DARK_CSS = """
<style>
    /* SLB AIV / KOC industrial dark dashboard */
    .stApp {
        background: linear-gradient(160deg, #0B1120 0%, #111827 45%, #0F172A 100%);
        color: #E2E8F0;
    }
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0F172A 0%, #1E293B 100%);
        border-right: 1px solid #334155;
    }
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3,
    [data-testid="stSidebar"] label, [data-testid="stSidebar"] p, [data-testid="stSidebar"] span {
        color: #CBD5E1 !important;
    }
    .main-title {
        font-size: 1.65rem;
        font-weight: 800;
        color: #F8FAFC;
        letter-spacing: -0.02em;
        margin-bottom: 0.15rem;
    }
    .sub-title {
        font-size: 0.85rem;
        color: #94A3B8;
        margin-bottom: 1.5rem;
    }
    .aiv-badge {
        display: inline-block;
        background: linear-gradient(90deg, #1D4ED8, #0D9488);
        color: white;
        font-size: 0.7rem;
        font-weight: 700;
        padding: 4px 12px;
        border-radius: 999px;
        letter-spacing: 0.05em;
        text-transform: uppercase;
        margin-bottom: 1rem;
    }
    .node-card {
        background: #1E293B;
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 1rem;
        text-align: center;
        min-height: 200px;
        transition: border-color 0.2s;
    }
    .node-card:hover {
        border-color: #3B82F6;
    }
    .node-card.critical { border-color: #DC2626; box-shadow: 0 0 12px rgba(220,38,38,0.3); }
    .node-card.elevated { border-color: #EA580C; }
    .node-card.watch { border-color: #D97706; }
    .node-card.healthy { border-color: #16A34A; }
    .node-name { font-size: 0.75rem; font-weight: 700; color: #94A3B8; text-transform: uppercase; letter-spacing: 0.04em; }
    .node-rate { font-size: 1.6rem; font-weight: 800; color: #F8FAFC; margin: 0.4rem 0; }
    .node-rul { font-size: 0.8rem; color: #64748B; }
    .health-badge {
        display: inline-block;
        font-size: 0.65rem;
        font-weight: 700;
        padding: 3px 10px;
        border-radius: 999px;
        margin-top: 0.5rem;
        text-transform: uppercase;
    }
    .badge-healthy { background: #064E3B; color: #6EE7B7; }
    .badge-watch { background: #78350F; color: #FCD34D; }
    .badge-elevated { background: #7C2D12; color: #FDBA74; }
    .badge-critical { background: #7F1D1D; color: #FCA5A5; }
    .pipeline-arrow {
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.5rem;
        color: #3B82F6;
        font-weight: 700;
        padding-top: 3rem;
    }
    .kpi-card {
        background: linear-gradient(135deg, #1E293B 0%, #0F172A 100%);
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 1.25rem;
        text-align: center;
    }
    .kpi-value { font-size: 1.75rem; font-weight: 800; color: #34D399; }
    .kpi-label { font-size: 0.7rem; color: #94A3B8; text-transform: uppercase; letter-spacing: 0.06em; margin-top: 0.3rem; }
    .warning-flag { color: #F87171; font-size: 0.7rem; font-weight: 600; }
    .section-header { color: #F1F5F9; font-size: 1.05rem; font-weight: 700; margin: 1.5rem 0 0.75rem 0; border-bottom: 1px solid #334155; padding-bottom: 0.5rem; }
    div[data-testid="stMetric"] {
        background: #1E293B;
        border: 1px solid #334155;
        border-radius: 8px;
        padding: 0.75rem;
    }
    div[data-testid="stMetric"] label { color: #94A3B8 !important; }
    div[data-testid="stMetric"] [data-testid="stMetricValue"] { color: #F8FAFC !important; }
</style>
"""
st.markdown(DARK_CSS, unsafe_allow_html=True)


def push_profile_to_session(profile: dict, display_name: str) -> None:
    """Inject profile values into Streamlit session state for all widgets."""
    is_known = profile.get("_known", False)
    clean = apply_profile(profile, display_name)
    for key in PROFILE_KEYS:
        if key in clean:
            st.session_state[key] = clean[key]
    st.session_state["_active_profile"] = display_name
    st.session_state["_profile_known"] = is_known


# ---------------------------------------------------------------------------
# Sidebar — grouped AIV input taxonomy
# ---------------------------------------------------------------------------

def render_sidebar() -> tuple[ScadaInputs, LabFluidTraits, ChemistryControls, PhysicalInspection, dict]:
    """Render expanding sidebar sections and return typed input bundles."""

    st.sidebar.markdown("## 🌍 Global Asset Search")
    st.sidebar.caption("ogcorrosion.org · Worldwide field integrity twin")

    # Dynamic text search — replaces hardcoded dropdown
    search_query = st.sidebar.text_input(
        "🔍 Type Oil Field or Asset Name",
        key="field_search_query",
        placeholder="e.g. Ghawar, Brent, Sabriyah, Rumaila…",
    )

    # Resolve search on query change
    last_query = st.session_state.get("_last_search_query", "")
    if search_query != last_query:
        profile, display_name, is_known = resolve_field_search(search_query)
        profile["_known"] = is_known
        push_profile_to_session(profile, display_name)
        st.session_state["_last_search_query"] = search_query
        st.session_state["_profile_known"] = is_known

    # Initialize session on first load
    if "_active_profile" not in st.session_state:
        profile, display_name, is_known = resolve_field_search("")
        profile["_known"] = is_known
        push_profile_to_session(profile, display_name)
        st.session_state["_last_search_query"] = search_query

    # Alert for unknown / new assets
    if search_query.strip() and not st.session_state.get("_profile_known", False):
        st.sidebar.info(
            "ℹ️ **New Asset Profile Detected.** Defaulting to standard global baseline. "
            "Please adjust fluid parameters using the sliders below."
        )
    elif st.session_state.get("_profile_known", False):
        st.sidebar.success(
            f"✅ Matched global database: **{st.session_state.get('_active_profile', '')}**"
        )

    # CSV template download & upload
    st.sidebar.download_button(
        label="📥 Download Sample CSV Template",
        data=get_csv_template_bytes(),
        file_name="ogcorrosion_field_laboratory_template.csv",
        mime="text/csv",
        help="Format your water cut, CO₂, H₂S, and operating data using this template.",
    )

    uploaded_csv = st.sidebar.file_uploader(
        "📤 Upload Field Laboratory Report (.CSV)",
        type=["csv"],
        help="Upload a completed template to overwrite engine variables securely client-side.",
    )

    if uploaded_csv is not None:
        csv_bytes = uploaded_csv.getvalue()
        last_upload_id = st.session_state.get("_last_csv_id")
        current_id = f"{uploaded_csv.name}:{len(csv_bytes)}"

        if current_id != last_upload_id:
            overrides, field_name, csv_warnings = parse_laboratory_csv(csv_bytes)
            base: dict = {}
            for key in PROFILE_KEYS:
                if key in st.session_state:
                    base[key] = st.session_state[key]
            merged = merge_profile_with_upload(base, overrides, field_name)
            push_profile_to_session(merged, field_name)
            st.session_state["_last_csv_id"] = current_id
            st.session_state["_profile_known"] = True
            st.session_state["field_search_query"] = field_name
            st.session_state["_last_search_query"] = field_name

            st.sidebar.success(f"📤 Laboratory report loaded for **{field_name}**")
            for warn in csv_warnings:
                st.sidebar.warning(warn)

    st.sidebar.markdown("---")
    st.sidebar.markdown("## ⚙️ Digital Twin Inputs")

    with st.sidebar.expander("📡 Real-Time SCADA Streams", expanded=True):
        pressure = st.slider(
            "Tubing Head Pressure (psi)",
            min_value=500, max_value=6000, step=50,
            key="pressure",
            help="Live SCADA THP — drives CO2/H2S partial pressures at each node.",
        )
        temperature = st.slider(
            "Wellhead Temperature (°C)",
            min_value=40, max_value=150, step=1,
            key="temperature",
            help="Downhole / wellhead temperature for Arrhenius corrosion kinetics.",
        )
        velocity = st.slider(
            "Fluid Velocity (m/s)",
            min_value=0.5, max_value=12.0, step=0.1,
            key="velocity",
            help="Superficial velocity — triggers erosion-corrosion above 6 m/s.",
        )

    with st.sidebar.expander("🧪 Daily Laboratory Fluid Traits", expanded=True):
        water_cut = st.slider(
            "Water Cut (%)",
            min_value=0, max_value=95, step=1,
            key="water_cut",
            help="Volumetric water cut from production test separator.",
        )
        gor = st.slider(
            "Gas-Oil Ratio (SCF/BBL)",
            min_value=100, max_value=3000, step=50,
            key="gor",
            help="GOR affects gas breakout and top-of-line corrosion at surface.",
        )
        co2 = st.slider(
            "CO₂ (mol %)",
            min_value=0.0, max_value=15.0, step=0.5,
            key="co2",
            help="Sweet corrosion driver — de Waard CO2 partial pressure model.",
        )
        h2s = st.slider(
            "H₂S (ppm)",
            min_value=0.0, max_value=50.0, step=0.5,
            key="h2s",
            help="Sour service indicator — pitting risk above 0.05 bar pH2S + WC>30%.",
        )

    with st.sidebar.expander("💊 Production Chemistry Controls", expanded=False):
        inhibitor_dose = st.slider(
            "Inhibitor Dosage (ppm)",
            min_value=0, max_value=200, step=5,
            key="inhibitor_dose",
            help="Filming amine injection rate at wellhead chemical skid.",
        )
        chem_cost = st.number_input(
            "Chemical Cost ($/L)",
            min_value=1.0, max_value=100.0, step=0.50,
            key="chem_cost",
            help="Unit cost for ROI over-injection waste calculation.",
        )
        inhibitor_eff = st.slider(
            "Inhibitor Efficiency (%)",
            min_value=0, max_value=100, step=5,
            key="inhibitor_eff",
            help="Laboratory coupon test verified inhibitor film efficiency.",
        )

    with st.sidebar.expander("🔬 Physical Inspection / Reconciliation", expanded=False):
        use_physical = st.toggle(
            "Enable Physical Inspection Data",
            key="use_physical",
            help="Toggle UT / ILI wall thickness for model calibration.",
        )
        measured_wall = None
        inspection_method = "Ultrasonic Testing (UT)"
        operating_days = 365.0

        if use_physical:
            inspection_method = st.selectbox(
                "Inspection Method",
                ["Ultrasonic Testing (UT)", "Intelligent Pigging (ILI)", "ROV Visual + UT"],
            )
            measured_wall = st.number_input(
                "Measured Wall Thickness (mm)",
                min_value=1.0, max_value=15.0, step=0.1,
                key="measured_wall",
                help="Latest field measurement at worst-case node.",
            )
            operating_days = st.slider(
                "Days Since Last Inspection",
                min_value=30, max_value=3650, step=30,
                key="operating_days",
            )

    production_bpd = st.sidebar.number_input(
        "Production Rate (BPD)", min_value=100, max_value=50000, step=100,
        key="production_bpd",
    )
    critical_days = st.sidebar.slider(
        "Critical Risk Duration (days)", min_value=0, max_value=180, step=5,
        key="critical_days",
        help="Days any node has remained in Critical status for exposure cost calc.",
    )

    st.sidebar.caption(f"Active asset: **{st.session_state.get('_active_profile', 'Global Baseline')}**")

    scada = ScadaInputs(pressure_psi=pressure, temperature_c=temperature, flow_velocity_m_s=velocity)
    lab = LabFluidTraits(water_cut_pct=water_cut, gor_scf_bbl=gor, co2_mol_pct=co2, h2s_ppm=h2s)
    chemistry = ChemistryControls(
        inhibitor_dosage_ppm=inhibitor_dose,
        chemical_cost_per_liter_usd=chem_cost,
        inhibitor_efficiency_pct=inhibitor_eff,
    )
    physical = PhysicalInspection(
        measured_wall_thickness_mm=measured_wall if use_physical else None,
        method=inspection_method,
    )
    extras = {
        "operating_days": operating_days,
        "production_bpd": production_bpd,
        "critical_days": critical_days,
        "use_physical": use_physical,
    }

    return scada, lab, chemistry, physical, extras


def health_badge_class(status: HealthStatus) -> str:
    """Map health enum to CSS badge class."""
    mapping = {
        HealthStatus.HEALTHY: "badge-healthy",
        HealthStatus.WATCH: "badge-watch",
        HealthStatus.ELEVATED: "badge-elevated",
        HealthStatus.CRITICAL: "badge-critical",
    }
    return mapping.get(status, "badge-healthy")


def node_card_class(status: HealthStatus) -> str:
    """Map health enum to node card border class."""
    mapping = {
        HealthStatus.HEALTHY: "healthy",
        HealthStatus.WATCH: "watch",
        HealthStatus.ELEVATED: "elevated",
        HealthStatus.CRITICAL: "critical",
    }
    return mapping.get(status, "healthy")


def render_node_card(node) -> None:
    """Render a single nodal integrity card."""
    card_cls = node_card_class(node.health_status)
    badge_cls = health_badge_class(node.health_status)

    warnings = ""
    if node.erosion_corrosion_warning:
        warnings += '<div class="warning-flag">⚠ Erosion-Corrosion</div>'
    if node.h2s_pitting_active:
        warnings += '<div class="warning-flag">⚠ H₂S Pitting Risk</div>'

    st.markdown(f"""
    <div class="node-card {card_cls}">
        <div class="node-name">{node.display_name}</div>
        <div class="node-rate">{node.calibrated_rate_mm_yr:.3f}</div>
        <div style="font-size:0.65rem;color:#64748B;">mm/yr</div>
        <div class="node-rul">RUL: {node.remaining_useful_life_yr:.1f} years</div>
        <div style="font-size:0.6rem;color:#475569;margin-top:0.3rem;">
            CO₂: {node.co2_component_mm_yr:.3f} | H₂S: {node.h2s_component_mm_yr:.3f} | EC: {node.erosion_component_mm_yr:.3f}
        </div>
        <div class="health-badge {badge_cls}">{node.health_status.value}</div>
        {warnings}
    </div>
    """, unsafe_allow_html=True)


def render_pipeline(nodes) -> None:
    """Render downstream nodal network with visual connectors."""
    st.markdown('<div class="section-header">🔗 Downstream Integrity Network</div>', unsafe_allow_html=True)
    st.caption("Reservoir → Tubing → Choke → Flowline → GC Header")

    cols = st.columns([3, 1, 3, 1, 3, 1, 3, 1, 3])
    for i, node in enumerate(nodes):
        col_idx = i * 2
        with cols[col_idx]:
            render_node_card(node)
        if i < len(nodes) - 1:
            with cols[col_idx + 1]:
                st.markdown('<div class="pipeline-arrow">➔</div>', unsafe_allow_html=True)


def render_reconciliation(assessment) -> None:
    """Render physical vs. virtual reconciliation panel."""
    st.markdown('<div class="section-header">🔬 Physical vs. Virtual Reconciliation</div>', unsafe_allow_html=True)

    if assessment.reconciliation is None:
        st.info(
            "Enable **Physical Inspection Data** in the sidebar to calibrate "
            "theoretical corrosion predictions against UT / ILI wall thickness logs."
        )
        return

    rec = assessment.reconciliation
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Theoretical Wall (mm)", f"{rec.theoretical_wall_mm:.2f}")
    c2.metric("Measured Wall (mm)", f"{rec.measured_wall_mm:.2f}")
    c3.metric("Delta (mm)", f"{rec.delta_mm:+.2f}")
    c4.metric("Calibration Factor", f"{rec.calibration_factor:.3f}")

    if rec.calibration_factor > 1.05:
        st.warning(
            f"Model **under-predicts** corrosion by {rec.model_bias_pct:.1f}%. "
            f"Calibration factor {rec.calibration_factor:.2f}× applied to all nodes."
        )
    elif rec.calibration_factor < 0.95:
        st.success(
            f"Model **over-predicts** by {abs(rec.model_bias_pct):.1f}%. "
            f"Downward calibration {rec.calibration_factor:.2f}× applied."
        )
    else:
        st.success("Model aligned with physical inspection within ±5% tolerance.")


def render_roi(assessment) -> None:
    """Render business intelligence / ROI dashboard."""
    st.markdown('<div class="section-header">💰 Business Intelligence & ROI Dashboard</div>', unsafe_allow_html=True)
    st.caption("KOC Operational Manager — OPEX Optimization & Risk Exposure")

    roi = assessment.roi
    if roi is None:
        return

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-value" style="color:#F87171;">${roi.chemical_over_injection_waste_usd:,.0f}</div>
            <div class="kpi-label">Chemical Over-injection Waste / yr</div>
        </div>
        """, unsafe_allow_html=True)

    with c2:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-value" style="color:#FB923C;">${roi.risk_exposure_cost_usd:,.0f}</div>
            <div class="kpi-label">Risk Exposure Cost</div>
        </div>
        """, unsafe_allow_html=True)

    with c3:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-value">${roi.optimized_opex_savings_usd:,.0f}</div>
            <div class="kpi-label">Optimized OPEX Savings</div>
        </div>
        """, unsafe_allow_html=True)

    with c4:
        st.markdown(f"""
        <div class="kpi-card">
            <div class="kpi-value" style="color:#60A5FA;">{roi.inhibitor_utilization_pct:.0f}%</div>
            <div class="kpi-label">Inhibitor Utilization</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown(
        "**ROI Narrative for Steering Committee:** "
        f"At current chemical dosing, the twin identifies **${roi.chemical_over_injection_waste_usd:,.0f}/yr** "
        f"in avoidable inhibitor spend. Deferred intervention on elevated nodes saves an estimated "
        f"**${roi.optimized_opex_savings_usd:,.0f}/yr** versus reactive workover strategy. "
        f"Critical-risk exposure stands at **${roi.risk_exposure_cost_usd:,.0f}** "
        f"if integrity breaches persist beyond {roi.critical_node_days} days."
    )


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

def main() -> None:
    st.markdown('<div class="aiv-badge">Global Asset Integrity · SLB AIV Framework</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="main-title">ogcorrosion.org | Integrated Integrity Digital Twin (AIV Framework)</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="sub-title">Predictive downhole-to-surface asset integrity · '
        'Sweet &amp; sour multiphase corrosion · Physical reconciliation · ROI optimization</div>',
        unsafe_allow_html=True,
    )

    scada, lab, chemistry, physical, extras = render_sidebar()

    assessment = run_full_assessment(
        scada=scada,
        lab=lab,
        chemistry=chemistry,
        physical=physical if extras["use_physical"] else None,
        operating_days=extras["operating_days"],
        production_rate_bpd=extras["production_bpd"],
        critical_days=extras["critical_days"],
    )

    # System-level partial pressures
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("pCO₂ (bar)", f"{assessment.system_co2_partial_pressure_bar:.3f}")
    m2.metric("pH₂S (bar)", f"{assessment.system_h2s_partial_pressure_bar:.4f}")
    m3.metric("Calibration Factor", f"{assessment.calibration_factor:.3f}")
    m4.metric("Water Cut (%)", f"{lab.water_cut_pct:.0f}")

    render_pipeline(assessment.nodes)
    render_reconciliation(assessment)
    render_roi(assessment)

    # Audit trail expander for SLB technical review
    with st.expander("📋 Engineering Audit Trail — Equation Reference"):
        st.markdown("""
        | Mechanism | Model Basis | Key Threshold |
        |-----------|-------------|---------------|
        | Sweet CO₂ | de Waard-Milliams pCO₂^0.67 × f(T) × f(WC) | WC > 30% → exponential wetting |
        | Sour H₂S | NACE MR0175 pH₂S pitting | pH₂S > 0.05 bar + WC > 30% |
        | Erosion-Corrosion | τ ∝ v² shear stress proxy | v > 6 m/s → film stripping |
        | Inhibitor | Filming amine efficiency saturation | > 50 ppm diminishing returns |
        | Reconciliation | CF = Δt_actual / Δt_predicted | Applied to all nodal rates |
        | RUL | (t_nominal − t_MAWT) / CR_calibrated | 10 mm nominal, 3 mm MAWT |
        """)

        for node in assessment.nodes:
            st.markdown(
                f"**{node.display_name}**: CR={node.calibrated_rate_mm_yr:.4f} mm/yr | "
                f"RUL={node.remaining_useful_life_yr:.1f} yr | "
                f"CO₂={node.co2_component_mm_yr:.4f} | H₂S={node.h2s_component_mm_yr:.4f} | "
                f"EC={node.erosion_component_mm_yr:.4f} | "
                f"EC Warn={'YES' if node.erosion_corrosion_warning else 'NO'} | "
                f"Pitting={'YES' if node.h2s_pitting_active else 'NO'}"
            )


if __name__ == "__main__":
    main()
