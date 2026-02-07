# main.py
import os
import json
import requests
from datetime import date, datetime, timedelta
from collections import defaultdict
from typing import List, Dict

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.responses import Response
from pydantic import BaseModel

from sqlmodel import Session, select, func

from database import init_db, get_session
from models import Team, Standup

from dotenv import load_dotenv
from groq import Groq

from apscheduler.schedulers.background import BackgroundScheduler

# -------------------------------------------------------------
# Load env & Groq client
# -------------------------------------------------------------
load_dotenv()
GROQ_KEY = os.getenv("GROQ_API_KEY")
client = Groq(api_key=GROQ_KEY) if GROQ_KEY else None

# -------------------------------------------------------------
# Utility: AI summarizer using Groq API
# -------------------------------------------------------------
def summarize_standups(standups: List[Standup]) -> str:
    """AI-based summarizer using Groq. Falls back to rule-based summary on error."""
    if not standups:
        return "No stand-up updates found for today."

    raw_text = "\n".join([
        f"User: {s.user_name}\nYesterday: {s.yesterday}\nToday: {s.today}\nBlockers: {s.blockers or 'None'}"
        for s in standups
    ])

    prompt = f"""
You are an assistant summarizing daily stand-up updates.
For each user, provide concise bullet points summarizing their yesterday/today work.
Include blockers if present.
End with one concise overall team summary.

Reports:
{raw_text}
"""

    # Try Groq LLM if configured
    if client:
        try:
            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": "You are a helpful stand-up summary assistant."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print("⚠️ AI summarization failed; falling back to rule-based summary.")
            import traceback
            traceback.print_exc()

    # Fallback - simple rule-based summarizer
    summaries = []
    for s in standups:
        line = f"**{s.user_name}**\n- Yesterday: {s.yesterday}\n- Today: {s.today}"
        if s.blockers and s.blockers.strip().lower() != "none":
            line += f"\n- Blocker: {s.blockers}"
        summaries.append(line)
    overall = "\n\n".join(summaries)
    return f"**Daily Stand-up Summary**\n\n{overall}\n\n**Team Summary:** The team is progressing; check blockers above."

# -------------------------------------------------------------
# App init
# -------------------------------------------------------------
app = FastAPI(title="Smart Standup Orchestrator", version="1.1.0")

@app.on_event("startup")
def on_startup():
    print("Initializing database...")
    init_db()
    start_scheduler()

# -------------------------------------------------------------
# Request models
# -------------------------------------------------------------
class StartStandupRequest(BaseModel):
    team_id: str
    scheduled_by: str | None = None

# -------------------------------------------------------------
# Teams endpoints
# -------------------------------------------------------------
@app.post("/teams")
def create_team(team: Team, session: Session = Depends(get_session)):
    session.add(team)
    session.commit()
    session.refresh(team)
    return team

@app.get("/teams")
def get_teams(session: Session = Depends(get_session)):
    return session.exec(select(Team)).all()

