"""
VERA-NSW - Verification Engine for Results & Accountability
Streamlit Web Application for Australian Education Data

Analyzes NSW government school data to identify schools with hidden
language-based literacy disadvantage using LBOTE and FOEI indices.
"""

import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path
import json
import sqlite3
from datetime import datetime

# =============================================================================
# Configuration
# =============================================================================

st.set_page_config(
    page_title="VERA-NSW | Education Equity Analysis",
    page_icon="🦘",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Australian / NSW Brand Colors
NAVY = "#002664"      # NSW Government blue
GOLD = "#C9A227"      # Gold accent
CREAM = "#F5F5F0"
RED = "#D4351C"
GREEN = "#00703C"

# Custom CSS
st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;600;700&display=swap');

    .stApp {{
        background-color: {CREAM};
    }}

    section[data-testid="stSidebar"] {{
        background-color: {NAVY};
    }}
    section[data-testid="stSidebar"] .stMarkdown {{
        color: white;
    }}
    section[data-testid="stSidebar"] label {{
        color: white !important;
    }}
    section[data-testid="stSidebar"] .stRadio label,
    section[data-testid="stSidebar"] .stRadio label span,
    section[data-testid="stSidebar"] .stRadio label p,
    section[data-testid="stSidebar"] .stRadio label div {{
        color: white !important;
    }}

    h1, h2, h3 {{
        font-family: 'Public Sans', sans-serif;
        color: {NAVY};
    }}
    h1 {{
        border-bottom: 4px solid {GOLD};
        padding-bottom: 16px;
    }}

    .stat-card {{
        background: white;
        padding: 20px;
        border-radius: 8px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        border-left: 4px solid {GOLD};
    }}
    .stat-card .value {{
        font-size: 2.5rem;
        font-weight: 700;
        color: {GOLD};
    }}
    .stat-card .label {{
        font-size: 0.9rem;
        color: #666;
    }}

    .risk-high {{
        background-color: {RED};
        color: white;
        padding: 4px 12px;
        border-radius: 4px;
        font-weight: 600;
    }}
    .risk-medium {{
        background-color: #F47738;
        color: white;
        padding: 4px 12px;
        border-radius: 4px;
        font-weight: 600;
    }}
    .risk-low {{
        background-color: {GREEN};
        color: white;
        padding: 4px 12px;
        border-radius: 4px;
        font-weight: 600;
    }}

    #MainMenu {{visibility: hidden;}}
    footer {{visibility: hidden;}}
</style>
""", unsafe_allow_html=True)

# =============================================================================
# Data Functions
# =============================================================================

BASE_URL = "https://data.nsw.gov.au/data/api/action/datastore_search"
MASTER_RESOURCE_ID = "3e6d5f6a-055c-440d-a690-fc0537c31095"

@st.cache_data(ttl=3600)
def fetch_all_schools():
    """Fetch all NSW government schools from Data.NSW API."""
    all_schools = []
    offset = 0
    limit = 500

    with st.spinner("Loading NSW school data from Data.NSW..."):
        while True:
            params = {
                "resource_id": MASTER_RESOURCE_ID,
                "limit": limit,
                "offset": offset
            }

            try:
                response = requests.get(BASE_URL, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()

                if not data.get("success"):
                    break

                records = data.get("result", {}).get("records", [])
                if not records:
                    break

                all_schools.extend(records)
                offset += limit

                total = data.get("result", {}).get("total", 0)
                if offset >= total:
                    break

            except Exception as e:
                st.error(f"Error fetching data: {e}")
                break

    return all_schools


def safe_float(value, default=0.0):
    """Safely convert value to float."""
    try:
        if value is None or value == "" or value == "np":
            return default
        return float(value)
    except (ValueError, TypeError):
        return default


def compute_risk_score(row):
    """Compute equity risk score for a school."""
    lbote = safe_float(row.get("LBOTE_pct", 0))
    foei = safe_float(row.get("FOEI_Value", 0))
    icsea = safe_float(row.get("ICSEA_value", 1000))

    lbote_factor = min(lbote / 100, 1.0)
    foei_factor = min(foei / 200, 1.0)
    icsea_factor = max(0, 1 - (icsea / 1200))

    risk = (lbote_factor * 0.4 + foei_factor * 0.4 + icsea_factor * 0.2) * 100
    return round(risk, 2)


def prepare_dataframe(schools):
    """Convert school data to DataFrame with computed fields."""
    records = []
    for school in schools:
        risk_score = compute_risk_score(school)
        enrollment = safe_float(school.get("latest_year_enrolment_FTE", 0))
        lbote = safe_float(school.get("LBOTE_pct", 0))

        records.append({
            "school_code": school.get("School_code"),
            "school_name": school.get("School_name"),
            "school_type": school.get("School_subtype"),
            "suburb": school.get("Town_suburb"),
            "postcode": school.get("Postcode"),
            "lga": school.get("LGA"),
            "remoteness": school.get("ASGS_remoteness"),
            "enrollment": enrollment,
            "icsea": safe_float(school.get("ICSEA_value", 0)),
            "foei": safe_float(school.get("FOEI_Value", 0)),
            "lbote_pct": lbote,
            "indigenous_pct": safe_float(school.get("Indigenous_pct", 0)),
            "risk_score": risk_score,
            "students_at_risk": int(enrollment * (lbote / 100)) if lbote > 0 else 0,
            "latitude": safe_float(school.get("Latitude", 0)),
            "longitude": safe_float(school.get("Longitude", 0))
        })

    return pd.DataFrame(records)


# =============================================================================
# Sidebar
# =============================================================================

with st.sidebar:
    st.markdown(f"""
        <div style="text-align: center; padding: 20px 0;">
            <span style="font-size: 3rem;">🦘</span>
            <h2 style="color: white; margin: 10px 0;">VERA-NSW</h2>
            <p style="color: {GOLD}; font-size: 0.9rem;">Verification Engine for Results & Accountability</p>
            <p style="color: rgba(255,255,255,0.6); font-size: 0.8rem;">New South Wales Edition</p>
        </div>
    """, unsafe_allow_html=True)

    st.markdown("---")

    page = st.radio(
        "Navigate",
        ["📊 School Dashboard", "🔍 LBOTE Risk Analysis", "🚩 Intervention Gaps", "📝 Student Record", "📅 Daily Observations", "ℹ️ About VERA-NSW"],
        label_visibility="collapsed"
    )

    # Gold divider bar
    st.markdown(f"""
        <div style="
            height: 4px;
            background: linear-gradient(90deg, {GOLD}, #D4AF37, {GOLD});
            margin: 30px 0 20px 0;
            border-radius: 2px;
        "></div>
    """, unsafe_allow_html=True)

    # VERA logo
    st.image("vera_logo.png", use_container_width=True)

    # Version and attribution - bright gold text
    st.markdown(f"""
        <p style="color: {GOLD}; font-size: 1.4rem; font-weight: 700; text-align: center; margin: 12px 0 6px 0; text-shadow: 0 1px 2px rgba(0,0,0,0.5);">
            VERA-NSW v0.1
        </p>
        <p style="color: white; font-size: 0.9rem; text-align: center; margin: 0 0 12px 0;">
            Verification Engine for<br>Results & Accountability
        </p>
        <p style="text-align: center;">
            <a href="https://data.nsw.gov.au" target="_blank" style="
                color: {GOLD};
                font-size: 1rem;
                font-weight: 600;
                text-decoration: none;
                border-bottom: 2px solid {GOLD};
            ">Data.NSW Open Data</a>
        </p>
    """, unsafe_allow_html=True)


# =============================================================================
# Load Data
# =============================================================================

schools_raw = fetch_all_schools()
if schools_raw:
    df = prepare_dataframe(schools_raw)
else:
    st.error("Unable to load school data from Data.NSW API")
    st.stop()


# =============================================================================
# Page: School Dashboard
# =============================================================================

if page == "📊 School Dashboard":
    st.title("NSW School Dashboard")

    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        school_types = ["All"] + sorted(df["school_type"].dropna().unique().tolist())
        selected_type = st.selectbox("School Type", school_types)
    with col2:
        lgas = ["All"] + sorted(df["lga"].dropna().unique().tolist())
        selected_lga = st.selectbox("Local Government Area", lgas)
    with col3:
        min_risk = st.slider("Minimum Risk Score", 0, 100, 0)

    # Filter data
    filtered = df.copy()
    if selected_type != "All":
        filtered = filtered[filtered["school_type"] == selected_type]
    if selected_lga != "All":
        filtered = filtered[filtered["lga"] == selected_lga]
    filtered = filtered[filtered["risk_score"] >= min_risk]

    # Summary stats
    st.markdown("### Overview")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"""
            <div class="stat-card">
                <div class="value">{len(filtered):,}</div>
                <div class="label">Schools</div>
            </div>
        """, unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
            <div class="stat-card">
                <div class="value">{int(filtered['enrollment'].sum()):,}</div>
                <div class="label">Total Enrollment</div>
            </div>
        """, unsafe_allow_html=True)
    with c3:
        avg_lbote = filtered["lbote_pct"].mean()
        st.markdown(f"""
            <div class="stat-card">
                <div class="value">{avg_lbote:.1f}%</div>
                <div class="label">Avg LBOTE</div>
            </div>
        """, unsafe_allow_html=True)
    with c4:
        high_risk = len(filtered[filtered["risk_score"] >= 50])
        st.markdown(f"""
            <div class="stat-card">
                <div class="value" style="color: {RED};">{high_risk}</div>
                <div class="label">High Risk Schools</div>
            </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # Risk distribution chart
    st.markdown("### Risk Score Distribution")
    fig = px.histogram(
        filtered,
        x="risk_score",
        nbins=20,
        color_discrete_sequence=[NAVY]
    )
    fig.update_layout(
        xaxis_title="Risk Score",
        yaxis_title="Number of Schools",
        showlegend=False
    )
    st.plotly_chart(fig, use_container_width=True)

    # School table
    st.markdown("### Schools")
    display_cols = ["school_name", "school_type", "suburb", "lga", "enrollment", "lbote_pct", "foei", "icsea", "risk_score"]
    st.dataframe(
        filtered[display_cols].sort_values("risk_score", ascending=False),
        use_container_width=True,
        hide_index=True
    )

    # Download
    csv = filtered.to_csv(index=False)
    st.download_button("Download CSV", csv, "vera_nsw_schools.csv", "text/csv")


# =============================================================================
# Page: LBOTE Risk Analysis
# =============================================================================

elif page == "🔍 LBOTE Risk Analysis":
    st.title("LBOTE Risk Profile Analysis")

    st.markdown("""
    **LBOTE** (Language Background Other Than English) indicates students who speak a language
    other than English at home. When high LBOTE concentration intersects with high disadvantage
    (FOEI), schools may have hidden literacy gaps not captured by current funding models.
    """)

    # Thresholds
    col1, col2 = st.columns(2)
    with col1:
        lbote_threshold = st.slider("LBOTE Threshold (%)", 10, 80, 30)
    with col2:
        foei_threshold = st.slider("FOEI Threshold", 50, 180, 100)

    # Filter
    high_risk = df[(df["lbote_pct"] >= lbote_threshold) & (df["foei"] >= foei_threshold)]
    high_risk = high_risk.sort_values("risk_score", ascending=False)

    # Summary
    st.markdown("### Analysis Summary")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Schools Meeting Criteria", len(high_risk))
    with c2:
        st.metric("Students at Risk", f"{high_risk['students_at_risk'].sum():,}")
    with c3:
        pct = len(high_risk) / len(df) * 100 if len(df) > 0 else 0
        st.metric("% of All Schools", f"{pct:.1f}%")

    # Scatter plot
    st.markdown("### LBOTE vs FOEI Correlation")
    fig = px.scatter(
        df,
        x="lbote_pct",
        y="foei",
        size="enrollment",
        color="risk_score",
        color_continuous_scale=["green", "yellow", "red"],
        hover_name="school_name",
        hover_data=["suburb", "lga", "icsea"]
    )
    fig.add_hline(y=foei_threshold, line_dash="dash", line_color="red", annotation_text=f"FOEI={foei_threshold}")
    fig.add_vline(x=lbote_threshold, line_dash="dash", line_color="red", annotation_text=f"LBOTE={lbote_threshold}%")
    fig.update_layout(
        xaxis_title="LBOTE %",
        yaxis_title="FOEI (Disadvantage Index)"
    )
    st.plotly_chart(fig, use_container_width=True)

    # Top risk schools
    st.markdown("### Top 20 High-Risk Schools")
    st.dataframe(
        high_risk[["school_name", "suburb", "lga", "enrollment", "lbote_pct", "foei", "icsea", "risk_score", "students_at_risk"]].head(20),
        use_container_width=True,
        hide_index=True
    )


# =============================================================================
# Page: Intervention Gaps
# =============================================================================

elif page == "🚩 Intervention Gaps":
    st.title("Intervention Gap Analysis")

    st.markdown("""
    Schools flagged here have the highest equity risk scores — combinations of high LBOTE,
    high disadvantage (FOEI), and low socioeconomic index (ICSEA) that indicate potential
    gaps in literacy intervention coverage.

    **⚠️ Data Gap:** Without NAPLAN outcome data, we cannot verify intervention effectiveness.
    This analysis identifies WHERE risk is concentrated; outcome data would show WHETHER
    interventions are working.
    """)

    risk_threshold = st.slider("Risk Score Threshold", 20, 80, 50)

    flagged = df[df["risk_score"] >= risk_threshold].sort_values("risk_score", ascending=False)

    # Summary
    st.markdown("### Flagged Schools Summary")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Schools Flagged", len(flagged))
    with c2:
        st.metric("Total Enrollment", f"{int(flagged['enrollment'].sum()):,}")
    with c3:
        st.metric("At-Risk Students", f"{flagged['students_at_risk'].sum():,}")
    with c4:
        avg_risk = flagged["risk_score"].mean() if len(flagged) > 0 else 0
        st.metric("Avg Risk Score", f"{avg_risk:.1f}")

    # LGA breakdown
    st.markdown("### Geographic Distribution")
    lga_counts = flagged.groupby("lga").agg({
        "school_name": "count",
        "students_at_risk": "sum"
    }).reset_index()
    lga_counts.columns = ["LGA", "Schools", "Students at Risk"]
    lga_counts = lga_counts.sort_values("Schools", ascending=False).head(15)

    fig = px.bar(
        lga_counts,
        x="LGA",
        y="Schools",
        color="Students at Risk",
        color_continuous_scale=["yellow", "red"]
    )
    fig.update_layout(xaxis_tickangle=-45)
    st.plotly_chart(fig, use_container_width=True)

    # Flagged schools table
    st.markdown("### Flagged Schools")
    st.dataframe(
        flagged[["school_name", "school_type", "suburb", "lga", "enrollment", "lbote_pct", "foei", "icsea", "risk_score", "students_at_risk"]].head(50),
        use_container_width=True,
        hide_index=True
    )

    # Export
    csv = flagged.to_csv(index=False)
    st.download_button("Download Flagged Schools CSV", csv, "vera_nsw_flagged.csv", "text/csv")


# =============================================================================
# Page: About
# =============================================================================

elif page == "ℹ️ About VERA-NSW":
    st.title("About VERA-NSW")

    st.markdown(f"""
    ## Verification Engine for Results & Accountability

    **VERA-NSW** is an equity analysis tool that identifies NSW government schools where
    hidden literacy disadvantage may exist — schools with high language diversity and
    high socioeconomic disadvantage that may not be fully captured by current funding models.

    ---

    ## The Risk Model

    VERA-NSW computes an **Equity Risk Score** (0-100) based on three factors:

    | Factor | Weight | Interpretation |
    |--------|--------|----------------|
    | **LBOTE %** | 40% | Language Background Other Than English |
    | **FOEI** | 40% | Family Occupation and Education Index (disadvantage) |
    | **ICSEA** | 20% | Index of Community Socio-Educational Advantage (inverted) |

    Schools with high LBOTE + high FOEI + low ICSEA receive the highest risk scores,
    indicating potential gaps between language-based literacy needs and intervention resources.

    ---

    ## Data Sources

    All data comes from **[Data.NSW](https://data.nsw.gov.au)**, the NSW Government's open data portal:

    - **Master Dataset:** All NSW government schools with demographics
    - **Fields:** School code, name, type, location, enrollment, ICSEA, FOEI, LBOTE%, Indigenous%
    - **License:** Creative Commons Attribution
    - **Update Frequency:** Nightly (some fields), Annual (enrollment)

    ---

    ## The Gap: NAPLAN Data

    NAPLAN assessment results — the performance data that would close the verification loop —
    are held by **ACARA** (Australian Curriculum, Assessment and Reporting Authority) federally,
    not by NSW. Access requires:

    - Application through the **ACARA Data Access Program**, or
    - Partnership with **CESE** (Centre for Education Statistics and Evaluation)

    VERA-NSW identifies WHERE risk is concentrated. NAPLAN data would show WHETHER
    interventions are working for those students.

    ---

    ## Contact

    For NAPLAN data access inquiries:
    - **CESE:** [education.nsw.gov.au/cese](https://education.nsw.gov.au/about-us/strategies-and-reports/centre-for-education-statistics-and-evaluation)
    - **ACARA:** [acara.edu.au](https://www.acara.edu.au)

    ---

    <p style="color: #666; font-size: 0.9rem;">
        VERA-NSW v0.1 | Built by <a href="https://hallucinations.cloud" style="color: {GOLD};">Hallucinations.cloud</a>
    </p>
    """, unsafe_allow_html=True)

# =============================================================================
# Page: Student Initialization Record (Document 1)
# =============================================================================

elif page == "📝 Student Record":
    st.title("Student Initialization Record")
    st.markdown("*Document 1 — Day-One Student Record*")

    # Initialize database tables
    def init_nsw_observation_tables():
        db_path = Path(__file__).parent / "vera_nsw.db"
        conn = sqlite3.connect(str(db_path))

        conn.execute("""
            CREATE TABLE IF NOT EXISTS initialization_records (
                record_id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id TEXT NOT NULL,
                teacher_id TEXT NOT NULL,
                school_code TEXT NOT NULL,
                school_year TEXT NOT NULL,
                vera_hypothesis TEXT,
                teacher_response TEXT,
                teacher_notes TEXT,
                intervention_assigned TEXT,
                section_a_complete INTEGER DEFAULT 0,
                section_b_complete INTEGER DEFAULT 0,
                section_c_complete INTEGER DEFAULT 0,
                section_d_complete INTEGER DEFAULT 0,
                section_e_complete INTEGER DEFAULT 0,
                locked_at TIMESTAMP,
                locked_by TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(student_id, school_year)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS observations (
                record_id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id TEXT NOT NULL,
                school_code TEXT NOT NULL,
                class_period TEXT,
                observation_date DATE NOT NULL,
                student_id TEXT NOT NULL,
                present INTEGER DEFAULT 0,
                oral_participation INTEGER DEFAULT 0,
                written_output INTEGER DEFAULT 0,
                engaged INTEGER DEFAULT 0,
                concern_flag INTEGER DEFAULT 0,
                absent INTEGER DEFAULT 0,
                elaboration TEXT,
                oral_quality TEXT,
                written_quality TEXT,
                intervention_response TEXT,
                note TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(teacher_id, observation_date, student_id, class_period)
            )
        """)
        conn.commit()
        conn.close()

    init_nsw_observation_tables()

    # Session state for form
    if 'init_record' not in st.session_state:
        st.session_state.init_record = {}

    # Student selector
    st.markdown("---")
    col1, col2, col3 = st.columns([2, 2, 1])

    with col1:
        student_id = st.text_input("Student ID", placeholder="Enter Student ID")
    with col2:
        teacher_id = st.text_input("Teacher ID", value="demo_teacher")
    with col3:
        school_year = st.selectbox("School Year", ["2026", "2025", "2027"])

    if not student_id:
        st.info("Enter a Student ID to begin the initialization record.")
        st.stop()

    # Check if record exists and is locked
    db_path = Path(__file__).parent / "vera_nsw.db"
    conn = sqlite3.connect(str(db_path))
    cursor = conn.execute(
        "SELECT * FROM initialization_records WHERE student_id = ? AND school_year = ?",
        (student_id, school_year)
    )
    existing = cursor.fetchone()
    conn.close()

    if existing and existing[15]:  # locked_at field
        st.warning(f"This record was locked on {existing[15]} and cannot be edited.")
        st.markdown("**Document 2 (Daily Observations)** is now active for this student.")
        st.stop()

    st.markdown("---")

    # Five-Section Checklist (adapted for NSW)
    st.markdown(f"""
        <div style="background: {NAVY}; color: white; padding: 16px; border-radius: 4px; margin-bottom: 20px;">
            <h3 style="color: {GOLD}; margin: 0;">Five-Section Initialization Checklist</h3>
            <p style="margin: 8px 0 0 0; opacity: 0.8;">All sections must be completed before this record can be locked.</p>
        </div>
    """, unsafe_allow_html=True)

    # SECTION A: Record Verification
    with st.expander("**Section A: Record Verification**", expanded=True):
        st.markdown("*Verify student identity and administrative records*")

        a1 = st.checkbox("Student name and ID confirmed against enrolment", key="a1")
        a2 = st.checkbox("Emergency contact and parent/guardian verified", key="a2")
        a3 = st.checkbox("Language background (LBOTE) reviewed", key="a3")
        a4 = st.checkbox("Immunisation record verified", key="a4")
        a5 = st.checkbox("Special population flags reviewed (ATSI, disability, EAL/D)", key="a5")

        # Population flags
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.checkbox("LBOTE", key="flag_lbote")
        with col2:
            st.checkbox("EAL/D", key="flag_eald")
        with col3:
            st.checkbox("ATSI", key="flag_atsi")
        with col4:
            st.checkbox("Disability", key="flag_disability")

        section_a_complete = all([a1, a2, a3, a4, a5])
        if section_a_complete:
            st.success("Section A complete")

    # SECTION B: Assessment Data Review
    with st.expander("**Section B: Assessment Data Review**", expanded=False):
        st.markdown("*Review baseline assessment scores and VERA hypothesis*")

        st.markdown("**NAPLAN Scores (when available)**")
        col1, col2 = st.columns(2)
        with col1:
            naplan_reading = st.number_input("Reading Band", value=5, disabled=True)
            naplan_writing = st.number_input("Writing Band", value=4, disabled=True)
        with col2:
            naplan_numeracy = st.number_input("Numeracy Band", value=5, disabled=True)

        st.markdown("**School Risk Profile (from VERA-NSW)**")
        col1, col2, col3 = st.columns(3)
        with col1:
            lbote_pct = st.number_input("LBOTE %", value=65, disabled=True)
        with col2:
            foei = st.number_input("FOEI Score", value=145, disabled=True)
        with col3:
            risk_score = st.number_input("VERA Risk Score", value=72, disabled=True)

        # VERA hypothesis
        vera_hypothesis = "High-risk LBOTE student at school with elevated FOEI. Writing support likely needed based on oral-written pattern indicators." if risk_score > 50 else "Standard monitoring recommended."
        st.info(vera_hypothesis)

        b1 = st.checkbox("Assessment data reviewed", key="b1")
        b2 = st.checkbox("VERA risk profile acknowledged", key="b2")
        b3 = st.checkbox("Teacher acknowledges VERA finding", key="b3")

        section_b_complete = all([b1, b2, b3])
        if section_b_complete:
            st.success("Section B complete")

    # SECTION C: Prior Intervention History
    with st.expander("**Section C: Prior Intervention History**", expanded=False):
        st.markdown("*Review what has been tried before*")

        st.markdown("**Prior Teacher Summary**")
        st.text_area(
            "Previous teacher notes",
            value="Strong verbal participation. Written work often incomplete. Benefits from visual supports and EAL/D scaffolding.",
            height=100,
            disabled=True,
            key="prior_summary"
        )

        c1 = st.checkbox("Prior teacher summary read and acknowledged", key="c1")
        c2 = st.checkbox("Prior intervention outcomes reviewed", key="c2")

        intervention_options = [
            "Writing-focused EAL/D support (VERA recommended)",
            "Standard EAL/D support",
            "Literacy intervention program",
            "Learning support team referral",
            "Other"
        ]
        assigned_intervention = st.selectbox("Intervention assignment", intervention_options, key="intervention")
        c3 = st.checkbox("Intervention assignment confirmed", key="c3")

        section_c_complete = all([c1, c2, c3])
        if section_c_complete:
            st.success("Section C complete")

    # SECTION D: Equity and Access
    with st.expander("**Section D: Equity and Access**", expanded=False):
        st.markdown("*Verify equitable access to resources*")

        d1 = st.checkbox("Device access confirmed", key="d1")
        d2 = st.checkbox("Internet access at home verified", key="d2")
        d3 = st.checkbox("Equity loading eligibility confirmed", key="d3")

        section_d_complete = all([d1, d2, d3])
        if section_d_complete:
            st.success("Section D complete")

    # SECTION E: Day-One Starting Plan
    with st.expander("**Section E: Day-One Starting Plan**", expanded=False):
        st.markdown("*Final review and sign-off — THIS LOCKS THE RECORD*")

        st.info(vera_hypothesis)

        teacher_response = st.radio(
            "Teacher response to VERA hypothesis",
            ["Confirmed — I agree with VERA's assessment",
             "Challenged — I disagree based on my observation",
             "Modified — I accept with adjustments"],
            key="teacher_response"
        )

        if "Challenged" in teacher_response or "Modified" in teacher_response:
            teacher_notes = st.text_area(
                "Explain your challenge or modification",
                placeholder="Provide rationale...",
                key="teacher_notes"
            )
        else:
            teacher_notes = ""

        e1 = st.checkbox("VERA hypothesis accepted or challenged", key="e1")
        e2 = st.checkbox("I understand this record will be LOCKED permanently", key="e2")

        section_e_complete = all([e1, e2])
        if section_e_complete:
            st.success("Section E complete — Ready to lock")

    # Summary
    st.markdown("---")
    st.markdown("### Checklist Summary")

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.success("A ✓") if section_a_complete else st.error("A ○")
    with col2:
        st.success("B ✓") if section_b_complete else st.error("B ○")
    with col3:
        st.success("C ✓") if section_c_complete else st.error("C ○")
    with col4:
        st.success("D ✓") if section_d_complete else st.error("D ○")
    with col5:
        st.success("E ✓") if section_e_complete else st.error("E ○")

    all_complete = all([section_a_complete, section_b_complete, section_c_complete,
                        section_d_complete, section_e_complete])

    if all_complete:
        st.markdown(f"""
            <div style="background: {GREEN}; color: white; padding: 16px; border-radius: 4px; margin: 20px 0;">
                <strong>All sections complete.</strong> This record is ready to be locked.
            </div>
        """, unsafe_allow_html=True)

        if st.button("🔒 LOCK RECORD & OPEN DOCUMENT 2", type="primary", use_container_width=True):
            db_path = Path(__file__).parent / "vera_nsw.db"
            conn = sqlite3.connect(str(db_path))

            response_map = {
                "Confirmed — I agree with VERA's assessment": "confirmed",
                "Challenged — I disagree based on my observation": "challenged",
                "Modified — I accept with adjustments": "modified"
            }

            conn.execute("""
                INSERT INTO initialization_records
                (student_id, teacher_id, school_code, school_year, vera_hypothesis, teacher_response,
                 teacher_notes, intervention_assigned, section_a_complete, section_b_complete,
                 section_c_complete, section_d_complete, section_e_complete, locked_at, locked_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1, 1, 1, 1, datetime('now'), ?)
                ON CONFLICT(student_id, school_year) DO UPDATE SET
                    locked_at = datetime('now'),
                    locked_by = excluded.locked_by
            """, (
                student_id,
                teacher_id,
                "demo_school",
                school_year,
                vera_hypothesis,
                response_map.get(teacher_response, "confirmed"),
                teacher_notes,
                assigned_intervention,
                teacher_id
            ))
            conn.commit()
            conn.close()

            st.success("✅ Record LOCKED. Document 2 (Daily Observations) is now active.")
            st.balloons()
    else:
        st.warning("Complete all five sections to lock this record.")

# =============================================================================
# Page: Daily Observations (Document 2)
# =============================================================================

elif page == "📅 Daily Observations":
    st.title("Daily Classroom Observations")
    st.markdown("*Document 2 — Ongoing Observation Log*")

    # Initialize tables
    def init_obs_table():
        db_path = Path(__file__).parent / "vera_nsw.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS observations (
                record_id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id TEXT NOT NULL,
                school_code TEXT NOT NULL,
                class_period TEXT,
                observation_date DATE NOT NULL,
                student_id TEXT NOT NULL,
                present INTEGER DEFAULT 0,
                oral_participation INTEGER DEFAULT 0,
                written_output INTEGER DEFAULT 0,
                engaged INTEGER DEFAULT 0,
                concern_flag INTEGER DEFAULT 0,
                absent INTEGER DEFAULT 0,
                elaboration TEXT,
                note TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(teacher_id, observation_date, student_id, class_period)
            )
        """)
        conn.commit()
        conn.close()

    init_obs_table()

    # Demo roster (NSW context)
    DEMO_ROSTER = [
        {"student_id": "NSW001", "name": "Nguyen, Minh", "flag": "LBOTE", "high_risk": True},
        {"student_id": "NSW002", "name": "Smith, Emma", "flag": None, "high_risk": False},
        {"student_id": "NSW003", "name": "Chen, Wei", "flag": "LBOTE", "high_risk": True},
        {"student_id": "NSW004", "name": "Williams, Jack", "flag": "ATSI", "high_risk": False},
        {"student_id": "NSW005", "name": "Garcia, Sofia", "flag": "LBOTE", "high_risk": False},
        {"student_id": "NSW006", "name": "Brown, Liam", "flag": None, "high_risk": False},
        {"student_id": "NSW007", "name": "Tran, Linh", "flag": "LBOTE", "high_risk": True},
        {"student_id": "NSW008", "name": "Jones, Olivia", "flag": "EAL/D", "high_risk": False},
    ]

    ELABORATION_OPTIONS = [
        "",
        "Strong oral response",
        "Oral prompting needed",
        "Written output strong",
        "Written output emerging",
        "Oral exceeds written",
        "Written exceeds oral",
        "Off task redirected",
        "VERA hypothesis confirmed",
        "VERA hypothesis challenged",
        "Intervention responding",
        "Intervention not responding",
        "Parent contact needed",
        "Referral recommended",
        "Other"
    ]

    # Header controls
    st.markdown("---")
    col1, col2, col3, col4 = st.columns([2, 2, 2, 1])

    with col1:
        teacher_id = st.text_input("Teacher ID", value="demo_teacher", key="obs_teacher")
    with col2:
        class_period = st.selectbox("Class", ["Year 3A", "Year 3B", "Year 4A", "Year 4B", "Year 5A"], key="obs_period")
    with col3:
        observation_date = st.date_input("Date", value=datetime.now(), key="obs_date")
    with col4:
        if st.button("Mark All Present", use_container_width=True):
            for student in DEMO_ROSTER:
                st.session_state[f"present_{student['student_id']}"] = True

    st.markdown("---")

    # Legend
    st.markdown(f"""
        <div style="display: flex; gap: 20px; margin-bottom: 16px; font-size: 0.85rem;">
            <span><span style="color: #FFA500; font-weight: bold;">●</span> High Risk (VERA)</span>
            <span><span style="color: #4CAF50; font-weight: bold;">●</span> LBOTE</span>
            <span><span style="color: #9C27B0; font-weight: bold;">●</span> ATSI</span>
            <span><span style="color: #2196F3; font-weight: bold;">●</span> EAL/D</span>
        </div>
    """, unsafe_allow_html=True)

    # Column headers
    header_cols = st.columns([3, 1, 1, 1, 1, 1, 1, 3, 2])
    headers = ["**Student**", "**P**", "**Or**", "**Wr**", "**En**", "**!**", "**Ab**", "**Elaboration**", "**Note**"]
    for col, h in zip(header_cols, headers):
        col.markdown(h)

    st.markdown("---")

    # Student roster
    observations_data = []

    for student in DEMO_ROSTER:
        sid = student['student_id']

        if student['high_risk']:
            dot = '<span style="color: #FFA500; font-weight: bold;">●</span>'
        elif student['flag'] == 'LBOTE':
            dot = '<span style="color: #4CAF50; font-weight: bold;">●</span>'
        elif student['flag'] == 'ATSI':
            dot = '<span style="color: #9C27B0; font-weight: bold;">●</span>'
        elif student['flag'] == 'EAL/D':
            dot = '<span style="color: #2196F3; font-weight: bold;">●</span>'
        else:
            dot = '<span style="color: #888;">○</span>'

        cols = st.columns([3, 1, 1, 1, 1, 1, 1, 3, 2])

        with cols[0]:
            st.markdown(f"{dot} {student['name']}", unsafe_allow_html=True)
        with cols[1]:
            present = st.checkbox("P", key=f"present_{sid}", label_visibility="collapsed")
        with cols[2]:
            oral = st.checkbox("Or", key=f"oral_{sid}", label_visibility="collapsed")
        with cols[3]:
            written = st.checkbox("Wr", key=f"written_{sid}", label_visibility="collapsed")
        with cols[4]:
            engaged = st.checkbox("En", key=f"engaged_{sid}", label_visibility="collapsed")
        with cols[5]:
            concern = st.checkbox("!", key=f"concern_{sid}", label_visibility="collapsed")
        with cols[6]:
            absent = st.checkbox("Ab", key=f"absent_{sid}", label_visibility="collapsed")
        with cols[7]:
            elaboration = st.selectbox("Elab", ELABORATION_OPTIONS, key=f"elab_{sid}", label_visibility="collapsed")
        with cols[8]:
            note = st.text_input("Note", key=f"note_{sid}", label_visibility="collapsed", placeholder="...")

        observations_data.append({
            "student_id": sid,
            "present": 1 if present and not absent else 0,
            "oral_participation": 1 if oral else 0,
            "written_output": 1 if written else 0,
            "engaged": 1 if engaged else 0,
            "concern_flag": 1 if concern else 0,
            "absent": 1 if absent else 0,
            "elaboration": elaboration if elaboration else None,
            "note": note if note else None
        })

    # Aggregation bar
    st.markdown("---")
    st.markdown(f"""
        <div style="background: {NAVY}; color: white; padding: 16px; border-radius: 4px;">
            <h4 style="color: {GOLD}; margin: 0;">Today's Aggregation</h4>
        </div>
    """, unsafe_allow_html=True)

    total_students = len(DEMO_ROSTER)
    present_count = sum(1 for o in observations_data if o['present'])
    oral_count = sum(1 for o in observations_data if o['oral_participation'])
    written_count = sum(1 for o in observations_data if o['written_output'])
    concern_count = sum(1 for o in observations_data if o['concern_flag'])

    agg_cols = st.columns(5)
    with agg_cols[0]:
        st.metric("Present", f"{present_count}/{total_students}")
    with agg_cols[1]:
        st.metric("Oral", oral_count)
    with agg_cols[2]:
        st.metric("Written", written_count)
    with agg_cols[3]:
        st.metric("Engaged", sum(1 for o in observations_data if o['engaged']))
    with agg_cols[4]:
        st.metric("Concerns", concern_count)

    # Pattern detection
    if present_count > 0:
        oral_rate = (oral_count / present_count) * 100
        written_rate = (written_count / present_count) * 100
        if oral_rate > written_rate + 15:
            st.warning(f"⚠️ **Pattern detected:** Oral ({oral_rate:.0f}%) exceeds written ({written_rate:.0f}%) by >15%.")

    # Submit
    st.markdown("---")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("💾 SUBMIT OBSERVATIONS", type="primary", use_container_width=True):
            db_path = Path(__file__).parent / "vera_nsw.db"
            conn = sqlite3.connect(str(db_path))

            for obs in observations_data:
                conn.execute("""
                    INSERT INTO observations
                    (teacher_id, school_code, class_period, observation_date, student_id,
                     present, oral_participation, written_output, engaged, concern_flag, absent, elaboration, note)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(teacher_id, observation_date, student_id, class_period)
                    DO UPDATE SET present=excluded.present, oral_participation=excluded.oral_participation,
                        written_output=excluded.written_output, engaged=excluded.engaged,
                        concern_flag=excluded.concern_flag, absent=excluded.absent,
                        elaboration=excluded.elaboration, note=excluded.note
                """, (
                    teacher_id, "demo_school", class_period, observation_date.strftime("%Y-%m-%d"),
                    obs['student_id'], obs['present'], obs['oral_participation'], obs['written_output'],
                    obs['engaged'], obs['concern_flag'], obs['absent'], obs['elaboration'], obs['note']
                ))

            conn.commit()
            conn.close()

            st.success(f"✅ Observations saved for {observation_date.strftime('%Y-%m-%d')} - {class_period}")
            st.balloons()
