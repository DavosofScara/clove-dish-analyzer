## Evo2 – Weekly commercial email (automation)

This project generates an **automated weekly email** (week/season KPIs + provisional revenue) using the same Excel source as `evo2_weekly_report.py`, plus a **CDP quality** section below the KPIs.

### Language

| Context | Language |
|--------|----------|
| **This README, issues, PRs, and day-to-day dev chat** | **English** |
| **CLI (`--help`), logs, and error messages in the terminal** | **English** |
| **Generated email / HTML report (labels, copy, definitions, chart placeholders)** | **French** (client-facing) |

Keep new user-facing strings in the email template and related output in **French**. Keep repository documentation, developer tooling output, and team communication in **English**.

### Goal

- **Active pipeline (email, French copy):** (1) Dossier counts and (2) Revenue tables include **Période actuelle**, **N-1 (YoY)**, and **Écart** columns (YoY/Écart show `-` until history is wired); **below the CA table**, a **cumulative realised CA chart** (current vs prior same-type season, aligned calendar — see **Définitions**). **Dossiers confirmés (semaine)** = distinct `CLIENT_ID` on the extract whose `NOM_CLIENT`+`NOM_AGENT` key matches **any** row on the Clients sheet with **`DATE CONFIRME`** in the **reference week** (not only the single merged row used for `TYPE_DE_CLIENT`); **Dossiers confirmés (saison)** still use confirmed + `Date_opération` in the full calendar season (proxy). (3) **Conversion par CDP** — table + scatter + **marge budget vs réelle** bar chart (`Marge_Reelle_Devis`, `ALL_LINES_VALIDE = True`, margin % of `PDV_DEVIS_CONFIRME`, simple average per CDP), **full extract** for table/scatter (all periods / dates, not week- or season-filtered). (4) **PDV confirmé par site** — current (blue) + next season (orange) bar charts by **`SITE`**. Footer **Définitions** documents metrics.
- **Archived (not in the email):** former sections (client type, agents, concentration) — see `archive/` below.

### Dependencies

```bash
python -m pip install pandas openpyxl requests python-dotenv matplotlib scipy
```

### Configuration

Reuses `EVOLUTION2/.env` at the repo root:

- `RESEND_API_KEY`
- `EMAIL_FROM`
- `RECIPIENT_EMAIL` or `RECIPIENT_EMAILS`: one or more addresses, **comma- or semicolon-separated** (e.g. `a@x.com,b@y.com`).
- `CC_EMAIL` or `CC_EMAILS` (optional): same format; passed to Resend as `cc`.
- `DROPBOX_REPORT_URL`
- `CLIENT_DB_PATH` (optional): absolute path to **Clients Database.xlsx** on disk (Dropbox-synced folder). Falls back to the path in `config.py` if unset.
- `DROPBOX_CLIENT_DATABASE_URL` (optional): Dropbox **share link** to the same file (documentation / your records; **pandas does not load from this URL** — use a local `CLIENT_DB_PATH`).
- `CLIENT_DB_SHEET_NAME` (optional): sheet name (default **`MARKETING_MAIL`**, unchanged from original). Set **`CLIENTS`** when **DATE CONFIRME** is on that sheet.

### Logos (email header)

The **Clove** image (wordmark + icon + tagline such as *Forensic profits in food and beverage*) is your **Clove** brand logo. `main.py` embeds the **first file that exists** from `CLOVE_LOGO_CANDIDATES` in `src/config.py` (e.g. repo-root `Color logo - no background.png`, then `clove_logo.png`, etc.). **Evolution2** uses `EVO2_LOGO_CANDIDATES` the same way. To change what recipients see, replace the image file or reorder the candidate list.

### Data source

Same workbook as the main weekly report:

```
/Users/davidcraig/Evolution2 Events Dropbox/djacraig@hotmail.com/DOSSIERS_TB/ALL_DOSSIERS_CA_2025/REPORTS/Evolution2_Report_V13.xlsm
```

