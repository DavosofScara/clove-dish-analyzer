#!/usr/bin/env python3
"""
Mumma email attachment fetcher.

Connects to an IMAP inbox, finds weekly Lightspeed reports that land every
Monday morning, downloads CSV attachments, and drops them into the raw
directories consumed by `lightspeed_clean_pipeline.py`. Optionally triggers
the cleaner immediately after new files are saved.
"""
from __future__ import annotations

import argparse
import email
import imaplib
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import Message
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

# Load environment variables from .env.local if it exists
try:
    from dotenv import load_dotenv
    SCRIPT_DIR = Path(__file__).resolve().parent
    ENV_FILE = SCRIPT_DIR / ".env.local"
    if ENV_FILE.exists():
        load_dotenv(ENV_FILE, override=True)
except ImportError:
    pass  # python-dotenv not installed, rely on system env vars

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAW_TRANSACTIONS = REPO_ROOT / "data" / "mumma" / "raw" / "transactions"
DEFAULT_RAW_PRODUCTS = REPO_ROOT / "data" / "mumma" / "raw" / "products"
DEFAULT_STATE_PATH = REPO_ROOT / "data" / "mumma" / "state" / "email_attachments.json"
PIPELINE_SCRIPT = REPO_ROOT / "pipelines" / "mumma" / "lightspeed_clean_pipeline.py"
WEEKLY_REPORT_SCRIPT = REPO_ROOT / "pipelines" / "mumma" / "mumma_weekly_report.py"
UPDATE_MASTER_SCRIPT = REPO_ROOT / "pipelines" / "mumma" / "update_mumma_master.py"


@dataclass
class EmailConfig:
    host: str
    username: str
    password: str
    mailbox: str = "INBOX"
    sender_filter: Optional[str] = None
    subject_keywords: Tuple[str, ...] = ("Lightspeed", "Transaction", "Report")
    lookback_hours: int = 72
    allowed_extensions: Tuple[str, ...] = (".csv", ".CSV")


def load_state(state_path: Path) -> Dict[str, Dict[str, str]]:
    if not state_path.exists():
        return {}
    try:
        return json.loads(state_path.read_text())
    except json.JSONDecodeError:
        return {}


def save_state(state_path: Path, state: Dict[str, Dict[str, str]]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True))


def connect_imap(cfg: EmailConfig) -> imaplib.IMAP4_SSL:
    client = imaplib.IMAP4_SSL(cfg.host)
    client.login(cfg.username, cfg.password)
    client.select(cfg.mailbox)
    return client


def sender_filters(cfg: EmailConfig) -> List[str]:
    if not cfg.sender_filter:
        return []
    return [s.strip().lower() for s in cfg.sender_filter.split(",") if s.strip()]


def sender_matches(msg: Message, cfg: EmailConfig) -> bool:
    """Match any configured sender address against the From header (in-Python filter)."""
    filters = sender_filters(cfg)
    if not filters:
        return True
    from_header = (msg.get("From") or "").lower()
    return any(sender in from_header for sender in filters)


def search_messages(client: imaplib.IMAP4_SSL, cfg: EmailConfig) -> List[bytes]:
    since_date = (datetime.now(timezone.utc) - timedelta(hours=cfg.lookback_hours)).strftime("%d-%b-%Y")
    # Search by date only; filter sender/subject in Python. IMAP FROM is brittle when
    # Lightspeed changes the noreply address (e.g. lsk.lightspeedhq.com -> lightspeedhq.com).
    criteria = ["SINCE", since_date]
    status, data = client.search(None, *criteria)
    if status != "OK":
        raise RuntimeError(f"IMAP search failed: {status}")
    message_ids = data[0].split()
    return message_ids


def message_matches(msg: Message, cfg: EmailConfig) -> bool:
    if not sender_matches(msg, cfg):
        return False
    if not cfg.subject_keywords:
        return True
    subject = msg.get("Subject", "")
    return any(keyword.lower() in subject.lower() for keyword in cfg.subject_keywords)


def determine_destination(filename: str) -> Path:
    lower = filename.lower()
    if "product" in lower or "sku" in lower:
        return DEFAULT_RAW_PRODUCTS
    return DEFAULT_RAW_TRANSACTIONS


