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
        ["📊 School Dashboard", "🔍 LBOTE Risk Analysis", "🚩 Intervention Gaps", "ℹ️ About VERA-NSW"],
        label_visibility="collapsed"
    )

    st.markdown(f"""<hr style="border: none; border-top: 1px solid rgba(255,255,255,0.5); margin: 20px 0;">""", unsafe_allow_html=True)

    # VERA logo and version
    col1, col2 = st.columns([1, 2])
    with col1:
        st.image("vera_logo.png", width=85)
    with col2:
        st.markdown(f"""
            <p style="color: white; font-size: 0.85rem; margin-top: 15px; font-weight: 500;">
                VERA-NSW v0.1<br>
                <a href="https://data.nsw.gov.au" style="color: {GOLD}; font-size: 0.8rem;">Data.NSW</a>
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
