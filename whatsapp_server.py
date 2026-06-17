"""
WhatsApp webhook server for the AI receptionist (Phase 4).

Twilio receives WhatsApp messages in its sandbox and POSTs them to this server.
Each incoming message is routed to that sender's own conversation (a
BookingDialog), and Sara's reply is returned as TwiML for Twilio to deliver.

Run it (with the venv active):
    python whatsapp_server.py

Then expose it to the internet with ngrok and point the Twilio sandbox at it.
See the README "WhatsApp (Twilio sandbox) setup" section.
"""

from __future__ import annotations

import ollama
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse

from app import config
from app.calendar_service import CalendarService
from app.dialog import BookingDialog

app = Flask(__name__)

# One shared calendar connection for every conversation.
_calendar = CalendarService()

# Per-sender conversations, keyed by WhatsApp number (e.g. "whatsapp:+216...").
_sessions: dict[str, BookingDialog] = {}

# Words a caller can text to start over.
_RESET_WORDS = {"reset", "restart", "/reset", "start over"}


def _warm_up_model() -> None:
    """Load gemma into VRAM at startup so the first real message is fast."""
    try:
        ollama.Client(host=config.OLLAMA_HOST).generate(
            model=config.CHAT_MODEL,
            prompt="hello",
            options={"num_predict": 1},
            keep_alive=config.OLLAMA_KEEP_ALIVE,
        )
        print(f"Model {config.CHAT_MODEL} warmed up and kept alive.")
    except Exception as exc:  # noqa: BLE001 - warmup is best-effort
        print(f"Warning: could not warm up model ({exc}).")


@app.route("/", methods=["GET"])
def health() -> str:
    return "AI receptionist WhatsApp server is running."


@app.route("/whatsapp", methods=["POST"])
def whatsapp() -> str:
    sender = request.form.get("From", "")
    body = (request.form.get("Body") or "").strip()

    response = MessagingResponse()

    if not body:
        response.message("Sorry, I can only read text messages right now.")
        return str(response)

    if body.lower() in _RESET_WORDS:
        _sessions.pop(sender, None)

    is_new = sender not in _sessions
    if is_new:
        _sessions[sender] = BookingDialog(calendar=_calendar)

    dialog = _sessions[sender]

    if is_new:
        # Open with the branded greeting, then answer their first message.
        reply = f"{dialog.greeting()}\n\n{dialog.respond(body)}"
    else:
        reply = dialog.respond(body)

    response.message(reply)
    return str(response)


if __name__ == "__main__":
    _warm_up_model()
    # Port 5000 is what we'll point ngrok at.
    app.run(host="0.0.0.0", port=5000)