# -------------------------------------------------------------
# Standup endpoints
# -------------------------------------------------------------
@app.post("/standup", status_code=status.HTTP_201_CREATED)
def submit_standup(standup: Standup, session: Session = Depends(get_session)):
    # Validate team
    team = session.get(Team, standup.team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    # Save standup
    session.add(standup)
    session.commit()
    session.refresh(standup)

    # After saving, send only this user's update to Slack (real-time)
    try:
        send_slack_report(team_id=standup.team_id, user_name=standup.user_name)
        print(f"✅ Slack updated automatically for {standup.user_name}")
    except Exception as e:
        # Don't block the user on Slack failures
        print(f"⚠️ Slack auto-update failed for {standup.user_name}: {e}")

    return {"message": "Stand-up submitted successfully", "standup": standup}

@app.get("/standup")
def get_all_standups(session: Session = Depends(get_session)):
    return session.exec(select(Standup)).all()

# -------------------------------------------------------------
# Daily summary endpoint
# -------------------------------------------------------------
@app.get("/report/today/{team_id}")
def get_today_report(team_id: int, session: Session = Depends(get_session)):
    today = date.today()
    tomorrow = today + timedelta(days=1)
    statement = select(Standup).where(
        Standup.team_id == team_id,
        Standup.created_at >= datetime.combine(today, datetime.min.time()),
        Standup.created_at < datetime.combine(tomorrow, datetime.min.time())
    )
    results = session.exec(statement).all()
    report_text = summarize_standups(results)
    return {"team_id": team_id, "date": today.isoformat(), "report": report_text}

# -------------------------------------------------------------
# Risk detection endpoint (pretty JSON)
# -------------------------------------------------------------
@app.get("/risk/today/{team_id}")
def get_risk_report(team_id: int, days_missing: int = 2, session: Session = Depends(get_session)):
    today = datetime.utcnow().date()
    yesterday = today - timedelta(days=1)

    # Recent 7 days entries for repeated blocker / stale detection
    recent_statement = select(Standup).where(
        Standup.team_id == team_id,
        Standup.created_at >= datetime.combine(today - timedelta(days=7), datetime.min.time())
    ).order_by(Standup.user_name, Standup.created_at)
    recent = session.exec(recent_statement).all()

    # Per-user lists
    user_entries = defaultdict(list)
    for s in recent:
        user_entries[s.user_name].append(s)

    risks: List[Dict] = []

    # Stale tasks and repeated blockers
    for user, entries in user_entries.items():
        by_date = {}
        for e in entries:
            by_date[e.created_at.date()] = e
        today_entry = by_date.get(today)
        yesterday_entry = by_date.get(yesterday)

        if today_entry and yesterday_entry:
            if today_entry.today.strip().lower() == yesterday_entry.today.strip().lower():
                risks.append({
                    "user": user,
                    "type": "Stale Task",
                    "description": f"Task unchanged between {yesterday} and {today}: '{today_entry.today}'"
                })

            t_block = (today_entry.blockers or "").strip().lower()
            y_block = (yesterday_entry.blockers or "").strip().lower()
            if t_block and y_block and t_block == y_block and t_block not in ["none", "no blockers", "n/a", "na"]:
                risks.append({
                    "user": user,
                    "type": "Repeated Blocker",
                    "description": f"Same blocker reported on {yesterday} and {today}: '{today_entry.blockers}'"
                })

    # Missing updates: infer members by last posted
    team_recent_stmt = select(Standup.user_name, func.max(Standup.created_at).label("last_at")).where(
        Standup.team_id == team_id
    ).group_by(Standup.user_name)
    rows = session.exec(team_recent_stmt).all()
    for row in rows:
        user = row[0]
        last_at = row[1]
        if last_at is None or last_at.date() < (today - timedelta(days=days_missing - 1)):
            risks.append({
                "user": user,
                "type": "Missing Update",
                "description": f"Last update was on {last_at.date() if last_at else 'never'} — no update in last {days_missing} days."
            })

    result = {"team_id": team_id, "date": today.isoformat(), "risks": risks}
    return Response(content=json.dumps(result, indent=2), media_type="application/json")

# -------------------------------------------------------------
# Dashboard Endpoint (latest per user only)
# -------------------------------------------------------------
@app.get("/dashboard/today/{team_id}")
def get_dashboard(team_id: int, session: Session = Depends(get_session)):
    today = date.today()
    tomorrow = today + timedelta(days=1)

    # fetch today's standups
    statement = select(Standup).where(
        Standup.team_id == team_id,
        Standup.created_at >= datetime.combine(today, datetime.min.time()),
        Standup.created_at < datetime.combine(tomorrow, datetime.min.time())
    )
    standups = session.exec(statement).all()

    # keep only latest entry per user
    latest_entries = {s.user_name: s for s in standups}
    standups = list(latest_entries.values())

    summary = summarize_standups(standups)

    # reuse risk detection summary (7-day window) to include risks in dashboard
    yesterday = today - timedelta(days=1)
    recent_statement = select(Standup).where(
        Standup.team_id == team_id,
        Standup.created_at >= datetime.combine(today - timedelta(days=7), datetime.min.time())
    ).order_by(Standup.user_name, Standup.created_at)
    recent = session.exec(recent_statement).all()

    user_entries = defaultdict(list)
    for s in recent:
        user_entries[s.user_name].append(s)

    risks = []
    for user, entries in user_entries.items():
        by_date = {e.created_at.date(): e for e in entries}
        today_entry = by_date.get(today)
        yesterday_entry = by_date.get(yesterday)
        if today_entry and yesterday_entry:
            if today_entry.today.strip().lower() == yesterday_entry.today.strip().lower():
                risks.append({
                    "user": user,
                    "type": "Stale Task",
                    "description": f"Task unchanged between {yesterday} and {today}: '{today_entry.today}'"
                })
            t_block = (today_entry.blockers or "").strip().lower()
            y_block = (yesterday_entry.blockers or "").strip().lower()
            if t_block and y_block and t_block == y_block and t_block not in ["none", "no blockers", "n/a", "na"]:
                risks.append({
                    "user": user,
                    "type": "Repeated Blocker",
                    "description": f"Same blocker reported on {yesterday} and {today}: '{today_entry.blockers}'"
                })

    dashboard = {
        "team_id": team_id,
        "date": today.isoformat(),
        "summary": summary,
        "risks": risks,
        "updates": [
            {
                "user": s.user_name,
                "yesterday": s.yesterday,
                "today": s.today,
                "blockers": s.blockers,
                "created_at": s.created_at.isoformat()
            } for s in standups
        ]
    }
    return Response(content=json.dumps(dashboard, indent=2), media_type="application/json")

# -------------------------------------------------------------
# Slack delivery (smart: full or per-user)
# -------------------------------------------------------------
def send_slack_report(team_id: int, user_name: str | None = None):
    """
    Sends a Slack message.
    - If user_name is None: produce a full team report (used by scheduler).
    - If user_name is provided: publish only that user's latest update.
    This implementation queries the internal dashboard endpoint and filters client-side,
    so the function is independent of DB session usage and safe for scheduler calls.
    """
    today = date.today()
    dashboard_url = f"http://127.0.0.1:8000/dashboard/today/{team_id}"
    try:
        resp = requests.get(dashboard_url, timeout=10)
        dashboard = resp.json()
    except Exception as e:
        print(f"⚠️ Failed to fetch dashboard for Slack message: {e}")
        dashboard = {"summary": "No summary available.", "risks": [], "updates": []}

    summary = dashboard.get("summary", "No summary available.")
    risks = dashboard.get("risks", [])
    updates = dashboard.get("updates", [])

    # dedupe latest per user (dashboard already does this, but keep safe)
    unique_updates = {u["user"]: u for u in updates}
    updates = list(unique_updates.values())

    # If user_name specified, filter down to only that user
    if user_name:
        updates = [u for u in updates if u["user"].lower() == user_name.lower()]
        # If not found, nothing to post
        if not updates:
            print(f"ℹ️ No today's update found for user {user_name}; skipping Slack post.")
            return
        # create a short summary for the single user
        u = updates[0]
        summary = f"🧍 *{u['user']}*'s latest stand-up:\n- Yesterday: {u['yesterday']}\n- Today: {u['today']}\n- Blockers: {u['blockers'] or 'None'}"

    # Risk text only meaningful for full reports
    if user_name:
        risk_text = "_(No team risk summary for individual updates)_"
    elif not risks:
        risk_text = ":white_check_mark: No major risks detected."
    else:
        risk_text = "\n".join([f"• *{r['user']}* — {r['type']}: {r['description']}" for r in risks])

    # Updates text
    if not updates:
        updates_text = "_No stand-up updates found for today._"
    else:
        updates_text = "\n".join([
            f"• *{u['user']}*\n   • Yesterday: {u['yesterday']}\n   • Today: {u['today']}\n   • Blockers: {u['blockers']}"
            for u in updates
        ])

    title = f"📅 Daily Stand-up Report — {today}" if user_name is None else f"🧍 Stand-up Update — {user_name}"

    message = {
        "blocks": [
            {"type": "header", "text": {"type": "plain_text", "text": title}},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*Team ID:* {team_id}"}},
            {"type": "divider"},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*🧠 Summary:*\n{summary}"}},
        ]
    }

    if user_name is None:
        message["blocks"].extend([
            {"type": "divider"},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*⚠️ Risks:*\n{risk_text}"}},
        ])

    message["blocks"].extend([
        {"type": "divider"},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*🧾 Updates:*\n{updates_text}"}},
        {"type": "context", "elements": [{"type": "mrkdwn", "text": "_Generated automatically by Smart Daily Stand-up Reporter 🤖_"}]}
    ])

    slack_webhook = os.getenv("SLACK_WEBHOOK_URL")
    if not slack_webhook:
        print("⚠️ SLACK_WEBHOOK_URL not configured; skipping Slack post.")
        return

    r = requests.post(slack_webhook, json=message, timeout=10)
    if r.status_code != 200:
        print(f"⚠️ Slack post failed: {r.status_code} - {r.text}")
    else:
        kind = "full team report" if user_name is None else f"{user_name}'s update"
        print(f"✅ Slack {kind} posted for team {team_id}")

# -------------------------------------------------------------
# Optional endpoint to trigger slack manually
# -------------------------------------------------------------
@app.post("/notify/slack/{team_id}")
def notify_slack(team_id: int):
    send_slack_report(team_id, None)
    return {"message": "Report successfully queued for Slack."}

# -------------------------------------------------------------
# Scheduler (reload-safe)
# -------------------------------------------------------------
_scheduler = None
def start_scheduler():
    global _scheduler
    if _scheduler and _scheduler.running:
        print("Scheduler already running; skipping re-init.")
        return
    _scheduler = BackgroundScheduler()
    # full-team daily report at 10:00
    _scheduler.add_job(lambda: send_slack_report(1, None), "cron", hour=10, minute=0)
    _scheduler.start()
    print("✅ Daily Slack auto-report scheduled for 10:00 AM")

# -------------------------------------------------------------
# Health + start-standup small endpoints
# -------------------------------------------------------------
@app.get("/health")
async def health():
    return {"status": "ok", "date": date.today().isoformat()}

@app.post("/start-standup")
async def start_standup(payload: StartStandupRequest):
    # placeholder for a scheduler trigger or webhook invocation
    return {"message": "standup trigger received", "team_id": payload.team_id, "scheduled_by": payload.scheduled_by}

