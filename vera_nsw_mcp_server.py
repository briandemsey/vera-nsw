"""
VERA-NSW MCP Server
Verification Engine for Results & Accountability - New South Wales

An MCP server that connects Claude to NSW Department of Education open data
via Data.NSW APIs. Identifies schools with hidden language-based literacy
disadvantage using LBOTE and FOEI indices.

Tools:
1. list_nsw_schools - Query all NSW government schools with demographics
2. compute_lbote_risk_profile - Analyze LBOTE vs disadvantage correlation
3. flag_intervention_gap_schools - Identify high-risk, low-visibility schools
"""

import json
import requests
from typing import Optional
from mcp.server.fastmcp import FastMCP

# Initialize MCP server
mcp = FastMCP("vera-nsw")

# Data.NSW API configuration
BASE_URL = "https://data.nsw.gov.au/data/api/action/datastore_search"
MASTER_RESOURCE_ID = "3e6d5f6a-055c-440d-a690-fc0537c31095"

# Cache for school data
_school_cache = None


def fetch_all_schools() -> list:
    """Fetch all NSW government schools from Data.NSW API."""
    global _school_cache

    if _school_cache is not None:
        return _school_cache

    all_schools = []
    offset = 0
    limit = 500

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

            # Check if we've fetched all records
            total = data.get("result", {}).get("total", 0)
            if offset >= total:
                break

        except Exception as e:
            print(f"Error fetching schools: {e}", file=__import__('sys').stderr)
            break

    _school_cache = all_schools
    return all_schools


def safe_float(value, default=0.0) -> float:
    """Safely convert a value to float."""
    try:
        if value is None or value == "" or value == "np":
            return default
        return float(value)
    except (ValueError, TypeError):
        return default


def compute_risk_score(school: dict) -> float:
    """
    Compute equity risk score for a school.

    Higher LBOTE% + Higher FOEI (disadvantage) + Lower ICSEA = Higher Risk

    Risk Score = (LBOTE% / 100) * (FOEI / 200) * (1 - ICSEA/1200)
    Normalized to 0-100 scale.
    """
    lbote = safe_float(school.get("LBOTE_pct", 0))
    foei = safe_float(school.get("FOEI_Value", 0))
    icsea = safe_float(school.get("ICSEA_value", 1000))

    # Normalize components
    lbote_factor = min(lbote / 100, 1.0)
    foei_factor = min(foei / 200, 1.0)  # FOEI typically 0-200
    icsea_factor = max(0, 1 - (icsea / 1200))  # Lower ICSEA = higher risk

    # Combined risk score (0-100)
    risk = (lbote_factor * 0.4 + foei_factor * 0.4 + icsea_factor * 0.2) * 100

    return round(risk, 2)


@mcp.tool()
def list_nsw_schools(
    school_type: Optional[str] = None,
    min_enrollment: Optional[int] = None,
    min_lbote_pct: Optional[float] = None,
    suburb: Optional[str] = None,
    limit: int = 50
) -> str:
    """
    List NSW government schools with demographic data.

    Args:
        school_type: Filter by type (e.g., "Primary School", "High School", "Central School")
        min_enrollment: Minimum student enrollment
        min_lbote_pct: Minimum LBOTE percentage (Language Background Other Than English)
        suburb: Filter by suburb name (partial match)
        limit: Maximum number of results (default 50)

    Returns:
        JSON array of schools with demographics including ICSEA, FOEI, LBOTE%, Indigenous%
    """
    schools = fetch_all_schools()

    # Apply filters
    filtered = []
    for school in schools:
        # School type filter
        if school_type:
            st = school.get("School_subtype", "").lower() if school.get("School_subtype") else ""
            if school_type.lower() not in st:
                continue

        # Enrollment filter
        if min_enrollment:
            enrollment = safe_float(school.get("latest_year_enrolment_FTE", 0))
            if enrollment < min_enrollment:
                continue

        # LBOTE filter
        if min_lbote_pct:
            lbote = safe_float(school.get("LBOTE_pct", 0))
            if lbote < min_lbote_pct:
                continue

        # Suburb filter
        if suburb:
            school_suburb = school.get("Town_suburb", "").lower() if school.get("Town_suburb") else ""
            if suburb.lower() not in school_suburb:
                continue

        # Compute risk score
        risk_score = compute_risk_score(school)

        filtered.append({
            "school_code": school.get("School_code"),
            "school_name": school.get("School_name"),
            "school_type": school.get("School_subtype"),
            "suburb": school.get("Town_suburb"),
            "postcode": school.get("Postcode"),
            "enrollment": safe_float(school.get("latest_year_enrolment_FTE", 0)),
            "icsea": safe_float(school.get("ICSEA_value", 0)),
            "foei": safe_float(school.get("FOEI_Value", 0)),
            "lbote_pct": safe_float(school.get("LBOTE_pct", 0)),
            "indigenous_pct": safe_float(school.get("Indigenous_pct", 0)),
            "remoteness": school.get("ASGS_remoteness"),
            "lga": school.get("LGA"),
            "risk_score": risk_score
        })

    # Sort by risk score descending
    filtered.sort(key=lambda x: x["risk_score"], reverse=True)

    return json.dumps({
        "total_matching": len(filtered),
        "showing": min(limit, len(filtered)),
        "schools": filtered[:limit]
    }, indent=2)


