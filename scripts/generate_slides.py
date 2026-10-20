"""
scripts/generate_slides.py
Oral Defense Presentation Deck Generator for Component 2 (NWSDB Water Fraud Surveillance)
Generates reports/Component2_Viva_Presentation.pptx using python-pptx.

12-Slide Executive & Technical Structure:
  Slide 1: Title, Author, University & NWSDB Kaduwela Research Context
  Slide 2: Problem Statement: The IWS Non-Revenue Water Challenge & Failure of Household Meters
  Slide 3: Digital Twin Formulation: EPANET/WNTR PDD Simulation & Kaduwela DMA 01/02 Layout
  Slide 4: Feature Engineering: Hydraulic Residuals, Temporal Recurrence, Spatial Gradients
  Slide 5: AI Architecture: Stage 1 (Isolation Forest) + Stage 2 (Random Forest)
  Slide 6: 0-100 Fraud Risk Engine & IWS Morning Refill Transient Filter
  Slide 7: Confusion Matrix & Quantitative Benchmark Results
  Slide 8: Cross-Component Ecosystem Integration (C1, C3, and C4 Interfacing)
  Slide 9: React Decision-Support Dashboard & Geo-Spatial Inspection Dispatch
  Slide 10: Field Telemetry Resilience & Edge Gateway Architecture
  Slide 11: Limitations, Ethical Boundaries (Decision-Support vs. Accusation), and Future Enhancements
  Slide 12: Live Demonstration Script & Conclusion

Automatically embeds high-resolution publication figures from reports/figures/
into designated slide layouts.
"""

import argparse
import logging
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple, Union

# Ensure UTF-8 output on Windows terminals
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("generate_slides")

REPORTS_DIR = PROJECT_ROOT / "reports"
FIGURES_DIR = REPORTS_DIR / "figures"
DEFAULT_OUTPUT_PPTX = REPORTS_DIR / "Component2_Viva_Presentation.pptx"


# ==============================================================================
# Theme Color Palette & Typographic Constants
# ==============================================================================
class Theme:
    # Dominant Deep Navy & Slate
    BG_DARK = RGBColor(15, 23, 42)        # #0f172a (Title / Dark Slide)
    BG_LIGHT = RGBColor(248, 250, 252)    # #f8fafc (Clean Light Content)
    CARD_BG = RGBColor(255, 255, 255)     # #ffffff (White Card Shape)
    CARD_BG_MUTED = RGBColor(241, 245, 249) # #f1f5f9
    BORDER_LIGHT = RGBColor(226, 232, 240) # #e2e8f0

    # Primary Accents
    PRIMARY_BLUE = RGBColor(2, 132, 199)  # #0284c7 (NWSDB Cyan/Blue)
    PRIMARY_DARK = RGBColor(30, 41, 59)   # #1e293b (Slate Header Text)
    ACCENT_CYAN = RGBColor(56, 189, 248)  # #38bdf8 (Glow Cyan)
    ACCENT_GREEN = RGBColor(16, 185, 129) # #10b981 (Verified / Normal)
    ACCENT_AMBER = RGBColor(245, 158, 11) # #f59e0b (Warning / Warning)
    ACCENT_RED = RGBColor(239, 68, 68)    # #ef4444 (Critical / Theft)
    TEXT_MUTED = RGBColor(100, 116, 139)  # #64748b (Subtitle Slate)

    FONT_TITLE = "Calibri"
    FONT_BODY = "Calibri"


# ==============================================================================
# Slide Builder Helper Utilities
# ==============================================================================
def create_widescreen_presentation() -> Presentation:
    """Initializes a 16:9 widescreen PowerPoint presentation."""
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    return prs


def add_solid_background(slide, color: RGBColor) -> None:
    """Fills slide background with a solid color."""
    bg = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(7.5)
    )
    bg.fill.solid()
    bg.fill.fore_color.rgb = color
    bg.line.fill.background()  # No border


def add_slide_header(
    slide,
    title_text: str,
    category_text: str = "NWSDB WATERGUARD (COMPONENT 2) -- ORAL VIVA DEFENSE",
    slide_num: str = "01/12",
) -> None:
    """Renders consistent executive header banner with title and metadata."""
    # Top Category Tracker
    cat_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.4), Inches(10.0), Inches(0.35))
    tf_c = cat_box.text_frame
    tf_c.word_wrap = True
    tf_c.margin_left = tf_c.margin_right = tf_c.margin_top = tf_c.margin_bottom = 0
    p_c = tf_c.paragraphs[0]
    p_c.text = category_text.upper()
    p_c.font.name = Theme.FONT_TITLE
    p_c.font.size = Pt(10)
    p_c.font.bold = True
    p_c.font.color.rgb = Theme.PRIMARY_BLUE

    # Slide Number Right Alignment
    num_box = slide.shapes.add_textbox(Inches(11.0), Inches(0.4), Inches(1.533), Inches(0.35))
    tf_n = num_box.text_frame
    tf_n.margin_left = tf_n.margin_right = tf_n.margin_top = tf_n.margin_bottom = 0
    p_n = tf_n.paragraphs[0]
    p_n.alignment = PP_ALIGN.RIGHT
    p_n.text = f"SLIDE {slide_num}"
    p_n.font.name = Theme.FONT_TITLE
    p_n.font.size = Pt(10)
    p_n.font.bold = True
    p_n.font.color.rgb = Theme.TEXT_MUTED

    # Main Action Title
    title_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.72), Inches(11.733), Inches(0.65))
    tf_t = title_box.text_frame
    tf_t.word_wrap = True
    tf_t.margin_left = tf_t.margin_right = tf_t.margin_top = tf_t.margin_bottom = 0
    p_t = tf_t.paragraphs[0]
    p_t.text = title_text
    p_t.font.name = Theme.FONT_TITLE
    p_t.font.size = Pt(21)
    p_t.font.bold = True
    p_t.font.color.rgb = Theme.PRIMARY_DARK

    # Bottom Utility Watermark
    footer_box = slide.shapes.add_textbox(Inches(0.8), Inches(7.08), Inches(11.733), Inches(0.3))
    tf_f = footer_box.text_frame
    tf_f.margin_left = tf_f.margin_right = tf_f.margin_top = tf_f.margin_bottom = 0
    p_f = tf_f.paragraphs[0]
    p_f.text = "National Water Supply and Drainage Board (NWSDB) | Kaduwela Water Supply Scheme (DMA 01 & DMA 02) | Component 2"
    p_f.font.name = Theme.FONT_BODY
    p_f.font.size = Pt(9)
    p_f.font.color.rgb = Theme.TEXT_MUTED