def wait_for_files_ready(
    paths: List[Path],
    *,
    stable_seconds: float = 5.0,
    poll_interval: float = 2.0,
    timeout_seconds: float = 120.0,
    min_size_bytes: int = 100,
) -> bool:
    """Wait until files have stable sizes (no change for stable_seconds) and meet min_size.
    Returns True if all files are ready, False if timeout.
    Handles Dropbox/sync delay where files may still be writing after initial save.
    """
    if not paths:
        return True
    start = time.monotonic()
    last_sizes: Dict[Path, int] = {}
    stable_since: Dict[Path, float] = {}
    for p in paths:
        last_sizes[p] = -1
        stable_since[p] = time.monotonic()

    while (time.monotonic() - start) < timeout_seconds:
        all_ready = True
        now = time.monotonic()
        for p in paths:
            if not p.exists():
                all_ready = False
                stable_since[p] = now
                continue
            try:
                sz = p.stat().st_size
            except OSError:
                all_ready = False
                stable_since[p] = now
                continue
            if sz < min_size_bytes:
                all_ready = False
                stable_since[p] = now
                last_sizes[p] = sz
                continue
            if sz != last_sizes.get(p, -1):
                last_sizes[p] = sz
                stable_since[p] = now
                all_ready = False
            elif (now - stable_since[p]) < stable_seconds:
                all_ready = False
        if all_ready:
            print(f"✅ All {len(paths)} file(s) ready (stable for {stable_seconds}s, min {min_size_bytes}B)")
            return True
        time.sleep(poll_interval)

    print(f"⚠️ Timeout after {timeout_seconds}s waiting for files to stabilize; proceeding anyway")
    return False


def save_attachment(part: Message, dest_dir: Path, prefix: str) -> Path:
    filename = part.get_filename()
    if not filename:
        filename = f"attachment_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.csv"
    dest_dir.mkdir(parents=True, exist_ok=True)
    sanitized = filename.replace(" ", "_")
    dest_path = dest_dir / f"{prefix}_{sanitized}"
    with open(dest_path, "wb") as f:
        f.write(part.get_payload(decode=True))
    return dest_path


def process_messages(
    client: imaplib.IMAP4_SSL,
    message_ids: Iterable[bytes],
    cfg: EmailConfig,
    state: Dict[str, Dict[str, str]],
) -> List[Path]:
    saved_files: List[Path] = []
    for msg_id in message_ids:
        status, data = client.fetch(msg_id, "(RFC822)")
        if status != "OK":
            continue
        msg = email.message_from_bytes(data[0][1])
        message_token = msg.get("Message-ID", f"{msg_id.decode()}")
        if message_token in state:
            continue
        if not message_matches(msg, cfg):
            continue

        attachment_paths: List[str] = []
        for part in msg.walk():
            if part.get_content_disposition() != "attachment":
                continue
            filename = part.get_filename()
            if not filename:
                continue
            extension = Path(filename).suffix
            if extension not in cfg.allowed_extensions:
                continue

            dest_dir = determine_destination(filename)
            prefix = datetime.utcnow().strftime("%Y%m%d")
            saved_path = save_attachment(part, dest_dir, prefix)
            saved_files.append(saved_path)
            attachment_paths.append(str(saved_path))

        if attachment_paths:
            state[message_token] = {
                "saved_at": datetime.utcnow().isoformat() + "Z",
                "attachments": attachment_paths,
                "subject": msg.get("Subject", ""),
            }

    return saved_files


def run_pipeline(output: Optional[Path] = None, metadata: Optional[Path] = None, skip_dropbox: bool = True) -> subprocess.CompletedProcess:
    cmd = [
        sys.executable,
        str(PIPELINE_SCRIPT),
        "--raw-transactions",
        str(DEFAULT_RAW_TRANSACTIONS),
        "--raw-products",
        str(DEFAULT_RAW_PRODUCTS),
    ]
    if output:
        cmd.extend(["--output", str(output)])
    if metadata:
        cmd.extend(["--metadata", str(metadata)])
    if skip_dropbox:
        cmd.append("--skip-dropbox")
    return subprocess.run(cmd, check=True)


def run_weekly_report(*, no_email: bool = False) -> subprocess.CompletedProcess:
    """Invoke the Mumma weekly insights report script after a successful pipeline run."""
    if not WEEKLY_REPORT_SCRIPT.exists():
        # Fail silently if the script is not present; pipeline output is still valid.
        print("ℹ️ Weekly report script not found; skipping report generation.")
        return subprocess.CompletedProcess(args=[], returncode=0)

    dry_run = no_email or os.getenv("MUMMA_DRY_RUN", "").lower() in ("1", "true", "yes")
    if dry_run:
        print("📧 Generating MUMMA Weekly Insights Report (dry run — no email)...")
    else:
        print("📧 Generating and sending MUMMA Weekly Insights Report...")
    cmd = [sys.executable, str(WEEKLY_REPORT_SCRIPT)]
    if dry_run:
        cmd.append("--no-email")
    return subprocess.run(cmd, check=True)


