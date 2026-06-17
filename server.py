"""
Unified server for self-hosting the AI receptionist (Phase 6).

Runs every channel in one process on one port, so a single tunnel exposes
everything:

    GET  /            -> voice demo web page
    POST /greeting    -> voice: start a call (Sara's opening line + audio)
    POST /voice       -> voice: a spoken turn (audio in -> audio out)
    POST /whatsapp    -> Twilio WhatsApp webhook
    GET  /health      -> status check

For isolated development you can still run whatsapp_server.py or voice_server.py
on their own; this file is the one to run for always-on hosting.

Run (venv active):  python server.py
"""

from __future__ import annotations

import base64
import os
import tempfile
import uuid

import ollama
from flask import Flask, jsonify, request, send_from_directory
from twilio.twiml.messaging_response import MessagingResponse

from app import config
from app.calendar_service import CalendarService
from app.dialog import BookingDialog
from app.speech import SpeechToText, synthesize

app = Flask(__name__, static_folder="static")

# Shared singletons (built once at startup).
_calendar = CalendarService()
_stt = SpeechToText()

# Voice uses one browser conversation; WhatsApp keeps one per sender number.
_voice_dialog = BookingDialog(calendar=_calendar)
_wa_sessions: dict[str, BookingDialog] = {}
_RESET_WORDS = {"reset", "restart", "/reset", "start over"}


def _warm_up_model() -> None:
    try:
        ollama.Client(host=config.OLLAMA_HOST).generate(
            model=config.CHAT_MODEL, prompt="hello",
            options={"num_predict": 1, "num_ctx": config.OLLAMA_NUM_CTX},
            keep_alive=config.OLLAMA_KEEP_ALIVE,
        )
        print(f"Model {config.CHAT_MODEL} warmed up.")
    except Exception as exc:  # noqa: BLE001
        print(f"Warning: warmup failed ({exc}).")


def _speak(text: str) -> str:
    out = os.path.join(tempfile.gettempdir(), f"sara_{uuid.uuid4().hex}.wav")
    try:
        synthesize(text, out)
        with open(out, "rb") as fh:
            return base64.b64encode(fh.read()).decode("ascii")
    finally:
        if os.path.exists(out):
            os.remove(out)


# --- health ---------------------------------------------------------------
@app.route("/health")
def health():
    return jsonify(
        status="ok",
        model=config.CHAT_MODEL,
        whisper_device=_stt.device,
        whatsapp_sessions=len(_wa_sessions),
    )


# --- voice channel --------------------------------------------------------
@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/greeting", methods=["POST"])
def greeting():
    global _voice_dialog
    _voice_dialog = BookingDialog(calendar=_calendar)
    text = _voice_dialog.greeting()
    return jsonify(reply=text, audio=_speak(text))


@app.route("/voice", methods=["POST"])
def voice():
    audio = request.files.get("audio")
    if audio is None:
        return jsonify(error="no audio"), 400
    tmp = os.path.join(tempfile.gettempdir(), f"in_{uuid.uuid4().hex}.webm")
    audio.save(tmp)
    try:
        heard = _stt.transcribe(tmp)
    finally:
        os.remove(tmp)
    if not heard:
        reply = "I'm sorry, I didn't catch that. Could you say it again?"
    else:
        reply = _voice_dialog.respond(heard)
    return jsonify(transcript=heard, reply=reply, audio=_speak(reply))


# --- WhatsApp channel -----------------------------------------------------
@app.route("/whatsapp", methods=["POST"])
def whatsapp():
    sender = request.form.get("From", "")
    body = (request.form.get("Body") or "").strip()
    response = MessagingResponse()
    if not body:
        response.message("Sorry, I can only read text messages right now.")
        return str(response)
    if body.lower() in _RESET_WORDS:
        _wa_sessions.pop(sender, None)
    is_new = sender not in _wa_sessions
    if is_new:
        _wa_sessions[sender] = BookingDialog(calendar=_calendar)
    dialog = _wa_sessions[sender]
    if is_new:
        reply = f"{dialog.greeting()}\n\n{dialog.respond(body)}"
    else:
        reply = dialog.respond(body)
    response.message(reply)
    return str(response)


if __name__ == "__main__":
    _warm_up_model()
    print("AI receptionist (all channels) on http://localhost:5000")
    app.run(host="0.0.0.0", port=5000)