def add_card(
    slide,
    left: float,
    top: float,
    width: float,
    height: float,
    bg_color: RGBColor = Theme.CARD_BG,
    border_color: RGBColor = Theme.BORDER_LIGHT,
):
    """Adds a rounded rectangle card container for structured content."""
    shape = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE,
        Inches(left),
        Inches(top),
        Inches(width),
        Inches(height),
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = bg_color
    if border_color:
        shape.line.color.rgb = border_color
        shape.line.width = Pt(1.2)
    else:
        shape.line.fill.background()
    return shape


def add_bullet_list(
    slide,
    left: float,
    top: float,
    width: float,
    height: float,
    items: List[Tuple[str, str]],
    title: Optional[str] = None,
    font_size: int = 12,
):
    """
    Renders structured bold-prefix bullet points inside a defined text bounding box.
    items format: [(bold_prefix, regular_text), ...]
    """
    tx_box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = tx_box.text_frame
    tf.word_wrap = True
    tf.margin_left = Inches(0.15)
    tf.margin_right = Inches(0.15)
    tf.margin_top = Inches(0.12)
    tf.margin_bottom = Inches(0.12)

    para_idx = 0
    if title:
        p_title = tf.paragraphs[0]
        p_title.text = title
        p_title.font.name = Theme.FONT_TITLE
        p_title.font.size = Pt(font_size + 3)
        p_title.font.bold = True
        p_title.font.color.rgb = Theme.PRIMARY_BLUE
        p_title.space_after = Pt(8)
        para_idx = 1

    for i, (prefix, text) in enumerate(items):
        if para_idx == 0 and i == 0:
            p = tf.paragraphs[0]
        else:
            p = tf.add_paragraph()

        p.space_after = Pt(7)
        p.space_before = Pt(2)

        # Bold Lead-in
        r1 = p.add_run()
        r1.text = f"•  {prefix}: " if prefix else "•  "
        r1.font.name = Theme.FONT_BODY
        r1.font.bold = True
        r1.font.size = Pt(font_size)
        r1.font.color.rgb = Theme.PRIMARY_DARK

        # Supporting text
        r2 = p.add_run()
        r2.text = text
        r2.font.name = Theme.FONT_BODY
        r2.font.bold = False
        r2.font.size = Pt(font_size)
        r2.font.color.rgb = RGBColor(51, 65, 85)


def add_image_safe(
    slide,
    image_path: Union[str, Path],
    left: float,
    top: float,
    width: Optional[float] = None,
    height: Optional[float] = None,
    caption: Optional[str] = None,
) -> bool:
    """Embeds high-resolution image into slide with an optional caption."""
    path = Path(image_path)
    if not path.exists():
        logger.warning(f"Image not found for slide embed: {path}")
        # Add visual placeholder card
        add_card(slide, left, top, width or 5.0, height or 4.0, bg_color=Theme.CARD_BG_MUTED)
        box = slide.shapes.add_textbox(Inches(left), Inches(top + (height or 4.0)/2 - 0.5), Inches(width or 5.0), Inches(1.0))
        p = box.text_frame.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        p.text = f"[Artifact Placeholder: {path.name}]"
        p.font.bold = True
        p.font.color.rgb = Theme.TEXT_MUTED
        return False

    w = Inches(width) if width else None
    h = Inches(height) if height else None

    # Embed picture
    if w and h:
        slide.shapes.add_picture(str(path), Inches(left), Inches(top), width=w, height=h)
    elif w:
        slide.shapes.add_picture(str(path), Inches(left), Inches(top), width=w)
    elif h:
        slide.shapes.add_picture(str(path), Inches(left), Inches(top), height=h)
    else:
        slide.shapes.add_picture(str(path), Inches(left), Inches(top))

    # Add optional caption below image
    if caption and h:
        cap_box = slide.shapes.add_textbox(Inches(left), Inches(top + height + 0.05), Inches(width or 5.0), Inches(0.4))
        tf = cap_box.text_frame
        tf.word_wrap = True
        tf.margin_top = tf.margin_bottom = tf.margin_left = tf.margin_right = 0
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        p.text = caption
        p.font.name = Theme.FONT_BODY
        p.font.size = Pt(9)
        p.font.italic = True
        p.font.color.rgb = Theme.TEXT_MUTED

    return True