@mcp.tool()
def compute_lbote_risk_profile(
    min_lbote_pct: float = 30.0,
    min_foei: float = 100.0
) -> str:
    """
    Analyze schools where high LBOTE (Language Background Other Than English)
    intersects with high disadvantage (FOEI), identifying potential hidden
    literacy gaps - the Australian equivalent of VERA's Type 4 analysis.

    Args:
        min_lbote_pct: Minimum LBOTE percentage threshold (default 30%)
        min_foei: Minimum FOEI (disadvantage index) threshold (default 100)

    Returns:
        Analysis of schools with high language diversity and high disadvantage,
        where literacy interventions may be under-resourced.
    """
    schools = fetch_all_schools()

    # Find schools meeting both criteria
    high_risk = []
    total_schools = len(schools)
    total_lbote_above = 0
    total_foei_above = 0

    for school in schools:
        lbote = safe_float(school.get("LBOTE_pct", 0))
        foei = safe_float(school.get("FOEI_Value", 0))
        icsea = safe_float(school.get("ICSEA_value", 1000))
        enrollment = safe_float(school.get("latest_year_enrolment_FTE", 0))

        if lbote >= min_lbote_pct:
            total_lbote_above += 1
        if foei >= min_foei:
            total_foei_above += 1

        if lbote >= min_lbote_pct and foei >= min_foei:
            risk_score = compute_risk_score(school)
            high_risk.append({
                "school_code": school.get("School_code"),
                "school_name": school.get("School_name"),
                "school_type": school.get("School_subtype"),
                "suburb": school.get("Town_suburb"),
                "lga": school.get("LGA"),
                "enrollment": enrollment,
                "lbote_pct": lbote,
                "foei": foei,
                "icsea": icsea,
                "risk_score": risk_score,
                "students_at_risk": int(enrollment * (lbote / 100)) if lbote > 0 else 0
            })

    # Sort by risk score
    high_risk.sort(key=lambda x: x["risk_score"], reverse=True)

    # Calculate totals
    total_students_at_risk = sum(s["students_at_risk"] for s in high_risk)
    total_enrollment = sum(s["enrollment"] for s in high_risk)

    return json.dumps({
        "analysis": "LBOTE Risk Profile - Schools with High Language Diversity and High Disadvantage",
        "thresholds": {
            "min_lbote_pct": min_lbote_pct,
            "min_foei": min_foei
        },
        "summary": {
            "total_nsw_schools": total_schools,
            "schools_above_lbote_threshold": total_lbote_above,
            "schools_above_foei_threshold": total_foei_above,
            "schools_meeting_both_criteria": len(high_risk),
            "percentage_of_all_schools": round(len(high_risk) / total_schools * 100, 1) if total_schools > 0 else 0,
            "total_enrollment_in_flagged_schools": int(total_enrollment),
            "estimated_students_at_risk": total_students_at_risk
        },
        "interpretation": (
            f"These {len(high_risk)} schools have both high LBOTE concentration (>{min_lbote_pct}%) "
            f"and high disadvantage (FOEI>{min_foei}). This combination indicates potential hidden "
            "literacy gaps where students from non-English speaking backgrounds face socioeconomic "
            "barriers that may not be fully addressed by current intervention programs. "
            f"Approximately {total_students_at_risk:,} students are in this high-risk cohort."
        ),
        "top_20_highest_risk": high_risk[:20]
    }, indent=2)


