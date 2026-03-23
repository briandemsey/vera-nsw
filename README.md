# VERA-NSW

**Verification Engine for Results & Accountability - New South Wales**

An equity analysis tool that identifies NSW government schools with potential hidden literacy disadvantage — schools where high language diversity (LBOTE) intersects with high socioeconomic disadvantage (FOEI).

## Features

- **School Dashboard** — Browse all ~2,200 NSW government schools with demographics
- **LBOTE Risk Analysis** — Identify schools where language background meets disadvantage
- **Intervention Gap Flags** — Surface schools requiring review
- **CSV Export** — Download data for further analysis

## Data Source

All data from [Data.NSW](https://data.nsw.gov.au) — the NSW Government's open data portal.

- Creative Commons licensed
- No API key required
- Updated nightly (some fields), annually (enrollment)

## Risk Model

VERA-NSW computes an Equity Risk Score (0-100):

| Factor | Weight | Source |
|--------|--------|--------|
| LBOTE % | 40% | Language Background Other Than English |
| FOEI | 40% | Family Occupation and Education Index |
| ICSEA | 20% | Index of Community Socio-Educational Advantage (inverted) |

## The Gap

**NAPLAN assessment results** are required to close the verification loop. Current analysis identifies WHERE risk is concentrated; outcome data would show WHETHER interventions are working.

For NAPLAN access, contact:
- CESE (Centre for Education Statistics and Evaluation)
- ACARA (Australian Curriculum, Assessment and Reporting Authority)

## Local Development

```bash
pip install -r requirements.txt
streamlit run app.py
```

## MCP Server

For Claude Desktop integration:

```bash
pip install mcp
python vera_nsw_mcp_server.py
```

Add to Claude Desktop config:
```json
{
  "mcpServers": {
    "vera-nsw": {
      "command": "python",
      "args": ["C:/path/to/vera_nsw_mcp_server.py"]
    }
  }
}
```

## Deployment

Push to GitHub, then connect to Render. Auto-detects `render.yaml`.

---

*Built by [Hallucinations.cloud](https://hallucinations.cloud)*