# ==============================================================================
# Slide 1: Title & Research Context
# ==============================================================================
def build_slide_1_title(prs: Presentation):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_solid_background(slide, Theme.BG_DARK)

    # Accent top border strip
    accent = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(0.12))
    accent.fill.solid()
    accent.fill.fore_color.rgb = Theme.PRIMARY_BLUE
    accent.line.fill.background()

    # Utility Tag Badge
    badge = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1.0), Inches(1.0), Inches(4.5), Inches(0.45))
    badge.fill.solid()
    badge.fill.fore_color.rgb = RGBColor(30, 41, 59)
    badge.line.color.rgb = Theme.ACCENT_CYAN
    badge.line.width = Pt(1.0)
    p_b = badge.text_frame.paragraphs[0]
    p_b.text = "NWSDB MUNICIPAL WATER RESEARCH INITIATIVE"
    p_b.font.name = Theme.FONT_TITLE
    p_b.font.size = Pt(10)
    p_b.font.bold = True
    p_b.font.color.rgb = Theme.ACCENT_CYAN

    # Title Box
    title_box = slide.shapes.add_textbox(Inches(1.0), Inches(1.7), Inches(11.333), Inches(2.2))
    tf = title_box.text_frame
    tf.word_wrap = True
    p1 = tf.paragraphs[0]
    p1.text = "AI-Driven Water Theft & Fraud Surveillance Engine"
    p1.font.name = Theme.FONT_TITLE
    p1.font.size = Pt(32)
    p1.font.bold = True
    p1.font.color.rgb = RGBColor(255, 255, 255)

    p2 = tf.add_paragraph()
    p2.text = "Physical Digital Twin Validation, Multi-Criteria Machine Learning & Real-Time Decision-Support under Intermittent Water Supply (IWS)"
    p2.font.name = Theme.FONT_TITLE
    p2.font.size = Pt(16)
    p2.font.color.rgb = Theme.ACCENT_CYAN
    p2.space_before = Pt(10)

    # Metadata Card Container
    add_card(slide, 1.0, 4.4, 11.333, 2.3, bg_color=RGBColor(30, 41, 59), border_color=RGBColor(51, 65, 85))

    meta_items = [
        ("Candidate & Author", "Postgraduate Researcher & Lead System Architect (M.Sc. Candidate)"),
        ("University & Faculty", "Faculty of Computing & Graduate Studies -- Advanced Sensor & Network Systems"),
        ("Industrial Partner & Scheme", "National Water Supply and Drainage Board (NWSDB) -- Kaduwela Water Supply Scheme (DMAs 01 & 02)"),
        ("Core Defense Contribution", "Physics-guided EPANET/WNTR twin + 2-stage AI eliminating 100% of IWS morning refill false alarms"),
    ]
    add_bullet_list(slide, 1.2, 4.6, 10.9, 1.9, meta_items, font_size=12)


# ==============================================================================
# Slide 2: Problem Statement: Non-Revenue Water & Metering Failures
# ==============================================================================
def build_slide_2_problem(prs: Presentation):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_solid_background(slide, Theme.BG_LIGHT)
    add_slide_header(slide, "Problem Statement: The Intermittent Water Supply (IWS) Challenge", slide_num="02/12")

    # Column 1: Core Physical Failures of Standard Smart Meters
    add_card(slide, 0.8, 1.5, 5.7, 5.3)
    p1_items = [
        ("Failure of Revenue Meters", "Household positive-displacement meters record zero consumption during unauthorized taps installed upstream of property boundary chambers."),
        ("Drained Pipe Re-Pressurization", "Under IWS (06:00-18:00 supply window), empty distribution pipes fill rapidly, causing air pockets that spin mechanical meters erratically or spin backward."),
        ("AMR/AMI Limitations", "Consumer-level smart meters detect meter tampering but fail entirely when illegal bypasses draw directly from public distribution feeder pipes."),
        ("Economic Severity", "Unmetered commercial and industrial withdrawals in Kaduwela East account for an estimated 28-34% of localized Non-Revenue Water (NRW)."),
    ]
    add_bullet_list(slide, 0.9, 1.6, 5.5, 5.0, p1_items, title="Why Conventional Smart Meters Fail under IWS", font_size=11)

    # Column 2: The Crippling False Alarm Dilemma
    add_card(slide, 6.8, 1.5, 5.7, 5.3)
    p2_items = [
        ("Morning Refill Surges", "When distribution valves open at 06:00 AM, legitimate line filling creates massive localized head losses (ΔP > 6-10 m) as empty mains recharge."),
        ("The False Alarm Paradox", "Naïve SCADA pressure thresholding (e.g. ΔP > 3.0 m) flags 50-80% of normal morning refills as theft or pipe bursts."),
        ("Utility Fatigue", "Frequent false dispatch orders desensitize field enforcement officers, resulting in ignored genuine theft alerts."),
        ("Research Objective", "Develop a physics-guided digital twin framework that differentiates authentic unmetered theft from legitimate IWS hydraulic refill transients."),
    ]
    add_bullet_list(slide, 6.9, 1.6, 5.5, 5.0, p2_items, title="The False Alarm Bottleneck in Utility SCADA", font_size=11)


