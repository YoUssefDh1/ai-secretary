"""
Central configuration for the AI receptionist.

Everything a small business would customize lives here so the rest of the
code stays generic. Edit the BUSINESS dict to match a real business.
"""

# --- Model settings -------------------------------------------------------
# The conversational "brain". mistral:latest is the best balance of quality
# and speed among the locally-installed models. phi:2.7b is faster but weaker.
CHAT_MODEL = "gemma2:9b"

# A small, fast model used only to tag the caller's intent (optional, used by
# the --show-intent flag). Kept separate so normal chat stays fast.
INTENT_MODEL = "phi:2.7b"

# Where the local Ollama server lives.
OLLAMA_HOST = "http://localhost:11434"

# How long Ollama keeps the model loaded in VRAM after a request. Keeping it
# warm avoids the ~20s cold-start reload, which matters for webhook timeouts.
OLLAMA_KEEP_ALIVE = "30m"

# Context window for the LLM. gemma2's default (8192) inflates VRAM use and, on
# an 8 GB card, pushes layers onto the CPU (which makes replies take many
# seconds). A receptionist conversation is short, so a smaller window keeps the
# whole model on the GPU and replies fast.
OLLAMA_NUM_CTX = 4096

# Timezone the business operates in (used heavily by the calendar).
TIMEZONE = "Africa/Tunis"


# --- Google Calendar settings --------------------------------------------
# "primary" = the main calendar of whichever Google account you authorize.
# You can later point this at a dedicated calendar's ID instead.
GOOGLE_CALENDAR_ID = "primary"

# OAuth files (kept in the project root, ignored by git).
#   credentials.json -> the OAuth client you download from Google Cloud.
#   token.json       -> created automatically after your first login.
GOOGLE_CREDENTIALS_FILE = "credentials.json"
GOOGLE_TOKEN_FILE = "token.json"


# --- Voice settings -------------------------------------------------------
# Speech-to-text (local Whisper via faster-whisper).
WHISPER_MODEL = "small"          # base/small/medium - small fits with gemma in 8GB
WHISPER_LANGUAGE = "en"          # set None to auto-detect (less reliable on short clips)
# Device for Whisper: "cpu", "cuda", or "auto".
# IMPORTANT: on an 8 GB GPU, running Whisper on "cuda" steals VRAM from gemma2,
# forcing the LLM onto the CPU and making replies take minutes. Keep Whisper on
# the CPU (~3s, fine) and leave the GPU entirely to the LLM.
WHISPER_DEVICE = "cpu"

# Text-to-speech (local Piper). Paths are relative to the project root.
PIPER_EXE = "tools/piper/piper.exe"
PIPER_VOICE = "tools/voices/en_US-lessac-medium.onnx"


# --- Scheduling rules -----------------------------------------------------
# Working days: Monday=0 ... Sunday=6. Here: Monday-Friday.
BUSINESS_DAYS = [0, 1, 2, 3, 4]
# Opening and closing time (24h, in TIMEZONE).
OPEN_TIME = "09:00"
CLOSE_TIME = "18:00"
# Default length of an appointment, and the granularity of offered slots.
DEFAULT_APPT_MINUTES = 30
SLOT_GRANULARITY_MINUTES = 30


# --- Business profile -----------------------------------------------------
# This is the only part you should normally need to edit per-business.
BUSINESS = {
    "name": "Bright Smile Dental Clinic",
    "kind": "dental clinic",
    "receptionist_name": "Sara",
    "hours": "Monday to Friday, 9:00 AM to 6:00 PM. Closed weekends.",
    "services": [
        "general check-up",
        "teeth cleaning",
        "tooth extraction",
        "teeth whitening",
    ],
    "address": "12 Avenue Habib Bourguiba, Tunis",
    "phone": "+216 71 000 000",
}