Sheet: `extract_devis`

**Clients database** (`Clients Database.xlsx`): default sheet **`MARKETING_MAIL`** (as originally). Set **`CLIENT_DB_SHEET_NAME=CLIENTS`** in `.env` if Power Query writes **DATE CONFIRME** there. Used to enrich **`TYPE_DE_CLIENT`** and **`DATE CONFIRME`** → `DATE_CONFIRME_CLIENT` on the extract before KPIs.

### Run

From the `Evo2_Commercial_Report` folder:

```bash
python -m src.main --dry-run
# Optional: reference date for week/season windows (YYYY-MM-DD)
python -m src.main --dry-run --as-of 2026-03-29
```

HTML preview:

```
outputs/commercial_report_preview.html
```

Send via Resend:

```bash
python -m src.main --send
```

### Standalone — cumulative season chart (also embedded in the weekly email)

The same figure is rendered **inline in section 2** of the weekly HTML email (below the CA table). You can still regenerate a PNG locally with:

```bash
python -m src.cumulative_season_yoy --as-of 2026-04-06
python -m src.cumulative_season_yoy --as-of 2026-04-06 --html
# or: ./scripts/run_cumulative_season_yoy.sh
```

Outputs (gitignored by default): `outputs/cumulative_season_yoy.png`, optional `outputs/cumulative_season_yoy_preview.html`.

**Forwarding / Gmail / Outlook:** The **inline** HTML body is often **re-sanitized** on forward or inside a **reply** (layout, colours, embedded images). That is normal and **not fixable** in the sender HTML alone. Mitigations in this project: (**1**) same report attached as **`rapport_evolution2_hebdomadaire.html`** — recipients can **download and open in a browser** for full fidelity; (**2**) the **Dropbox** button for your canonical workbook; (**3**) a short note in the email footer explains the attachment. `send_email(..., attach_html_copy=False)` disables the attachment if needed.

### Schedule — Monday 09:10 (local time)

The report uses the **Mon–Sun week ending on the last Sunday on or before** `--as-of` / today (Monday morning = yesterday’s Sunday; **Sunday same day** = that week, not the prior one).

**Cron (recommended — same idea as other email automations)**  

1. `chmod +x scripts/send_weekly_report.sh`  
2. Open `scripts/crontab.example`, copy **one** line after replacing the absolute path with your `Evo2_Commercial_Report` folder.  
3. `crontab -e` and paste the line.

Example (Monday 09:10, log to `/tmp`):

```cron
10 9 * * 1 /ABSOLUTE/PATH/TO/Evo2_Commercial_Report/scripts/send_weekly_report.sh >> /tmp/evo2-weekly-commercial-cron.log 2>&1
```