# ==============================================================================
# Slide 3: Digital Twin Formulation: EPANET/WNTR PDD Simulation
# ==============================================================================
def build_slide_3_digital_twin(prs: Presentation):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_solid_background(slide, Theme.BG_LIGHT)
    add_slide_header(slide, "Digital Twin Formulation: EPANET/WNTR Pressure-Dependent Demand", slide_num="03/12")

    # Left Column: Formulation & Mathematical Framework
    add_card(slide, 0.8, 1.5, 6.2, 5.3)
    dt_items = [
        ("EPANET 2.2 / WNTR Engine", "Calibrated hydraulic twin executing Pressure-Dependent Demand (PDD) with Wagner's equation to eliminate unrealistic negative pressure anomalies."),
        ("Network Topology", "Extracted from NWSDB INP model: 3,904 junction nodes, 4,279 distribution pipes, 2 storage reservoirs, and 2 DMA boundary isolation valves."),
        ("DMA 01 (Commercial)", "Heavily industrialized corridor along Kaduwela-Malabe main line; target node J_100 (elevation 12.0m, baseline head 34.7m)."),
        ("DMA 02 (Residential)", "Mixed residential/commercial zone served by dedicated boundary prvs; target nodes J_1200, J_2200, J_3000."),
        ("SCADA Sensor Deployment", "6 strategic pressure sensor concentrators monitoring critical hydraulic junctions across both DMAs at 15-minute sampling intervals."),
    ]
    add_bullet_list(slide, 0.9, 1.6, 6.0, 5.0, dt_items, title="Hydraulic Formulation & Network Structure", font_size=11)

    # Right Column: Network Scale Metric Cards
    add_card(slide, 7.3, 1.5, 5.2, 5.3, bg_color=Theme.CARD_BG_MUTED)

    # 4 Mini Metric Callout Cards
    metrics = [
        ("3,904", "Junction Nodes", Theme.PRIMARY_BLUE, 7.5, 1.8),
        ("4,279", "Distribution Pipes", Theme.PRIMARY_BLUE, 10.0, 1.8),
        ("6 Nodes", "Designated SCADA Sensors", Theme.ACCENT_GREEN, 7.5, 3.4),
        ("15 min", "Sampling Interval", Theme.ACCENT_GREEN, 10.0, 3.4),
    ]
    for val, lbl, col, l, t in metrics:
        card = add_card(slide, l, t, 2.3, 1.3, bg_color=Theme.CARD_BG)
        box = slide.shapes.add_textbox(Inches(l), Inches(t + 0.1), Inches(2.3), Inches(1.1))
        p = box.text_frame.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        p.text = val
        p.font.bold = True
        p.font.size = Pt(20)
        p.font.color.rgb = col
        p2 = box.text_frame.add_paragraph()
        p2.alignment = PP_ALIGN.CENTER
        p2.text = lbl
        p2.font.size = Pt(9.5)
        p2.font.color.rgb = Theme.TEXT_MUTED

    # Bottom summary box on right
    add_card(slide, 7.5, 4.9, 4.8, 1.6, bg_color=Theme.CARD_BG)
    sum_box = slide.shapes.add_textbox(Inches(7.6), Inches(5.0), Inches(4.6), Inches(1.4))
    tf = sum_box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = "Physical Validation Principle:"
    p.font.bold = True
    p.font.size = Pt(11)
    p.font.color.rgb = Theme.PRIMARY_DARK
    p2 = tf.add_paragraph()
    p2.text = "The digital twin mirrors operating baseline pressure P_expected at each junction in real time. Departures reflect unmetered physical consumption, not model drift."
    p2.font.size = Pt(10)
    p2.font.color.rgb = RGBColor(71, 85, 105)


# ==============================================================================
# Slide 4: Feature Engineering
# ==============================================================================
def build_slide_4_features(prs: Presentation):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_solid_background(slide, Theme.BG_LIGHT)
    add_slide_header(slide, "Feature Engineering: Physics-Guided Hydraulic Deficit Space", slide_num="04/12")

    # Left Column: Mathematical Definitions
    add_card(slide, 0.8, 1.5, 5.8, 5.3)
    feat_items = [
        ("Hydraulic Residual (ΔP)", "ΔP = P_expected - P_actual. Measures exact head loss deficit produced by unmetered branch withdrawals relative to digital twin physics."),
        ("Spatial Gradient Mismatch", "ΔP_spatial = ΔP_i - mean(ΔP_DMA). Isolates localized consumer theft from widespread diurnal network-level demand fluctuations."),
        ("Pressure Change Rate (dP/dt)", "dP/dt = P_actual(t) - P_actual(t-1). Captures the sudden onset of commercial bypass valves vs gradual reservoir head decay."),
        ("Temporal Recurrence Memory", "Tracks repeated morning peak withdrawals across consecutive diurnal cycles to build persistence confidence."),
        ("Rolling Statistical Windows", "4-timestep rolling mean and standard deviation to filter out high-frequency hydraulic water hammer noise."),
    ]
    add_bullet_list(slide, 0.9, 1.6, 5.6, 5.0, feat_items, title="Engineered Hydraulic Features", font_size=11)

    # Right Column: Feature Importance Plot
    add_card(slide, 6.9, 1.5, 5.6, 5.3)
    fig_path = FIGURES_DIR / "fig4_feature_importance.png"
    if not fig_path.exists():
        fig_path = FIGURES_DIR / "figure_4_feature_importance.png"
    add_image_safe(slide, fig_path, 7.1, 1.8, width=5.2, height=4.6, caption="Figure 4: Decisive Dominance of Hydraulic Residual & Spatial Deviation (>75%)")


