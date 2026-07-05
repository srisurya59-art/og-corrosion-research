"""
physics.py — Integrated Downhole-to-Surface Asset Integrity Corrosion Engine
=============================================================================
Petroleum engineering context for SLB AIV / KOC technical audit.

Governing mechanisms modelled:
  1. Sweet (CO2) corrosion  — de Waard / Milliams-style CO2 partial pressure scaling
  2. Sour (H2S) corrosion   — NACE MR0175-inspired pitting risk when pH2S + WC thresholds met
  3. Erosion-corrosion (EC) — shear-stress proxy from fluid velocity (API RP 14E lineage)
  4. Inhibitor mitigation   — filming amine efficiency applied to net metal loss
  5. Physical reconciliation — UT / ILI wall thickness delta calibration factor

Reference units (SI where noted, field units preserved for KOC operations):
  - Pressure: psi (converted to bar for H2S partial pressure)
  - Temperature: °C
  - Corrosion rate: mm/yr
  - Wall thickness budget: mm (default 10 mm nominal carbon steel)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Constants — KOC North Kuwait / Burgan typical operating envelopes
# ---------------------------------------------------------------------------

PSI_TO_BAR = 0.0689476
BASE_WALL_THICKNESS_MM = 10.0          # Nominal CS tubing / flowline design margin
H2S_PITTING_P_H2S_THRESHOLD_BAR = 0.05 # Aggressive localized pitting onset (sour service)
H2S_PITTING_WC_THRESHOLD_PCT = 30.0
EROSION_VELOCITY_THRESHOLD_M_S = 6.0   # EC warning per common field practice
CRITICAL_RISK_RATE_MM_YR = 1.0
CRITICAL_RISK_DAYS_THRESHOLD = 30
DEFAULT_INTERVENTION_COST_USD = 250_000  # Workover / line replacement proxy


class HealthStatus(str, Enum):
    """Operational health badge for nodal network cards."""
    HEALTHY = "Healthy"
    WATCH = "Watch"
    ELEVATED = "Elevated"
    CRITICAL = "Critical Risk"


@dataclass
class ScadaInputs:
    """Real-time SCADA stream parameters."""
    pressure_psi: float = 2500.0
    temperature_c: float = 85.0
    flow_velocity_m_s: float = 3.5


@dataclass
class LabFluidTraits:
    """Daily laboratory fluid characterization."""
    water_cut_pct: float = 25.0
    gor_scf_bbl: float = 600.0
    co2_mol_pct: float = 4.0
    h2s_ppm: float = 5.0


@dataclass
class ChemistryControls:
    """Production chemistry injection setpoints."""
    inhibitor_dosage_ppm: float = 35.0
    chemical_cost_per_liter_usd: float = 12.50
    inhibitor_efficiency_pct: float = 85.0  # Filming amine baseline efficiency


@dataclass
class PhysicalInspection:
    """Latest physical wall thickness from UT / intelligent pigging."""
    measured_wall_thickness_mm: Optional[float] = None
    inspection_date: str = ""
    method: str = "Ultrasonic Testing (UT)"


@dataclass
class NodeDefinition:
    """Downstream integrity node in the production network."""
    node_id: str
    display_name: str
    pressure_factor: float   # Fraction of wellhead pressure at this node
    temperature_factor: float
    velocity_factor: float   # Velocity amplification at restrictions / chokes
    base_multiplier: float   # Geometry / material susceptibility


# Ordered downstream network: Reservoir → GC Header
NETWORK_NODES: list[NodeDefinition] = [
    NodeDefinition("reservoir", "Reservoir / Sandface", 1.00, 1.00, 0.80, 1.20),
    NodeDefinition("tubing", "Downhole Tubing", 0.95, 0.98, 1.00, 1.10),
    NodeDefinition("choke", "Wellhead Choke", 0.55, 0.75, 1.80, 1.25),
    NodeDefinition("flowline", "Flowline", 0.30, 0.55, 1.10, 0.90),
    NodeDefinition("gc_header", "GC Header", 0.15, 0.40, 0.70, 0.75),
]


@dataclass
class NodeResult:
    """Calculated integrity metrics for a single network node."""
    node_id: str
    display_name: str
    corrosion_rate_mm_yr: float
    remaining_useful_life_yr: float
    health_status: HealthStatus
    co2_component_mm_yr: float
    h2s_component_mm_yr: float
    erosion_component_mm_yr: float
    erosion_corrosion_warning: bool
    h2s_pitting_active: bool
    calibrated_rate_mm_yr: float = 0.0


@dataclass
class ReconciliationResult:
    """Physical vs. virtual model calibration output."""
    theoretical_wall_mm: float
    measured_wall_mm: float
    delta_mm: float
    calibration_factor: float
    model_bias_pct: float


@dataclass
class RoiSummary:
    """Business intelligence KPIs for KOC operational managers."""
    chemical_over_injection_waste_usd: float
    risk_exposure_cost_usd: float
    optimized_opex_savings_usd: float
    critical_node_days: int
    inhibitor_utilization_pct: float


@dataclass
class IntegrityAssessment:
    """Full digital twin output bundle."""
    nodes: list[NodeResult] = field(default_factory=list)
    reconciliation: Optional[ReconciliationResult] = None
    roi: Optional[RoiSummary] = None
    system_h2s_partial_pressure_bar: float = 0.0
    system_co2_partial_pressure_bar: float = 0.0
    calibration_factor: float = 1.0


# ---------------------------------------------------------------------------
# Core corrosion physics
# ---------------------------------------------------------------------------

def co2_partial_pressure_bar(co2_mol_pct: float, total_pressure_psi: float) -> float:
    """
    CO2 partial pressure (bar).
    pCO2 = y_CO2 * P_total
    Basis: de Waard-Milliams CO2 corrosion correlation family.
    """
    return (co2_mol_pct / 100.0) * total_pressure_psi * PSI_TO_BAR


def h2s_partial_pressure_bar(h2s_ppm: float, total_pressure_psi: float) -> float:
    """
    H2S partial pressure (bar) from ppm volumetric concentration.
    pH2S = (ppm / 1e6) * P_total
    NACE MR0175 / ISO 15156 sour service screening basis.
    """
    return (h2s_ppm / 1_000_000.0) * total_pressure_psi * PSI_TO_BAR


def sweet_co2_corrosion_rate(
    pco2_bar: float,
    temperature_c: float,
    water_cut_pct: float,
) -> float:
    """
    Sweet (CO2) corrosion rate estimate (mm/yr).

    Simplified de Waard-style temperature and water-wetting scaling:
      CR_CO2 ∝ (pCO2)^0.67 * f(T) * f(WC)

    Water cut drives phase wetting — below 30% WC, metal exposure is
    partially shielded by oil-wetted film; above 30%, aqueous phase
    dominates and exponential acceleration applies (KOC Burgan wet-well trend).
    """
    if pco2_bar <= 0 or water_cut_pct <= 0:
        return 0.0

    temp_factor = math.pow(max(temperature_c, 20.0) / 20.0, 1.3)

    if water_cut_pct > 30.0:
        wc_factor = math.pow(10.0, (water_cut_pct - 30.0) / 30.0)
    else:
        wc_factor = 0.1 + (water_cut_pct / 30.0) * 0.9

    base = 0.005 * math.pow(pco2_bar, 0.67) * temp_factor * wc_factor
    return max(base, 0.0)


def sour_h2s_corrosion_rate(
    ph2s_bar: float,
    water_cut_pct: float,
    temperature_c: float,
) -> tuple[float, bool]:
    """
    Sour (H2S) corrosion contribution (mm/yr) and pitting flag.

    Localized pitting risk activates when:
      pH2S > 0.05 bar AND Water Cut > 30%

    This represents SSC / pitting susceptibility in wet sour service,
    common in KOC deep Marrat / Najmah carbonate sour producers.
    """
    if ph2s_bar <= 0 or water_cut_pct <= 0:
        return 0.0, False

    pitting_active = (
        ph2s_bar > H2S_PITTING_P_H2S_THRESHOLD_BAR
        and water_cut_pct > H2S_PITTING_WC_THRESHOLD_PCT
    )

    # Base H2S film breakdown rate
    h2s_base = 0.003 * math.pow(ph2s_bar, 0.5) * (1.0 + temperature_c / 100.0)

    if pitting_active:
        # Aggressive localized pitting multiplier (audit: NACE TM0177 context)
        h2s_base *= 8.0

    return max(h2s_base, 0.0), pitting_active


def erosion_corrosion_rate(
    velocity_m_s: float,
    water_cut_pct: float,
) -> tuple[float, bool]:
    """
    Erosion-corrosion metal loss contribution (mm/yr).

    Shear stress proxy: τ ∝ ρ * v² (simplified; assumes liquid-dominated flow).
    EC warning triggers when velocity > 6 m/s (field rule-of-thumb for CS).

    High velocity at choke / restriction nodes compounds CO2/H2S attack
    by continuously removing protective iron carbonate / sulfide films.
    """
    warning = velocity_m_s > EROSION_VELOCITY_THRESHOLD_M_S

    if velocity_m_s <= 1.0:
        return 0.0, warning

    # Velocity-squared scaling with water-cut amplification
    wc_amp = 1.0 + (water_cut_pct / 100.0)
    ec_rate = 0.0008 * math.pow(velocity_m_s, 2.2) * wc_amp

    if warning:
        ec_rate *= 2.5  # Film stripping compounding factor

    return max(ec_rate, 0.0), warning


def apply_inhibitor_mitigation(
    gross_rate_mm_yr: float,
    dosage_ppm: float,
    efficiency_pct: float,
) -> float:
    """
    Reduce gross corrosion rate by filming inhibitor efficiency.

    Efficiency saturates — overdosing beyond 50 ppm yields diminishing returns
    (basis for chemical over-injection waste calculation in ROI module).
    """
    if gross_rate_mm_yr <= 0:
        return 0.0

    # Dosage effectiveness curve: linear up to 50 ppm, then logarithmic saturation
    if dosage_ppm <= 50.0:
        dosage_factor = dosage_ppm / 50.0
    else:
        dosage_factor = 1.0 + 0.15 * math.log1p((dosage_ppm - 50.0) / 10.0)

    effective_efficiency = min(efficiency_pct / 100.0 * dosage_factor, 0.98)
    return gross_rate_mm_yr * (1.0 - effective_efficiency)


def classify_health_status(rate_mm_yr: float) -> HealthStatus:
    """Map corrosion rate to operational health badge."""
    if rate_mm_yr >= CRITICAL_RISK_RATE_MM_YR:
        return HealthStatus.CRITICAL
    if rate_mm_yr >= 0.5:
        return HealthStatus.ELEVATED
    if rate_mm_yr >= 0.2:
        return HealthStatus.WATCH
    return HealthStatus.HEALTHY


def remaining_useful_life_years(
    corrosion_rate_mm_yr: float,
    wall_thickness_mm: float = BASE_WALL_THICKNESS_MM,
    minimum_allowable_mm: float = 3.0,
) -> float:
    """
    RUL (years) = (t_nominal - t_MAWT) / CR

    MAWT = 3 mm default (API 5CT tubing corrosion allowance proxy).
    Returns inf-like large number if rate is negligible.
    """
    if corrosion_rate_mm_yr <= 1e-6:
        return 999.0

    available_metal = max(wall_thickness_mm - minimum_allowable_mm, 0.1)
    return round(available_metal / corrosion_rate_mm_yr, 1)


# ---------------------------------------------------------------------------
# Nodal network assessment
# ---------------------------------------------------------------------------

def assess_node(
    node: NodeDefinition,
    scada: ScadaInputs,
    lab: LabFluidTraits,
    chemistry: ChemistryControls,
    calibration_factor: float = 1.0,
) -> NodeResult:
    """Compute integrity metrics for one downstream network node."""
    node_pressure = scada.pressure_psi * node.pressure_factor
    node_temperature = scada.temperature_c * node.temperature_factor
    node_velocity = scada.flow_velocity_m_s * node.velocity_factor

    pco2 = co2_partial_pressure_bar(lab.co2_mol_pct, node_pressure)
    ph2s = h2s_partial_pressure_bar(lab.h2s_ppm, node_pressure)

    co2_rate = sweet_co2_corrosion_rate(pco2, node_temperature, lab.water_cut_pct)
    h2s_rate, pitting = sour_h2s_corrosion_rate(ph2s, lab.water_cut_pct, node_temperature)
    ec_rate, ec_warning = erosion_corrosion_rate(node_velocity, lab.water_cut_pct)

    # GOR increases CO2 flux at surface facilities (gas breakout)
    gor_factor = 1.0 + max((lab.gor_scf_bbl - 150.0) / 2350.0, 0.0) * 0.5

    gross_rate = (co2_rate + h2s_rate + ec_rate) * node.base_multiplier * gor_factor
    net_rate = apply_inhibitor_mitigation(
        gross_rate,
        chemistry.inhibitor_dosage_ppm,
        chemistry.inhibitor_efficiency_pct,
    )
    calibrated_rate = net_rate * calibration_factor

    return NodeResult(
        node_id=node.node_id,
        display_name=node.display_name,
        corrosion_rate_mm_yr=round(net_rate, 4),
        calibrated_rate_mm_yr=round(calibrated_rate, 4),
        remaining_useful_life_yr=remaining_useful_life_years(calibrated_rate),
        health_status=classify_health_status(calibrated_rate),
        co2_component_mm_yr=round(co2_rate * node.base_multiplier, 4),
        h2s_component_mm_yr=round(h2s_rate * node.base_multiplier, 4),
        erosion_component_mm_yr=round(ec_rate * node.base_multiplier, 4),
        erosion_corrosion_warning=ec_warning,
        h2s_pitting_active=pitting,
    )


def run_network_assessment(
    scada: ScadaInputs,
    lab: LabFluidTraits,
    chemistry: ChemistryControls,
    calibration_factor: float = 1.0,
) -> list[NodeResult]:
    """Evaluate all nodes in the downstream integrity network."""
    return [
        assess_node(node, scada, lab, chemistry, calibration_factor)
        for node in NETWORK_NODES
    ]


# ---------------------------------------------------------------------------
# Physical vs. virtual reconciliation
# ---------------------------------------------------------------------------

def reconcile_physical_inspection(
    theoretical_rate_mm_yr: float,
    operating_days: float,
    measured_wall_mm: float,
    nominal_wall_mm: float = BASE_WALL_THICKNESS_MM,
) -> ReconciliationResult:
    """
    Calibrate theoretical model against physical UT / ILI measurement.

    Theoretical remaining wall:
      t_theory = t_nominal - (CR_theory * t_operation_years)

    Calibration factor:
      CF = (t_nominal - t_measured) / (t_nominal - t_theory)

    CF > 1 → model under-predicts corrosion (apply upward correction)
    CF < 1 → model over-predicts (apply downward correction)
    """
    operation_years = operating_days / 365.0
    theoretical_wall = nominal_wall_mm - (theoretical_rate_mm_yr * operation_years)
    theoretical_wall = max(theoretical_wall, 0.0)

    delta = measured_wall_mm - theoretical_wall

    predicted_loss = nominal_wall_mm - theoretical_wall
    actual_loss = nominal_wall_mm - measured_wall_mm

    if predicted_loss > 0.01:
        calibration_factor = actual_loss / predicted_loss
    else:
        calibration_factor = 1.0

    calibration_factor = max(0.1, min(calibration_factor, 5.0))

    bias_pct = (
        ((theoretical_wall - measured_wall_mm) / measured_wall_mm) * 100.0
        if measured_wall_mm > 0
        else 0.0
    )

    return ReconciliationResult(
        theoretical_wall_mm=round(theoretical_wall, 3),
        measured_wall_mm=round(measured_wall_mm, 3),
        delta_mm=round(delta, 3),
        calibration_factor=round(calibration_factor, 3),
        model_bias_pct=round(bias_pct, 2),
    )


# ---------------------------------------------------------------------------
# Business intelligence / ROI
# ---------------------------------------------------------------------------

def calculate_roi_summary(
    nodes: list[NodeResult],
    chemistry: ChemistryControls,
    production_rate_bpd: float = 5000.0,
    critical_days: int = 30,
) -> RoiSummary:
    """
    Financial impact model for KOC operational managers.

    1. Chemical Over-injection Waste:
       If inhibitor is dosed at full efficiency but corrosion risk is baseline
       (all nodes Healthy), excess chemical spend above minimum effective dose.

    2. Risk Exposure Cost:
       Estimated intervention cost if any node remains Critical for > 30 days.

    3. Optimized OPEX Savings:
       Savings from right-sized chemical dosing + deferred intervention via
       early warning (Watch/Elevated nodes addressed before Critical).
    """
    all_healthy = all(n.health_status == HealthStatus.HEALTHY for n in nodes)
    critical_nodes = [n for n in nodes if n.health_status == HealthStatus.CRITICAL]
    elevated_nodes = [n for n in nodes if n.health_status in (HealthStatus.ELEVATED, HealthStatus.WATCH)]

    # Chemical cost: assume 1 L treats ~1000 BBL (field rule of thumb)
    daily_volume_bbl = production_rate_bpd
    liters_per_day = daily_volume_bbl / 1000.0
    daily_chemical_cost = liters_per_day * chemistry.chemical_cost_per_liter_usd * (chemistry.inhibitor_dosage_ppm / 35.0)

    min_effective_dose_ppm = 15.0
    if all_healthy and chemistry.inhibitor_dosage_ppm > min_effective_dose_ppm:
        waste_fraction = (chemistry.inhibitor_dosage_ppm - min_effective_dose_ppm) / chemistry.inhibitor_dosage_ppm
        chemical_waste = daily_chemical_cost * waste_fraction * 365.0
    else:
        chemical_waste = 0.0

    # Risk exposure: critical nodes × intervention cost prorated by RUL breach
    risk_exposure = len(critical_nodes) * DEFAULT_INTERVENTION_COST_USD
    if critical_days > CRITICAL_RISK_DAYS_THRESHOLD:
        risk_exposure *= 1.0 + (critical_days - CRITICAL_RISK_DAYS_THRESHOLD) / 30.0

    # OPEX savings: early intervention on elevated nodes avoids 60% of workover cost
    deferred_savings = len(elevated_nodes) * DEFAULT_INTERVENTION_COST_USD * 0.60
    chemical_rightsizing = chemical_waste * 0.75
    optimized_savings = deferred_savings + chemical_rightsizing

    inhibitor_util = min(
        (chemistry.inhibitor_efficiency_pct / 100.0)
        * min(chemistry.inhibitor_dosage_ppm / 35.0, 1.5)
        * 100.0,
        100.0,
    )

    return RoiSummary(
        chemical_over_injection_waste_usd=round(chemical_waste, 0),
        risk_exposure_cost_usd=round(risk_exposure, 0),
        optimized_opex_savings_usd=round(optimized_savings, 0),
        critical_node_days=critical_days,
        inhibitor_utilization_pct=round(inhibitor_util, 1),
    )


def run_full_assessment(
    scada: ScadaInputs,
    lab: LabFluidTraits,
    chemistry: ChemistryControls,
    physical: Optional[PhysicalInspection] = None,
    operating_days: float = 365.0,
    production_rate_bpd: float = 5000.0,
    critical_days: int = 30,
) -> IntegrityAssessment:
    """
    Master entry point — runs network assessment, optional reconciliation,
    and ROI calculation. Called by app.py Streamlit UI.
    """
    # Initial pass (uncalibrated)
    initial_nodes = run_network_assessment(scada, lab, chemistry)
    max_rate_node = max(initial_nodes, key=lambda n: n.corrosion_rate_mm_yr)

    calibration_factor = 1.0
    reconciliation = None

    if physical and physical.measured_wall_thickness_mm is not None:
        reconciliation = reconcile_physical_inspection(
            max_rate_node.corrosion_rate_mm_yr,
            operating_days,
            physical.measured_wall_thickness_mm,
        )
        calibration_factor = reconciliation.calibration_factor

    calibrated_nodes = run_network_assessment(scada, lab, chemistry, calibration_factor)
    roi = calculate_roi_summary(calibrated_nodes, chemistry, production_rate_bpd, critical_days)

    return IntegrityAssessment(
        nodes=calibrated_nodes,
        reconciliation=reconciliation,
        roi=roi,
        system_h2s_partial_pressure_bar=round(
            h2s_partial_pressure_bar(lab.h2s_ppm, scada.pressure_psi), 4
        ),
        system_co2_partial_pressure_bar=round(
            co2_partial_pressure_bar(lab.co2_mol_pct, scada.pressure_psi), 4
        ),
        calibration_factor=calibration_factor,
    )