- **`10 9 * * 1`** = minute 10, hour 9, every Monday (`1` = Monday; `0`/`7` = Sunday).  
- Use **full paths** in crontab (cron’s `PATH` is minimal).  
- Optional venv: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt` — the shell script uses `.venv/bin/python` when it exists.  
- Test manually first: `./scripts/send_weekly_report.sh` from the project folder.

Ensure the Mac is **awake** at 09:10, `EVOLUTION2/.env` is valid for that user, and the Dropbox Excel path is visible to cron (same user you use interactively).

**macOS launchd (recommended on macOS)**  

Use a Launch Agent so the job runs in your GUI session with predictable paths and logs (no minimal `PATH` surprises).

1. Edit `scripts/com.clove.evo2-weekly-commercial-report.plist` if your repo lives somewhere other than  
   `/Users/davidcraig/code/clove/EVOLUTION2/Evo2_Commercial_Report` (all paths in the plist must match).
2. Install and load (use `/bin/cp -f` so macOS does not prompt to overwrite):

   ```bash
   /bin/cp -f scripts/com.clove.evo2-weekly-commercial-report.plist ~/Library/LaunchAgents/
   launchctl bootout "gui/$(id -u)/com.clove.evo2-weekly-commercial-report" 2>/dev/null || true
   launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/com.clove.evo2-weekly-commercial-report.plist
   ```

3. Verify:

   ```bash
   launchctl print "gui/$(id -u)/com.clove.evo2-weekly-commercial-report"
   ```

4. Logs: `logs/launchd.out.log` and `logs/launchd.err.log` next to this project.

**Do not** also add the same Monday 09:10 line to `crontab` — you would send **two** emails. Pick **either** cron **or** launchd.

See also `scripts/com.clove.evo2-weekly-commercial-report.plist.example` for a template with placeholder paths.

### Notes

- **Section 1 (Nombre de dossiers)** is rendered as a **2×3 card grid** (not a wide table): row **Semaine** then row **Saison**, columns **Dossiers réalisés / propositions envoyées / confirmés** (French labels, no parentheses). Reading **down a column** compares week vs season for the same category.
- Column names are resolved case-insensitively.
- `PDV_DEVIS` may be blank (treated as 0).
- Charts are embedded as base64 (no local file paths in the email).
- **Dossiers réalisés (saison)** = distinct confirmed `CLIENT_ID` with `Date_opération` in **report-to-date** (`season_window_for_metrics`: season start → `min(as_of, season end)`). **Dossiers confirmés (saison)** = distinct confirmed `CLIENT_ID` with `Date_opération` in the **full calendar current season** (e.g. HIVER 15/11–30/04) — proxy until a dedicated confirmation date exists. **Week row:** **réalisés (semaine)** = distinct confirmed `CLIENT_ID` with `Date_opération` in the reference week; **confirmés (semaine)** = distinct `CLIENT_ID` on the extract whose `client_key` matches **any** Clients row with **`DATE CONFIRME`** in that week (raw sheet + `client_db` passed from `main`). **Realised revenue (week)** sums `PDV_DEVIS_CONFIRME` on confirmed rows in the reference week; **realised revenue (season row)** uses the **full calendar current season**, same as proposed dossiers (season). **CONFIRME** (no accent) = **CONFIRMÉ**.
- **Propositions envoyées** (email label; was “Dossiers proposés”) — **week row:** distinct `CLIENT_ID` with at least one **`Date_Demande`** in the **reference week** (Mon–Sun ending last Sunday ≤ report date), **any** `CONFIRME` / any `Date_opération`. **Season row:** distinct `CLIENT_ID` with at least one **`Date_opération`** in **`current_season.start` … `current_season.end`** (full calendar season). **Chiffre d’affaires** lines in the email are labelled **HT** (amounts are ex-VAT). The email **Définitions** block spells out dates for the run.
- **Provisional CA** (`compute_ca_provisionnel`) — **potential season revenue** (updates with `--as-of` / report date): **(1)** Sum `PDV_DEVIS_CONFIRME` on **CONFIRMÉ** rows with `Date_opération` in the **full** calendar season (e.g. HIVER **15/11→30/04 inclusive**). **(2)** Add **pipeline**: **EN COURS** rows (non annulés) with `Date_opération` from the **day after** `min(week_end, season end)` **through** `season end` (e.g. 30/04 for HIVER — not into May). **`week_end`** = Sunday end of that same reference week. Per `CLIENT_ID` in that slice: **sum** `PDV_DEVIS` ÷ **distinct** `DEVIS_ID`, then sum across clients and add to (1). Same structure for the **next** season row.

### Archived modules (optional reactivation)

Code under `archive/` is **not** wired into `main.py`:

- `valeur_stabilite_type_client.py` — client type + stacked chart
- `efficacite_commerciale_agent.py` — agents
- `top5_agents_volume_clients.py` — top 5 by client volume
- `concentration_risque_commercial.py` — concentration

See `archive/README.md` for details.