# ==============================================================================
# Slide 5: AI Architecture: Stage 1 + Stage 2
# ==============================================================================
def build_slide_5_architecture(prs: Presentation):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_solid_background(slide, Theme.BG_LIGHT)
    add_slide_header(slide, "AI Architecture: Two-Stage Anomaly Isolation & Root-Cause Classifier", slide_num="05/12")

    # Card 1: Stage 1 Isolation Forest
    add_card(slide, 0.8, 1.5, 5.7, 5.3)
    stg1_items = [
        ("Objective", "Unsupervised Anomaly Detection: Detects any abnormal departure from physical twin baseline."),
        ("Training Regime", "Trained strictly on clean baseline normal operations (label == 'normal'). Eliminates reliance on scarce physical theft labels."),
        ("Operational Output", "Anomaly score = -1 (departure) or +1 (nominal); calibrated threshold on decision function."),
        ("Robustness", "Isolates unexpected pressure depressions without making premature assumptions about whether it is a leak or theft."),
    ]
    add_bullet_list(slide, 0.9, 1.6, 5.5, 5.0, stg1_items, title="Stage 1: Isolation Forest (Anomaly Detector)", font_size=11)

    # Card 2: Stage 2 Random Forest
    add_card(slide, 6.8, 1.5, 5.7, 5.3)
    stg2_items = [
        ("Objective", "Supervised Root-Cause Classification: Discriminates between Physical Pipe Leak vs Commercial Bypass."),
        ("Class Taxonomy", "1. partial_bypass (Commercial / Industrial Theft)\n2. leak (Physical Pipe Burst / Fracture)"),
        ("Spatial Context", "Exploits spatial gradient mismatch: Bypasses produce concentrated head drops with steep local spatial gradients; leaks diffuse broadly."),
        ("Probabilistic Output", "Outputs confidence probabilities P(bypass) and P(leak) utilized by the downstream Multi-Criteria Risk Scoring Engine."),
    ]
    add_bullet_list(slide, 6.9, 1.6, 5.5, 5.0, stg2_items, title="Stage 2: Random Forest (Root-Cause Classifier)", font_size=11)


# ==============================================================================
# Slide 6: 0-100 Fraud Risk Engine & Refill Filter
# ==============================================================================
def build_slide_6_risk_engine(prs: Presentation):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_solid_background(slide, Theme.BG_LIGHT)
    add_slide_header(slide, "0–100 Multi-Criteria Fraud Risk Engine & IWS Transient Filter", slide_num="06/12")

    # Left Column: 100-Point Formula
    add_card(slide, 0.8, 1.5, 5.5, 5.3)
    risk_items = [
        ("1. Stage 1 Anomaly Flag", "+20 pts: Isolation Forest identifies abnormal pressure departure."),
        ("2. Hydraulic Severity", "+25 pts max: Proportional head loss deficit up to 10.0m (2.5 pts / meter)."),
        ("3. Temporal Persistence", "+15 pts max: min(15, recurrence_count * 3) confirmed across morning peak cycles."),
        ("4. Stage 2 RF Confidence", "+25 pts max: P(partial_bypass) * 25 probability weighting."),
        ("5. Spatial DMA Gradient", "+15 pts: Localized mismatch exceeds DMA neighborhood threshold (>= 0.50m)."),
        ("IWS Morning Refill Filter", "Suppresses high-risk alerts during 06:00-07:00 supply window unless persistence AND spatial mismatch are confirmed."),
    ]
    add_bullet_list(slide, 0.9, 1.6, 5.3, 5.0, risk_items, title="100-Point Multi-Criteria Risk Scoring", font_size=10.5)

    # Right Column: Refill Surge Figure
    add_card(slide, 6.6, 1.5, 5.9, 5.3)
    fig_path = FIGURES_DIR / "fig1_iws_refill_vs_theft.png"
    if not fig_path.exists():
        fig_path = FIGURES_DIR / "figure_1_refill_vs_theft.png"
    add_image_safe(slide, fig_path, 6.75, 1.7, width=5.6, height=4.8, caption="Figure 1: Legitimate IWS 06:00 Refill Surge (Panel A) vs. Afternoon Bypass Theft (Panel B)")


