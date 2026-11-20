"""Send step: email, CRM log, scheduled follow-up. No LLM calls."""
import csv
import os
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage
from pathlib import Path

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from dotenv import load_dotenv

DATA = Path(__file__).parent / "data"
CRM = DATA / "crm.csv"
FIELDS = ["company", "type", "fit_score", "evidence_links", "status", "sent_at", "followup_at"]

load_dotenv(Path(__file__).parent / ".env")


def send_email(subject: str, body: str) -> None:
    """Send to DEMO_TO_EMAIL via Gmail SSL. Raises on any failure."""
    user, pw, to = (os.environ.get(k, "") for k in ("GMAIL_USER", "GMAIL_APP_PASSWORD", "DEMO_TO_EMAIL"))
    if not (user and pw and to):
        raise RuntimeError("GMAIL_USER, GMAIL_APP_PASSWORD and DEMO_TO_EMAIL must be set in .env")
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = user, to, subject
    msg.set_content(body)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
        s.login(user, pw.replace(" ", ""))
        s.send_message(msg)


def read_crm() -> list[dict]:
    if not CRM.exists():
        return []
    with CRM.open(newline="") as f:
        return list(csv.DictReader(f))


def _write_crm(rows: list[dict]) -> None:
    with CRM.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def append_crm(row: dict) -> None:
    new = not CRM.exists() or CRM.stat().st_size == 0
    with CRM.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in FIELDS})


def followup_job(company: str) -> None:
    """Scheduler job (top-level so it can be pickled by reference)."""
    send_email(f"Following up: {company}",
               f"Hi {company} team,\n\nJust following up on my earlier note. "
               "Happy to find a time that suits you.\n\nThanks!")
    rows = read_crm()
    for r in rows:
        if r["company"] == company and r["status"] == "sent":
            r["status"] = "followed_up"
    _write_crm(rows)


def get_scheduler() -> BackgroundScheduler:
    """Build and start the scheduler. Wrap with st.cache_resource in the app."""
    sched = BackgroundScheduler(jobstores={"default": SQLAlchemyJobStore(url=f"sqlite:///{DATA / 'jobs.db'}")})
    sched.start()
    return sched


def followup_delay() -> timedelta:
    mins = os.environ.get("FOLLOWUP_MINUTES", "").strip()
    return timedelta(minutes=float(mins)) if mins else timedelta(days=3)


def send_and_record(sched, company: str, mtype: str, fit_score: int, links: list[str],
                    subject: str, body: str) -> datetime:
    """Send, log to CRM, schedule follow-up. Raises if the send fails (nothing logged)."""
    send_email(subject, body)
    now = datetime.now()
    due = now + followup_delay()
    append_crm({"company": company, "type": mtype, "fit_score": fit_score,
                "evidence_links": " ".join(links), "status": "sent",
                "sent_at": now.isoformat(timespec="seconds"),
                "followup_at": due.isoformat(timespec="seconds")})
    sched.add_job(followup_job, DateTrigger(run_date=due), args=[company],
                  id=f"followup_{company}", replace_existing=True)
    return now


def scheduled_jobs(sched) -> list[dict]:
    return [{"job_id": j.id, "next_run_time": j.next_run_time} for j in sched.get_jobs()]
