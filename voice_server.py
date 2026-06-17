"""
Browser voice demo for the AI receptionist (Phase 5).

Serves a web page where you click, speak into your mic, and hear Sara reply.
The full loop is local and free:

    browser mic -> Whisper (STT) -> BookingDialog -> Piper (TTS) -> browser

Run it (venv active):
    python voice_server.py
Then open http://localhost:5000 in Chrome or Edge.
"""

from __future__ import annotations

import base64
import os
import tempfile
import uuid

import ollama
from flask import Flask, jsonify, request, send_from_directory

from app import config
from app.calendar_service import CalendarService
from app.dialog import BookingDialog
from app.speech import SpeechToText, synthesize

app = Flask(__name__, static_folder="static")

# Built once at startup (Whisper load + calendar auth). Single-session demo:
# one browser conversation at a time, which is all a demo needs.
_stt = SpeechToText()
_calendar = CalendarService()
_dialog = BookingDialog(calendar=_calendar)


def _warm_up_model() -> None:
    try:
        ollama.Client(host=config.OLLAMA_HOST).generate(
            model=config.CHAT_MODEL, prompt="hello",
            options={"num_predict": 1}, keep_alive=config.OLLAMA_KEEP_ALIVE,
        )
        print(f"Model {config.CHAT_MODEL} warmed up.")
    except Exception as exc:  # noqa: BLE001
        print(f"Warning: warmup failed ({exc}).")


def _speak(text: str) -> str:
    """Synthesize text to WAV and return it base64-encoded for the browser."""
    out = os.path.join(tempfile.gettempdir(), f"sara_{uuid.uuid4().hex}.wav")
    try:
        synthesize(text, out)
        with open(out, "rb") as fh:
            return base64.b64encode(fh.read()).decode("ascii")
    finally:
        if os.path.exists(out):
            os.remove(out)


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/greeting", methods=["POST"])
def greeting():
    global _dialog
    _dialog = BookingDialog(calendar=_calendar)  # fresh conversation
    text = _dialog.greeting()
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
        reply = _dialog.respond(heard)

    return jsonify(transcript=heard, reply=reply, audio=_speak(reply))


if __name__ == "__main__":
    _warm_up_model()
    app.run(host="0.0.0.0", port=5000)
