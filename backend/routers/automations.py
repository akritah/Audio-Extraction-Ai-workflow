from fastapi import APIRouter, HTTPException
import requests
import os
import json
import logging
from services.automation import MAKE_GMAIL_WEBHOOK_URL, MAKE_CALENDAR_WEBHOOK_URL, post_with_retry, log_automation_attempt

router = APIRouter()
logger = logging.getLogger("uvicorn")


@router.post("/test/gmail")
def test_gmail_webhook():
    """
    Build a sample meeting summary payload, post it to the Gmail webhook, and return the result.
    """
    if not MAKE_GMAIL_WEBHOOK_URL:
        raise HTTPException(status_code=400, detail="MAKE_GMAIL_WEBHOOK_URL environment variable is not configured.")

    payload = {
        "type": "summary",
        "meeting_id": 999,
        "title": "Test Budget Review",
        "summary": "This was a test meeting to verify Gmail and Make.com integrations. We verified webhook triggers, retry handlers, and logging subsystems.",
        "tasks": [
            {"task": "Verify webhook responses", "owner": "Akrit", "deadline": "2026-06-18", "status": "Pending"},
            {"task": "Configure Make.com integrations", "owner": "Unassigned", "deadline": "2026-06-20", "status": "Pending"}
        ],
        "decisions": [
            "Approved the integration design for Make.com webhooks as primary automation layer."
        ],
        "events": [
            {
                "title": "Follow-up Integration Review",
                "date": "2026-06-25",
                "start_time": "15:00",
                "end_time": "16:00",
                "attendees": ["user@example.com", "akrit@example.com"]
            }
        ],
        "generated_at": "2026-06-17T20:00:00Z"
    }

    try:
        logger.info("[Test Automation] Sending test summary payload to Make.com...")
        resp = post_with_retry(MAKE_GMAIL_WEBHOOK_URL, payload)
        log_automation_attempt(999, "gmail", payload, "success", resp.status_code)
        
        try:
            resp_data = resp.json()
        except Exception:
            resp_data = resp.text

        return {
            "status": "success",
            "webhook_status_code": resp.status_code,
            "webhook_response": resp_data
        }
    except Exception as e:
        logger.error(f"[Test Automation] Gmail test failed: {e}")
        log_automation_attempt(999, "gmail", payload, "failed", None)
        raise HTTPException(status_code=500, detail=f"Webhook delivery failed: {str(e)}")


@router.post("/test/calendar")
def test_calendar_webhook():
    """
    Build a sample calendar event payload, post it to the Google Calendar webhook, and return the result.
    """
    if not MAKE_CALENDAR_WEBHOOK_URL:
        raise HTTPException(status_code=400, detail="MAKE_CALENDAR_WEBHOOK_URL environment variable is not configured.")

    payload = {
        "type": "event",
        "meeting_id": 999,
        "title": "Test Budget Review Event",
        "date": "2026-06-25",
        "start_time": "15:00",
        "end_time": "16:00",
        "attendees": ["user@example.com"]
    }

    try:
        logger.info("[Test Automation] Sending test event payload to Make.com...")
        resp = post_with_retry(MAKE_CALENDAR_WEBHOOK_URL, payload)
        log_automation_attempt(999, "calendar", payload, "success", resp.status_code)

        try:
            resp_data = resp.json()
        except Exception:
            resp_data = resp.text

        return {
            "status": "success",
            "webhook_status_code": resp.status_code,
            "webhook_response": resp_data
        }
    except Exception as e:
        logger.error(f"[Test Automation] Calendar test failed: {e}")
        log_automation_attempt(999, "calendar", payload, "failed", None)
        raise HTTPException(status_code=500, detail=f"Webhook delivery failed: {str(e)}")