@mcp.tool()
def flag_intervention_gap_schools(
    risk_threshold: float = 50.0,
    school_type: Optional[str] = None
) -> str:
    """
    Identify schools with the highest intervention gap - where equity risk
    is high but current visibility/funding mechanisms may be insufficient.

    This flags schools that are the NSW equivalent of VERA's Type 4 candidates:
    high language diversity + high disadvantage + low socioeconomic index.

    Args:
        risk_threshold: Minimum risk score to flag (0-100, default 50)
        school_type: Filter by type (e.g., "Primary", "High", "Central")

    Returns:
        Ranked list of schools requiring intervention review.
    """
    schools = fetch_all_schools()

    flagged = []

    for school in schools:
        # Apply school type filter
        if school_type:
            st = school.get("School_subtype", "").lower() if school.get("School_subtype") else ""
            if school_type.lower() not in st:
                continue

        risk_score = compute_risk_score(school)

        if risk_score >= risk_threshold:
            lbote = safe_float(school.get("LBOTE_pct", 0))
            foei = safe_float(school.get("FOEI_Value", 0))
            icsea = safe_float(school.get("ICSEA_value", 1000))
            enrollment = safe_float(school.get("latest_year_enrolment_FTE", 0))
            indigenous = safe_float(school.get("Indigenous_pct", 0))

            # Determine gap type
            gap_factors = []
            if lbote > 50:
                gap_factors.append("High LBOTE")
            if foei > 120:
                gap_factors.append("High Disadvantage")
            if icsea < 950:
                gap_factors.append("Low Socioeconomic")
            if indigenous > 20:
                gap_factors.append("High Indigenous")

            flagged.append({
                "school_code": school.get("School_code"),
                "school_name": school.get("School_name"),
                "school_type": school.get("School_subtype"),
                "suburb": school.get("Town_suburb"),
                "postcode": school.get("Postcode"),
                "lga": school.get("LGA"),
                "remoteness": school.get("ASGS_remoteness"),
                "enrollment": int(enrollment),
                "lbote_pct": lbote,
                "indigenous_pct": indigenous,
                "foei": foei,
                "icsea": icsea,
                "risk_score": risk_score,
                "gap_factors": gap_factors,
                "estimated_at_risk_students": int(enrollment * (lbote / 100)) if lbote > 0 else 0
            })

    # Sort by risk score descending
    flagged.sort(key=lambda x: x["risk_score"], reverse=True)

    # Group by LGA for geographic analysis
    lga_counts = {}
    for school in flagged:
        lga = school.get("lga", "Unknown")
        lga_counts[lga] = lga_counts.get(lga, 0) + 1

    top_lgas = sorted(lga_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    total_at_risk = sum(s["estimated_at_risk_students"] for s in flagged)

    return json.dumps({
        "analysis": "Intervention Gap Schools - Flagged for Review",
        "threshold": risk_threshold,
        "school_type_filter": school_type or "All",
        "summary": {
            "total_flagged": len(flagged),
            "total_students_in_flagged_schools": sum(s["enrollment"] for s in flagged),
            "estimated_at_risk_students": total_at_risk,
            "top_lgas_by_flagged_schools": dict(top_lgas)
        },
        "action_required": (
            f"{len(flagged)} schools have been flagged with risk scores above {risk_threshold}. "
            "These schools have combinations of high LBOTE concentration, high disadvantage (FOEI), "
            "and low socioeconomic indices (ICSEA) that indicate potential gaps in literacy "
            "intervention coverage. Without NAPLAN outcome data, we cannot verify whether current "
            "interventions are effective. These schools are candidates for deeper review."
        ),
        "data_gap_note": (
            "NAPLAN assessment results are required to close the verification loop. "
            "Current analysis identifies WHERE risk is concentrated; outcome data would show "
            "WHETHER interventions are working. Contact CESE or ACARA for NAPLAN data access."
        ),
        "flagged_schools": flagged[:50]
    }, indent=2)


if __name__ == "__main__":
    import sys
    # Run in stdio mode for Claude Desktop
    mcp.run()
