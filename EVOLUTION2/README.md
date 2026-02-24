## Evolution2 – Weekly Executive Report

This project generates a **weekly executive email** for Evolution2 based on the refreshed Excel report.

### Overview

Manual workflow:

1. Open `Evolution2_Report_V13.xlsm`.
2. Click **Refresh All** (Power Query etc.).
3. Save and close the workbook.
4. Run:

```bash
python evo2_weekly_report.py
```

The script:

- Reads the `extract_devis` sheet.
- Computes weekly KPIs.
- Maintains local snapshots/history.
- Sends a dark‑themed executive email via **Resend**.

---

### Project Structure

- `evo2_weekly_report.py` – main script.
- `data/`
  - `confirmed_snapshot.csv` – latest confirmed deals snapshot.
  - `weekly_kpi_history.csv` – per‑week KPI history.
- `logs/`
  - `evo2_weekly_report.log` – run logs.
- `.env` – local environment configuration (see `.env.example`).

Directories `data/` and `logs/` are created automatically next to the script.

---

### Requirements

- **OS**: macOS  
- **Python**: 3.10+ (3.9 ok if `zoneinfo` backport available)
- **Libraries**:
  - `pandas`
  - `openpyxl`
  - `requests`
  - `python-dotenv` (optional but recommended for `.env`)

Install:

```bash
python -m pip install pandas openpyxl requests python-dotenv
```

---

### Configuration

Create a `.env` file next to `evo2_weekly_report.py`:

```bash
cp .env.example .env
```

Edit `.env`:

- **RESEND_API_KEY** – your Resend API key.
- **EMAIL_FROM** – sender address, e.g. `Clove <no-reply@yourdomain.com>`.
- **DROPBOX_REPORT_URL** – shared link to `Evolution2_Report_V13.xlsm`.
- **CLOVE_LOGO_PATH** (optional) – path to Clove logo PNG.
- **EVO2_LOGO_PATH** (optional) – path to Evolution2 logo PNG.

If logo paths are not provided:

- Clove logo defaults to  
  `/Users/davidcraig/code/clove/Clove_Sales_Analyzer/For Web/clove_logo.png`
- Evolution2 logo defaults to `evo2_logo.png` (or `evo2_log.png`) next to the script.

---

### Excel File

The script expects:

- File:  
  `/Users/davidcraig/Evolution2 Events Dropbox/djacraig@hotmail.com/DOSSIERS_TB/Evolution2_Report_V13.xlsm`
- Sheet: `extract_devis`

Key columns (case‑insensitive match):

- `DEVIS_ID` (string)
- `CLIENT_ID` (string)
- `Date_Demande`
- `Date_opération`
- `PDV_DEVIS`
- `CONFIRME`
- `PDV_DEVIS_CONFIRME`
- `CDP`
- `MARGE_FINAL_EVENTS`
- `SITE_EVOLUTION` (fallback to `SITE`)

The script will parse dates and numeric fields with custom logic that matches Excel serials and French‑style numbers.

---

### Weekly Logic

- **Week definition**: Monday → Sunday, using the **last complete week** in `Europe/Paris` timezone.
- **Confirmed**: rows where `CONFIRME == "CONFIRME"` (case‑insensitive).
- There is **no confirmation date**: “confirmed this week” is computed by comparing the current confirmed set vs the previous snapshot.

Metrics (based on `Date_Demande`):

1. **Nouveaux clients** – unique `CLIENT_ID`.
2. **Devis proposés** – sum of `PDV_DEVIS`.
3. **Valeur confirmée (nouvelle)** – sum of `PDV_DEVIS_CONFIRME` for newly confirmed `DEVIS_ID` since last run (snapshot diff).
4. **Meilleur CDP** – CDP with highest newly‑confirmed value.

Forward 4 quarters (based on `Date_opération`):

- Only confirmed rows.
- Next 4 quarters starting from the current quarter.
- Sum `PDV_DEVIS_CONFIRME` per quarter.
- Labels: `T1 2026`, `T2 2026`, etc.

---

### Snapshots & History

`data/confirmed_snapshot.csv`:

- Columns: `snapshot_date, DEVIS_ID, PDV_DEVIS_CONFIRME, CDP`.
- Overwritten every run with the **current** confirmed deals.

`data/weekly_kpi_history.csv`:

- Columns:
  - `week_start`
  - `new_clients`
  - `proposed_value`
  - `newly_confirmed_value`
  - `top_cdp`
  - `top_cdp_value`
- One row per Monday (`week_start`).
- Updated (upsert) on each run, then used to compute week‑over‑week deltas.

---

### Email

- Sent via **Resend** to `davevondavrosh@gmail.com`.
- Subject:  
  `Résumé hebdomadaire – Evolution2 – Semaine du {dd/mm/yyyy}`
- Dark “Clove style” layout:
  - Header with Clove and Evolution2 logos.
  - Weekly KPI cards.
  - Deltas vs previous week.
  - 4‑quarter confirmed pipeline table.
  - CTA button **“Ouvrir le rapport complet”** to `DROPBOX_REPORT_URL`.

Logos are embedded inline as base64 PNGs.

---

### Running

After refreshing and saving the Excel workbook:

```bash
cd /Users/davidcraig/code/clove/EVOLUTION2
python evo2_weekly_report.py
```

Console output example:

```text
Week analysed: 2026-02-02 → 2026-02-08
New clients: 7
Proposed: 123456.78
Newly confirmed: 54321.00
Top CDP: Alice Martin (32100.00)
Email sent to: davevondavrosh@gmail.com
```

If anything fails, check:

- Terminal output.
- `logs/evo2_weekly_report.log` for detailed stack traces and warnings.

---

### Troubleshooting

- **“Excel file not found”** – verify the path in `EXCEL_PATH` inside `evo2_weekly_report.py`.
- **Resend error** – check `RESEND_API_KEY`, `EMAIL_FROM`, and Resend dashboard.
- **Missing columns** – verify column names in `extract_devis` sheet; the script does case‑insensitive matching but relies on the logical names listed above.
- **No email received** – confirm spam folder and that `EMAIL_FROM` domain is authorised in Resend.