# ==============================================================================
# Slide 7: Quantitative Benchmark & Confusion Matrix
# ==============================================================================
def build_slide_7_benchmark(prs: Presentation):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_solid_background(slide, Theme.BG_LIGHT)
    add_slide_header(slide, "Confusion Matrix & Quantitative Benchmark Results", slide_num="07/12")

    # Left Column: Comparative Benchmark Results & Performance Summary
    add_card(slide, 0.8, 1.5, 5.2, 5.3)
    b_items = [
        ("Model A (Static Rule)", "Static ΔP > 3.0m rule triggers on 51.4% of morning refill surges; F1 = 0.052."),
        ("Model B (Single-Stage SVM)", "Lacks operational context; misclassifies 87.7% of refill surges as theft; F1 = 0.052."),
        ("Model C (3-Layer MLP)", "Deep neural baseline triggers on 68.5% of refill pressure dips; F1 = 0.052."),
        ("Model D (Proposed System)", "Achieves 0.0% False Positive Rate during morning refill (100% false alarm reduction) with 89.4% Precision and F1 = 0.778."),
        ("Confusion Matrix Breakdown", "Partial Bypass Precision: 89.1%, Recall: 72.5%, F1: 80.0%, FPR: 4.0%; Pipe Leak F1: 78.6%."),
        ("Real-Time Latency", "Inference execution is 0.0088 ms/sample (sub-millisecond budget for 15-min SCADA polling)."),
    ]
    add_bullet_list(slide, 0.9, 1.6, 5.0, 5.0, b_items, title="Benchmark vs Competing Architectures", font_size=10.5)

    # Right Top Container: Embedded Model Comparison Chart
    add_card(slide, 6.3, 1.5, 6.2, 2.35)
    fig_benchmark = FIGURES_DIR / "model_benchmark_comparison.png"
    add_image_safe(
        slide,
        fig_benchmark,
        6.45,
        1.58,
        width=5.9,
        height=2.05,
        caption="Comparative Benchmark: Detection F1, Refill False Alarm Rate (0.0% vs 51.4%), and Inference Latency",
    )

    # Right Bottom Left Card: Confusion Matrix Figure
    add_card(slide, 6.3, 4.05, 3.5, 2.75)
    fig_cm = FIGURES_DIR / "confusion_matrix.png"
    add_image_safe(
        slide,
        fig_cm,
        6.45,
        4.12,
        width=3.2,
        height=2.35,
        caption="Confusion Matrix (Normal, Leak, Partial Bypass)",
    )

    # Right Bottom Right Card: Highlight KPI Metrics
    add_card(slide, 10.0, 4.05, 2.5, 2.75, bg_color=Theme.CARD_BG_MUTED)

    kpi_box = slide.shapes.add_textbox(Inches(10.05), Inches(4.15), Inches(2.4), Inches(2.55))
    tf_kpi = kpi_box.text_frame
    tf_kpi.word_wrap = True
    tf_kpi.margin_left = tf_kpi.margin_right = tf_kpi.margin_top = tf_kpi.margin_bottom = 0

    kpis = [
        ("0.0%", "Refill False Alarms", Theme.ACCENT_GREEN),
        ("89.1%", "Bypass Precision", Theme.PRIMARY_BLUE),
        ("0.0088 ms", "Inference Latency", Theme.PRIMARY_DARK),
    ]
    for idx, (val, label, col) in enumerate(kpis):
        p1 = tf_kpi.paragraphs[0] if idx == 0 else tf_kpi.add_paragraph()
        p1.alignment = PP_ALIGN.CENTER
        p1.text = val
        p1.font.bold = True
        p1.font.size = Pt(17)
        p1.font.color.rgb = col
        p1.space_before = Pt(4) if idx > 0 else Pt(0)

        p2 = tf_kpi.add_paragraph()
        p2.alignment = PP_ALIGN.CENTER
        p2.text = label
        p2.font.size = Pt(8.5)
        p2.font.bold = True
        p2.font.color.rgb = Theme.TEXT_MUTED
        p2.space_after = Pt(4)


# ==============================================================================
# Slide 8: Cross-Component Ecosystem Integration
# ==============================================================================
def build_slide_8_integration(prs: Presentation):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_solid_background(slide, Theme.BG_LIGHT)
    add_slide_header(slide, "Cross-Component Ecosystem Integration: C1, C3, and C4 Interfacing", slide_num="08/12")

    # 3 Column Cards for C1, C3, C4
    cards = [
        ("Component 1 (C1)", "Acoustic Leak Correlation", Theme.PRIMARY_BLUE, 0.8, [
            ("REST Contract", "POST /api/v1/c1-leak-feedback"),
            ("Cross-Validation", "When C1 acoustic sensor detects pipe fracture (P_leak > 0.70), fraud score drops by 40%."),
            ("Operational Impact", "Suppresses false theft accusation; dispatches emergency pipe repair clamp squad instead."),
        ]),
        ("Component 3 (C3)", "Storage Water Loss Forecast", Theme.ACCENT_GREEN, 4.9, [
            ("REST Contract", "GET /api/v1/c3-water-loss/{zone}"),
            ("Volumetric Translation", "Converts detected bypass head drop into volumetric water loss (LPS & m³/day)."),
            ("Operational Impact", "Directly updates municipal storage reservoir depletion curves and pumping schedules."),
        ]),
        ("Component 4 (C4)", "Water Quality Depressurization", Theme.ACCENT_AMBER, 9.0, [
            ("REST Contract", "GET /api/v1/c4-pressure-drop-events"),
            ("Contamination Risk", "Monitors severe depressurization (P < 5.0m) creating back-siphonage risk."),
            ("Operational Impact", "Alerts water quality taskforce for pathogen infiltration sampling near bypass nodes."),
        ]),
    ]

    for title, subtitle, color, left_pos, items in cards:
        add_card(slide, left_pos, 1.5, 3.8, 5.3)
        # Header banner inside card
        ban = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(left_pos), Inches(1.5), Inches(3.8), Inches(0.8))
        ban.fill.solid()
        ban.fill.fore_color.rgb = color
        ban.line.fill.background()
        tf = ban.text_frame
        p1 = tf.paragraphs[0]
        p1.text = title
        p1.font.bold = True
        p1.font.size = Pt(13)
        p1.font.color.rgb = RGBColor(255, 255, 255)
        p2 = tf.add_paragraph()
        p2.text = subtitle
        p2.font.size = Pt(9.5)
        p2.font.color.rgb = RGBColor(241, 245, 249)

        add_bullet_list(slide, left_pos + 0.1, 2.45, 3.6, 4.2, items, font_size=10.5)


