"""
The booking-capable dialogue manager (Phase 3).

This ties the conversational brain (gemma2 via Ollama) to the real Google
Calendar. It uses a deliberate split of responsibilities:

  * The LLM does LANGUAGE: understanding the caller, extracting the booking
    details (name / service / date / time) from messy natural speech, and
    answering free-form questions.
  * Plain Python does FACTS: checking real availability, booking, cancelling,
    and stating confirmed times. Critical details (the actual date and time of
    an appointment) are produced by code and never paraphrased by the model, so
    the model cannot drift and confirm the wrong slot.

The result is a natural conversation whose bookings are always correct.
"""

from __future__ import annotations

import datetime as dt
import json
import re

import dateparser
import ollama

from . import config
from .calendar_service import CalendarService, SlotUnavailable, TZ

# How many alternative slots to offer when a time is unavailable.
_MAX_SLOTS_OFFERED = 6

# "this"/"next"/etc. before a weekday defeat the date parser; we strip and retry.
_DATE_QUALIFIER = re.compile(
    r"\b(this|next|coming|upcoming|ce|cette|prochain|prochaine)\b", re.I
)


def _today_context() -> str:
    now = dt.datetime.now(TZ)
    return f"{now:%A}, {now:%Y-%m-%d}"


class BookingDialog:
    """One phone/text conversation that can actually book against the calendar."""

    def __init__(self, calendar: CalendarService | None = None) -> None:
        self.calendar = calendar or CalendarService()
        self._client = ollama.Client(host=config.OLLAMA_HOST)
        # Running transcript used for extraction and free-form answers.
        self.transcript: list[dict] = []
        # Merged booking state, accumulated across turns.
        self.state: dict = {
            "intent": "unknown",
            "name": None,
            "service": None,
            "date": None,
            "time": None,
        }
        # Slots already booked in THIS conversation. Because we re-extract the
        # booking from the whole transcript each turn, a completed booking would
        # otherwise be re-derived and re-attempted (colliding with itself). We
        # remember booked start-times and refuse to book the same one twice.
        self._booked_starts: set[dt.datetime] = set()

    # --- public API -------------------------------------------------------
    def greeting(self) -> str:
        b = config.BUSINESS
        line = (
            f"Thank you for calling {b['name']}, this is "
            f"{b['receptionist_name']}. How can I help you today?"
        )
        self.transcript.append({"role": "assistant", "content": line})
        return line

    def respond(self, user_text: str) -> str:
        self.transcript.append({"role": "user", "content": user_text})
        self._update_state()

        intent = self.state["intent"]
        if intent == "cancel":
            reply = self._handle_cancel()
        elif intent == "book":
            reply = self._handle_booking()
        elif intent == "info":
            reply = self._answer_question()
        else:
            reply = self._smalltalk()

        self.transcript.append({"role": "assistant", "content": reply})
        return reply

    # --- LLM: understanding ----------------------------------------------
    def _update_state(self) -> None:
        """Re-extract booking details from the whole conversation (JSON mode)."""
        services = ", ".join(config.BUSINESS["services"])
        prompt = (
            "You extract appointment details from a conversation between a "
            f"caller and a receptionist at {config.BUSINESS['name']}.\n"
            f"Today is {_today_context()} (timezone {config.TIMEZONE}).\n"
            f"Known services: {services}.\n\n"
            "Return ONLY a JSON object with these exact keys:\n"
            '  "intent": one of "book", "cancel", "info", "unknown"\n'
            '  "name": the caller\'s name, or null\n'
            '  "service": the requested service, or null\n'
            '  "date_phrase": the caller\'s exact words for the appointment day '
            '(e.g. "tomorrow", "this Friday", "the 25th", "June 26th"), or null\n'
            '  "time": a specific time as 24-hour HH:MM, or null if no exact '
            "time was given (e.g. for vague terms like 'afternoon')\n\n"
            "Conversation so far:\n"
            f"{self._transcript_text()}"
        )
        try:
            resp = self._client.chat(
                model=config.CHAT_MODEL,
                messages=[{"role": "user", "content": prompt}],
                format="json",
                options={"temperature": 0.0, "num_ctx": config.OLLAMA_NUM_CTX},
                keep_alive=config.OLLAMA_KEEP_ALIVE,
            )
            extracted = json.loads(resp["message"]["content"])
        except (json.JSONDecodeError, KeyError):
            return  # keep previous state if extraction fails

        # Merge: a newly found value wins; never overwrite a known value with null.
        if extracted.get("intent") in ("book", "cancel", "info", "unknown"):
            # don't downgrade a real intent back to "unknown"
            if extracted["intent"] != "unknown" or self.state["intent"] == "unknown":
                self.state["intent"] = extracted["intent"]
        for key in ("name", "service", "time"):
            value = extracted.get(key)
            if value:
                self.state[key] = value
        # Resolve the spoken day to a real date in Python (the LLM is unreliable
        # at weekday math). Only update when a new phrase was actually given.
        phrase = extracted.get("date_phrase")
        if phrase:
            resolved = self._resolve_date(phrase)
            if resolved:
                self.state["date"] = resolved

    def _transcript_text(self) -> str:
        who = {"user": "Caller", "assistant": config.BUSINESS["receptionist_name"]}
        return "\n".join(
            f"{who.get(m['role'], m['role'])}: {m['content']}"
            for m in self.transcript
        )

    # --- booking flow (deterministic) ------------------------------------
    def _handle_booking(self) -> str:
        s = self.state
        name_word = f", {s['name']}" if s["name"] else ""

        if not s["name"]:
            return "I can help you book that. May I have your name, please?"
        if not s["service"]:
            return f"Thanks{name_word}. What would you like to come in for?"
        if not s["date"]:
            return "Sure. What day would you like to come in?"

        date_obj = self._parse_date(s["date"])
        if date_obj is None:
            s["date"] = None
            return "Sorry, I didn't catch the day. What date works for you?"
        if date_obj < dt.datetime.now(TZ).date():
            s["date"] = None
            return "That date has already passed. What upcoming day works for you?"
        if date_obj.weekday() not in config.BUSINESS_DAYS:
            s["date"] = None
            return (
                f"We're closed that day. Our hours are {config.BUSINESS['hours']} "
                "What other day suits you?"
            )

        free = self.calendar.free_slots(date_obj)
        if not free:
            s["date"] = None
            return (
                f"I'm sorry, we're fully booked on {date_obj:%A %d %B}. "
                "Would another day work?"
            )

        if not s["time"]:
            return (
                f"For {date_obj:%A %d %B} I have these times available: "
                f"{self._format_slots(free)}. Which would you like?"
            )

        start = self._combine(date_obj, s["time"])
        if start is None:
            s["time"] = None
            return "Sorry, what time would you like?"

        # Already booked this slot in this conversation: the caller is just
        # acknowledging (e.g. "thanks"), not asking to book again. Don't collide
        # with our own booking — respond conversationally instead.
        if start in self._booked_starts:
            self._reset_booking()
            return self._smalltalk()

        try:
            self.calendar.book(s["name"], s["service"], start)
        except SlotUnavailable:
            s["time"] = None
            return (
                f"I'm sorry, {self._fmt_time(start)} is already taken. "
                f"I do have {self._format_slots(free)}. Which works for you?"
            )

        self._booked_starts.add(start)
        booked = f"{start:%A %d %B at %H:%M}"
        confirmed = self.state.copy()
        self._reset_booking()
        return (
            f"You're all set, {confirmed['name']} - {confirmed['service']} on "
            f"{booked}. We'll see you then!"
        )

    # --- cancellation flow (deterministic) -------------------------------
    def _handle_cancel(self) -> str:
        s = self.state
        if not s["name"]:
            return "I can help with that. What name is the appointment under?"

        matches = self.calendar.find_by_name(s["name"])
        if not matches:
            return f"I don't see any appointment under {s['name']}. Could you spell the name for me?"

        if len(matches) == 1 and (s["date"] or len(matches) == 1):
            ev = matches[0]
            when = self._event_when(ev)
            self.calendar.cancel(ev["id"])
            self._reset_booking()
            return f"Done - I've cancelled your appointment{when}. Anything else?"

        # Multiple appointments: if they named a day, match it; else ask.
        if s["date"]:
            for ev in matches:
                start = ev["start"].get("dateTime", "")
                if start.startswith(s["date"]):
                    when = self._event_when(ev)
                    self.calendar.cancel(ev["id"])
                    self._reset_booking()
                    return f"Done - I've cancelled your appointment{when}. Anything else?"
        listed = "; ".join(self._event_when(ev).strip() for ev in matches)
        return f"I see a few appointments for you: {listed}. Which one should I cancel?"

    # --- free-form answers (LLM) -----------------------------------------
    def _answer_question(self) -> str:
        return self._llm_reply(
            "Answer the caller's question briefly and warmly using only the "
            "business facts above. One or two sentences."
        )

    def _smalltalk(self) -> str:
        return self._llm_reply(
            "Reply briefly and warmly. If the caller hasn't said what they need, "
            "gently ask whether they'd like to book, cancel, or ask a question. "
            "One or two sentences."
        )

    def _llm_reply(self, instruction: str) -> str:
        b = config.BUSINESS
        system = (
            f"You are {b['receptionist_name']}, receptionist at {b['name']}. "
            "You are mid-call; never greet again or say you are an AI. "
            f"Hours: {b['hours']} Services: {', '.join(b['services'])}. "
            f"Address: {b['address']}. Phone: {b['phone']}.\n{instruction}"
        )
        messages = [{"role": "system", "content": system}] + self.transcript
        resp = self._client.chat(
            model=config.CHAT_MODEL,
            messages=messages,
            options={"temperature": 0.5, "num_ctx": config.OLLAMA_NUM_CTX},
            keep_alive=config.OLLAMA_KEEP_ALIVE,
        )
        return resp["message"]["content"].strip()

    # --- helpers ----------------------------------------------------------
    def _resolve_date(self, phrase: str) -> str | None:
        """Turn a spoken day ('this Friday', 'tomorrow') into a YYYY-MM-DD string."""
        settings = {
            "TIMEZONE": config.TIMEZONE,
            "RETURN_AS_TIMEZONE_AWARE": True,
            "PREFER_DATES_FROM": "future",
            "RELATIVE_BASE": dt.datetime.now(TZ),
        }
        for candidate in (phrase, _DATE_QUALIFIER.sub("", phrase).strip()):
            if not candidate:
                continue
            parsed = dateparser.parse(
                candidate, settings=settings, languages=["en", "fr"]
            )
            if parsed:
                return parsed.date().isoformat()
        return None

    def _parse_date(self, value: str) -> dt.date | None:
        try:
            return dt.date.fromisoformat(value)
        except (ValueError, TypeError):
            return None

    def _combine(self, date_obj: dt.date, time_str: str) -> dt.datetime | None:
        try:
            hour, minute = (int(x) for x in time_str.split(":"))
            return dt.datetime(date_obj.year, date_obj.month, date_obj.day,
                               hour, minute, tzinfo=TZ)
        except (ValueError, AttributeError):
            return None

    def _format_slots(self, slots: list[dt.datetime]) -> str:
        shown = slots[:_MAX_SLOTS_OFFERED]
        return ", ".join(f"{s:%H:%M}" for s in shown)

    def _fmt_time(self, when: dt.datetime) -> str:
        return f"{when:%H:%M}"

    def _event_when(self, ev: dict) -> str:
        raw = ev["start"].get("dateTime")
        if not raw:
            return ""
        start = dt.datetime.fromisoformat(raw)
        return f" on {start:%A %d %B at %H:%M}"

    def _reset_booking(self) -> None:
        self.state = {"intent": "unknown", "name": self.state.get("name"),
                      "service": None, "date": None, "time": None}