def update_mumma_master() -> subprocess.CompletedProcess:
    """Update the shared MUMMA_MASTER_2526.xlsx Excel file with the latest daily sales."""
    if not UPDATE_MASTER_SCRIPT.exists():
        print("ℹ️ Excel updater script not found; skipping MUMMA_MASTER update.")
        return subprocess.CompletedProcess(args=[], returncode=0)

    print("📊 Updating MUMMA_MASTER_2526.xlsx with latest daily sales...")
    return subprocess.run(
        [sys.executable, str(UPDATE_MASTER_SCRIPT)],
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Download weekly Lightspeed CSV attachments from email.")
    parser.add_argument("--host", default=os.getenv("MUMMA_EMAIL_HOST"), help="IMAP host (e.g., imap.gmail.com)")
    parser.add_argument("--username", default=os.getenv("MUMMA_EMAIL_USER"), help="IMAP username / email address")
    parser.add_argument("--password", default=os.getenv("MUMMA_EMAIL_PASS"), help="IMAP password or app password")
    parser.add_argument("--mailbox", default=os.getenv("MUMMA_EMAIL_MAILBOX", "INBOX"))
    parser.add_argument("--sender", default=os.getenv("MUMMA_EMAIL_SENDER"), help="Filter emails from this sender")
    parser.add_argument("--lookback", type=int, default=int(os.getenv("MUMMA_EMAIL_LOOKBACK_HOURS", "72")))
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH, help="Path to processed-message state JSON")
    parser.add_argument("--subject-keywords", nargs="*", default=["Lightspeed", "Report", "Transactions"])
    parser.add_argument(
        "--wait-stable-seconds",
        type=float,
        default=float(os.getenv("MUMMA_WAIT_STABLE_SECONDS", "0")),
        help="Wait for downloaded CSVs to have stable file size before pipeline. Default 0=disabled (polling can trigger Dropbox re-indexing). Use 5-10 only if sync delay is an issue.",
    )
    parser.add_argument(
        "--wait-timeout-seconds",
        type=float,
        default=float(os.getenv("MUMMA_WAIT_TIMEOUT_SECONDS", "120")),
        help="Max seconds to wait for file stability before proceeding anyway",
    )
    parser.add_argument("--run-pipeline", action="store_true", help="Run the Lightspeed cleaning pipeline if new files were downloaded")
    parser.add_argument(
        "--no-email",
        action="store_true",
        help="When used with --run-pipeline, generate the weekly report but do not send email.",
    )
    parser.add_argument("--pipeline-output", type=Path, default=None, help="Override processed ledger path")
    parser.add_argument("--pipeline-metadata", type=Path, default=None, help="Override metadata output path")
    args = parser.parse_args()

    missing = [name for name, value in (("host", args.host), ("username", args.username), ("password", args.password)) if not value]
    if missing:
        raise SystemExit(f"Missing required email config: {', '.join(missing)}")

    cfg = EmailConfig(
        host=args.host,
        username=args.username,
        password=args.password,
        mailbox=args.mailbox,
        sender_filter=args.sender,
        subject_keywords=tuple(args.subject_keywords),
        lookback_hours=args.lookback,
    )

    state = load_state(args.state)
    client = connect_imap(cfg)
    try:
        message_ids = search_messages(client, cfg)
        saved_files = process_messages(client, message_ids, cfg, state)
    finally:
        client.logout()

    if saved_files:
        save_state(args.state, state)
        print(f"📥 Downloaded {len(saved_files)} new attachment(s):")
        for path in saved_files:
            print(f"   - {path}")
        # Wait for files to stabilize (handles Dropbox sync / delayed writes)
        # before running pipeline, so we don't process incomplete CSVs
        if args.run_pipeline and args.wait_stable_seconds > 0:
            print(f"⏳ Waiting for CSVs to be fully synced (stable for {args.wait_stable_seconds}s)...")
            wait_for_files_ready(
                saved_files,
                stable_seconds=args.wait_stable_seconds,
                timeout_seconds=args.wait_timeout_seconds,
                min_size_bytes=1000,
            )
    else:
        print("No new attachments found.")

    if args.run_pipeline:
        if saved_files:
            print("🚀 Running Lightspeed cleaning pipeline (new attachments downloaded)...")
        else:
            print("🚀 Running Lightspeed cleaning pipeline (no new attachments — refreshing from existing raw data)...")
        run_pipeline(output=args.pipeline_output, metadata=args.pipeline_metadata)
        # Update the shared Mumma Excel workbook with fresh daily sales.
        update_mumma_master()
        # After the ledger and Excel workbook are refreshed, trigger the weekly insights report.
        run_weekly_report(no_email=args.no_email)


if __name__ == "__main__":
    main()