# ==============================================================================
# Slide 9: React Decision-Support Dashboard
# ==============================================================================
def build_slide_9_dashboard(prs: Presentation):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_solid_background(slide, Theme.BG_LIGHT)
    add_slide_header(slide, "React Operator Dashboard & Geo-Spatial Inspection Dispatch", slide_num="09/12")

    # Left Column: Dashboard Capabilities
    add_card(slide, 0.8, 1.5, 5.8, 5.3)
    dash_items = [
        ("Full-Stack Modern Architecture", "Vite + React 18 + TypeScript frontend backed by FastAPI REST API and WebSocket streaming."),
        ("Interactive Leaflet GIS Map", "Visualizes 3,904 WGS84 junctions and 4,279 pipes; color-codes monitored nodes by risk level (Green, Amber, Critical Red)."),
        ("Forensic Evidence Panel", "Displays automated 5-point evidence checklist explaining why the AI flagged the node."),
        ("Automated Authority Alerting", "Dispatches instant municipal email & webhook alerts containing WGS84 GPS coordinates and Google Maps navigation links."),
        ("Human-in-the-Loop Inspection Loop", "Field inspectors record ground-truth findings (Confirmed Bypass, Confirmed Leak, False Alarm) directly updating PPV metrics."),
    ]
    add_bullet_list(slide, 0.9, 1.6, 5.6, 5.0, dash_items, title="Surveillance Dashboard Features", font_size=11)

    # Right Column: Embedded Spatial DMA Chart
    add_card(slide, 6.9, 1.5, 5.6, 5.3)
    fig_path = FIGURES_DIR / "fig2_spatial_delta_dma.png"
    if not fig_path.exists():
        fig_path = FIGURES_DIR / "figure_2_spatial_comparison.png"
    add_image_safe(slide, fig_path, 7.05, 1.75, width=5.3, height=4.7, caption="Figure 2: Differential Spatial Gradient between DMA 01 (Theft) and DMA 02 (Control)")


# ==============================================================================
# Slide 10: Field Telemetry Resilience & Edge Gateway
# ==============================================================================
def build_slide_10_resilience(prs: Presentation):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_solid_background(slide, Theme.BG_LIGHT)
    add_slide_header(slide, "Field Telemetry Resilience & Edge Gateway Architecture", slide_num="10/12")

    # Card 1: Edge Gateway Logic
    add_card(slide, 0.8, 1.5, 5.7, 5.3)
    edge_items = [
        ("Deadband Filtering", "Suppresses telemetry transmission if |ΔP| < 0.05m to conserve cellular bandwidth and battery life (transmits 60-min heartbeat)."),
        ("Store-and-Forward Buffer", "If cellular network drops, telemetry queues in local SQLite buffer (edge_buffer.db); auto-flushes in FIFO order upon reconnection."),
        ("Battery & RSSI Telemetry", "Attaches real-time battery voltage (3.4-4.2V) and cellular signal quality (dBm) to each SCADA packet."),
        ("Zero Telemetry Loss", "Verified in resilience testing: zero data points lost during 30-second complete backend container disconnection."),
    ]
    add_bullet_list(slide, 0.9, 1.6, 5.5, 5.0, edge_items, title="Edge Gateway Sim (src/edge_gateway_sim.py)", font_size=11)

    # Card 2: Server-Side Imputation
    add_card(slide, 6.8, 1.5, 5.7, 5.3)
    imp_items = [
        ("Missing Data Imputation", "FastAPI backend handles 10-30% packet loss via forward-fill and linear interpolation guided by the digital twin slope."),
        ("False Alarm Suppression", "Imputation prevents erroneous artificial residual spikes during packet loss periods."),
        ("Sensor Health Warning", "Automatically flags hardware warning if consecutive missing cycles exceed 3 intervals (45 minutes)."),
        ("Stuck Sensor Override", "Detects mechanically locked transducers (e.g. constant 18.0m) and suppresses false theft accusations."),
    ]
    add_bullet_list(slide, 6.9, 1.6, 5.5, 5.0, imp_items, title="Server-Side Telemetry Imputation & Health", font_size=11)


# ==============================================================================
# Slide 11: Limitations & Ethical Boundaries
# ==============================================================================
def build_slide_11_ethics(prs: Presentation):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_solid_background(slide, Theme.BG_LIGHT)
    add_slide_header(slide, "Operational Boundaries, Ethics & Future Enhancements", slide_num="11/12")

    # Card 1: Ethical Boundaries
    add_card(slide, 0.8, 1.5, 5.7, 5.3)
    eth_items = [
        ("Decision-Support Principle", "The system flags 'anomalous hydraulic consumption candidates for field audit', never legally accuses or fines consumers automatically."),
        ("Human-in-the-Loop", "Dispatched NWSDB officers must physically verify the illegal branch before enforcement actions or legal notices are issued."),
        ("Inspection Audit Trail", "All inspector verifications are logged in field_inspections_ledger.json, computing live Positive Predictive Value (PPV)."),
        ("Candidate Retraining Trigger", "Every 10 verified field inspections trigger candidate batch extraction to retrain models on local ground truth."),
    ]
    add_bullet_list(slide, 0.9, 1.6, 5.5, 5.0, eth_items, title="Ethical Boundaries & Accountability", font_size=11)

    # Card 2: Limitations & Future Enhancements
    add_card(slide, 6.8, 1.5, 5.7, 5.3)
    fut_items = [
        ("Hydraulic Calibration Sensitivity", "Residual accuracy relies on calibrated pipe Hazen-Williams C-factors; unmodeled tuberculation causes minor baseline drift."),
        ("Sparse Sensor Density", "6 monitored junctions require spatial interpolation; future work explores optimal multi-sensor placement algorithms."),
        ("LoRaWAN Integration", "Transition from simulated edge gateways to physical LoRaWAN concentrators with long-life LiFePO4 batteries."),
        ("Satellite Earth Observation", "Combining hydraulic head drops with radar soil moisture anomalies to detect concealed underground bypass excavations."),
    ]
    add_bullet_list(slide, 6.9, 1.6, 5.5, 5.0, fut_items, title="System Limitations & Future Horizons", font_size=11)


