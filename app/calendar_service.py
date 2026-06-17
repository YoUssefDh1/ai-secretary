"""
Google Calendar integration for the AI receptionist (Phase 2).

Responsibilities:
- Authenticate to Google Calendar (OAuth, token cached after first login).
- Find free appointment slots within business hours.
- Create bookings, refusing any that would double-book.
- Cancel bookings.
- List upcoming appointments.

All times are timezone-aware in config.TIMEZONE (Africa/Tunis).
"""

from __future__ import annotations

import datetime as dt
import os
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from . import config

# Full read/write access to the user's calendars.
SCOPES = ["https://www.googleapis.com/auth/calendar"]

TZ = ZoneInfo(config.TIMEZONE)

# Resolve OAuth file paths relative to the project root (one level up from app/).
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CREDENTIALS_PATH = os.path.join(_ROOT, config.GOOGLE_CREDENTIALS_FILE)
_TOKEN_PATH = os.path.join(_ROOT, config.GOOGLE_TOKEN_FILE)


class SlotUnavailable(Exception):
    """Raised when a requested time is already taken (double-booking blocked)."""


def _parse_hhmm(value: str) -> dt.time:
    hour, minute = (int(x) for x in value.split(":"))
    return dt.time(hour, minute)


class CalendarService:
    """Thin, intent-shaped wrapper over the Google Calendar API."""

    def __init__(self, calendar_id: str | None = None) -> None:
        self.calendar_id = calendar_id or config.GOOGLE_CALENDAR_ID
        self.service = build(
            "calendar", "v3", credentials=self._authenticate(), cache_discovery=False
        )

    # --- auth -------------------------------------------------------------
    def _authenticate(self) -> Credentials:
        creds: Credentials | None = None
        if os.path.exists(_TOKEN_PATH):
            creds = Credentials.from_authorized_user_file(_TOKEN_PATH, SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(_CREDENTIALS_PATH):
                    raise FileNotFoundError(
                        f"Missing {config.GOOGLE_CREDENTIALS_FILE}. Download your "
                        "OAuth client from Google Cloud and place it in the "
                        "project root. See README."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    _CREDENTIALS_PATH, SCOPES
                )
                creds = flow.run_local_server(port=0)
            with open(_TOKEN_PATH, "w", encoding="utf-8") as fh:
                fh.write(creds.to_json())
        return creds

    # --- availability -----------------------------------------------------
    def _busy_intervals(
        self, start: dt.datetime, end: dt.datetime
    ) -> list[tuple[dt.datetime, dt.datetime]]:
        """Busy (start, end) pairs on the calendar within [start, end]."""
        body = {
            "timeMin": start.isoformat(),
            "timeMax": end.isoformat(),
            "timeZone": config.TIMEZONE,
            "items": [{"id": self.calendar_id}],
        }
        resp = self.service.freebusy().query(body=body).execute()
        busy = resp["calendars"][self.calendar_id]["busy"]
        return [
            (
                dt.datetime.fromisoformat(b["start"]),
                dt.datetime.fromisoformat(b["end"]),
            )
            for b in busy
        ]

    def is_free(self, start: dt.datetime, end: dt.datetime) -> bool:
        """True if nothing on the calendar overlaps [start, end)."""
        return not any(
            b_start < end and start < b_end
            for b_start, b_end in self._busy_intervals(start, end)
        )

    def free_slots(
        self, date: dt.date, duration_min: int | None = None
    ) -> list[dt.datetime]:
        """Open appointment start-times on a given date, within business hours."""
        duration_min = duration_min or config.DEFAULT_APPT_MINUTES
        if date.weekday() not in config.BUSINESS_DAYS:
            return []  # closed that day

        day_start = dt.datetime.combine(date, _parse_hhmm(config.OPEN_TIME), tzinfo=TZ)
        day_end = dt.datetime.combine(date, _parse_hhmm(config.CLOSE_TIME), tzinfo=TZ)

        busy = self._busy_intervals(day_start, day_end)
        step = dt.timedelta(minutes=config.SLOT_GRANULARITY_MINUTES)
        duration = dt.timedelta(minutes=duration_min)
        now = dt.datetime.now(TZ)

        slots: list[dt.datetime] = []
        cursor = day_start
        while cursor + duration <= day_end:
            slot_end = cursor + duration
            overlaps = any(b_s < slot_end and cursor < b_e for b_s, b_e in busy)
            if not overlaps and cursor > now:  # don't offer past times
                slots.append(cursor)
            cursor += step
        return slots

    # --- mutations --------------------------------------------------------
    def book(
        self,
        name: str,
        service: str,
        start: dt.datetime,
        duration_min: int | None = None,
    ) -> dict:
        """Create an appointment, refusing to double-book.

        Raises SlotUnavailable if the time is already taken.
        """
        duration_min = duration_min or config.DEFAULT_APPT_MINUTES
        end = start + dt.timedelta(minutes=duration_min)
        if not self.is_free(start, end):
            raise SlotUnavailable(
                f"{start:%A %d %B at %H:%M} is already booked."
            )
        event = {
            "summary": f"{service.title()} - {name}",
            "description": "Booked automatically by the AI receptionist.",
            "start": {"dateTime": start.isoformat(), "timeZone": config.TIMEZONE},
            "end": {"dateTime": end.isoformat(), "timeZone": config.TIMEZONE},
        }
        return (
            self.service.events()
            .insert(calendarId=self.calendar_id, body=event)
            .execute()
        )

    def cancel(self, event_id: str) -> None:
        """Delete an appointment by its event id."""
        self.service.events().delete(
            calendarId=self.calendar_id, eventId=event_id
        ).execute()

    # --- reads ------------------------------------------------------------
    def upcoming(self, days: int = 14) -> list[dict]:
        """Upcoming appointments over the next `days` days, in time order."""
        now = dt.datetime.now(TZ)
        resp = (
            self.service.events()
            .list(
                calendarId=self.calendar_id,
                timeMin=now.isoformat(),
                timeMax=(now + dt.timedelta(days=days)).isoformat(),
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        return resp.get("items", [])

    def find_by_name(self, name: str, days: int = 30) -> list[dict]:
        """Upcoming appointments whose title contains `name` (case-insensitive)."""
        name_l = name.lower()
        return [
            ev
            for ev in self.upcoming(days=days)
            if name_l in ev.get("summary", "").lower()
        ]