# ==============================================================================
# Slide 12: Live Demonstration & Conclusion
# ==============================================================================
def build_slide_12_conclusion(prs: Presentation):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_solid_background(slide, Theme.BG_LIGHT)
    add_slide_header(slide, "Live Demonstration Script & Oral Defense Conclusion", slide_num="12/12")

    # Card 1: Live Demo Walkthrough
    add_card(slide, 0.8, 1.5, 5.7, 5.3)
    demo_items = [
        ("Phase 1: Normal Baseline", "Run --scenario normal: Clean SCADA stream across DMA 01 & 02; dashboard displays 100% green (Risk < 20%)."),
        ("Phase 2: 06:00 Refill Surge", "Run --scenario refill_surge: Massive transient line-filling surge; IWS dampening filter holds risk < 45% (0 false alarms)."),
        ("Phase 3: Unauthorized Theft", "Run --scenario bypass_theft: Unauthorized 0.06 LPS tap at J_100; risk spikes to 86.7%, node turns red, GPS coordinates & alert dispatched."),
        ("Phase 4: C1 Cross-Validation", "Trigger C1 leak feedback: Risk score immediately drops -40% (reclassified to pipe burst repair squad)."),
    ]
    add_bullet_list(slide, 0.9, 1.6, 5.5, 5.0, demo_items, title="2-Minute Demonstration Script (src/scenario_runner.py)", font_size=11)

    # Card 2: Concluding Takeaway
    add_card(slide, 6.8, 1.5, 5.7, 5.3)
    conc_items = [
        ("First-of-its-Kind for IWS", "First digital twin surveillance platform designed specifically for intermittent water supply networks in the Global South."),
        ("Solved the Refill Dilemma", "Achieved 100% false alarm reduction during morning pipe-filling transients compared to static thresholding."),
        ("Multi-Component Interoperability", "Seamlessly connects with C1 (acoustic leaks), C3 (reservoir forecasts), and C4 (contamination risk)."),
        ("Field-Deployable Platform", "Production Docker containers, sub-millisecond inference (0.0088 ms), and resilient edge store-and-forward architecture."),
    ]
    add_bullet_list(slide, 6.9, 1.6, 5.5, 5.0, conc_items, title="Core Research Contributions", font_size=11)


# ==============================================================================
# Main Presentation Builder Orchestrator
# ==============================================================================
def generate_presentation(
    output_path: Union[str, Path] = DEFAULT_OUTPUT_PPTX,
    figures_dir: Union[str, Path] = FIGURES_DIR,
) -> Path:
    """
    Constructs the complete 12-slide oral defense presentation deck and saves to output_path.
    """
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Initializing 16:9 Widescreen Presentation Deck...")
    prs = create_widescreen_presentation()

    # Build 12 Slides Sequentially
    logger.info("Building Slide 1: Title & Research Context...")
    build_slide_1_title(prs)

    logger.info("Building Slide 2: Problem Statement & Non-Revenue Water...")
    build_slide_2_problem(prs)

    logger.info("Building Slide 3: Digital Twin Formulation (EPANET/WNTR)...")
    build_slide_3_digital_twin(prs)

    logger.info("Building Slide 4: Feature Engineering & Hydraulic Residuals...")
    build_slide_4_features(prs)

    logger.info("Building Slide 5: AI Architecture (Stage 1 + Stage 2)...")
    build_slide_5_architecture(prs)

    logger.info("Building Slide 6: 0-100 Risk Engine & Refill Transient Filter...")
    build_slide_6_risk_engine(prs)

    logger.info("Building Slide 7: Quantitative Benchmark & Confusion Matrix...")
    build_slide_7_benchmark(prs)

    logger.info("Building Slide 8: Cross-Component Ecosystem Integration...")
    build_slide_8_integration(prs)

    logger.info("Building Slide 9: React Operator Dashboard & Geo-Spatial Dispatch...")
    build_slide_9_dashboard(prs)

    logger.info("Building Slide 10: Field Telemetry Resilience & Edge Gateway...")
    build_slide_10_resilience(prs)

    logger.info("Building Slide 11: Limitations, Ethics & Future Horizons...")
    build_slide_11_ethics(prs)

    logger.info("Building Slide 12: Live Demonstration Script & Conclusion...")
    build_slide_12_conclusion(prs)

    # Save PPTX presentation
    prs.save(str(out_file))
    size_mb = out_file.stat().st_size / (1024.0 * 1024.0)
    logger.info(f"Presentation deck successfully compiled and saved to: {out_file} ({size_mb:.2f} MB, 12 slides)")
    return out_file


def main():
    parser = argparse.ArgumentParser(description="Generate Oral Defense Presentation Deck for Component 2.")
    parser.add_argument("--out", type=str, default=str(DEFAULT_OUTPUT_PPTX), help="Output path for PPTX file")
    parser.add_argument("--figures-dir", type=str, default=str(FIGURES_DIR), help="Directory containing figures")
    args = parser.parse_args()

    out_path = generate_presentation(output_path=args.out, figures_dir=args.figures_dir)
    print(f"\n[SUCCESS] Generated 12-slide presentation at: {out_path}\n")


if __name__ == "__main__":
    main()
