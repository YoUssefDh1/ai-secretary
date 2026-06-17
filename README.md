# AI Secretary / Virtual Receptionist

An AI receptionist for a small business: answers calls and texts, talks
naturally, understands what the caller wants (book / cancel / info), and manages
a real calendar. Built in phases.

Timezone: **Africa/Tunis**.

## Status

- [x] **Phase 1 — The brain (text only).** Multi-turn receptionist conversation
      in the terminal, powered by a local model via Ollama. Free, fully local.
- [x] **Phase 2 — Calendar.** Real Google Calendar: availability, booking,
      cancel, double-booking prevention, Africa/Tunis timezone.
- [x] **Phase 3 — Conversational booking.** Sara books, cancels, and answers
      questions during a live conversation, driving the real calendar. The LLM
      handles language; plain code guarantees correct times.
- [x] **Phase 4 — WhatsApp.** Sara receives and replies to WhatsApp messages
      via the Twilio sandbox; each sender gets their own conversation.
- [x] **Phase 5 — Voice (browser).** Talk to Sara in the browser: Whisper STT +
      Piper TTS, fully local and free. She books on the real calendar by voice.
- [x] **Phase 6 — Self-hosting.** All channels run together via `server.py`,
      started (with a public tunnel) by `start.ps1`. Runs 24/7 on your own PC, $0.

## Requirements

- [Ollama](https://ollama.com) running locally with the `gemma2:9b` model
  pulled (`ollama pull gemma2:9b`). Fits fully in 8 GB VRAM; ~2-3s per reply
  after a one-time cold start.
- Python 3.12.

> **Note on Python:** on this machine the `python` command points at Inkscape's
> bundled Python (no pip). Use the **`py`** launcher instead, which points at
> the real `C:\Python312`.

## Setup (one time)

This project uses an isolated virtual environment so its dependencies never
clash with other Python tools on the machine.

```powershell
py -m venv .venv                       # create the venv (uses real Python 3.12)
.\.venv\Scripts\Activate.ps1           # activate it (do this each new terminal)
pip install -r requirements.txt
```

Once activated, your prompt shows `(.venv)` and you use `python` normally.
If you prefer not to activate, prefix commands with `.\.venv\Scripts\python`.

## Run (Phase 1 — conversation)

```powershell
python cli.py                 # chat with the receptionist
python cli.py --show-intent   # also print the detected intent each turn
```

While chatting: `/reset` starts over, `/quit` exits.

## Run (Phase 2 — calendar)

First complete the Google Calendar setup below, then:

```powershell
python calendar_cli.py auth                       # first-time login
python calendar_cli.py slots 2026-06-18           # free slots that day
python calendar_cli.py book "Youssef" "cleaning" 2026-06-18 14:00
python calendar_cli.py list                       # upcoming appointments
python calendar_cli.py find "Youssef"             # find someone's bookings
python calendar_cli.py cancel <event_id>          # cancel by id
```

## Google Calendar setup (one time, ~15 min)

1. Go to <https://console.cloud.google.com> and create a project
   (e.g. "AI Receptionist").
2. **APIs & Services -> Library** -> search "Google Calendar API" -> **Enable**.
3. **APIs & Services -> OAuth consent screen**: choose **External**, fill in an
   app name and your email. Under **Test users**, add your own Google address.
4. **APIs & Services -> Credentials -> Create Credentials -> OAuth client ID** ->
   application type **Desktop app** -> Create.
5. **Download** the JSON, rename it to `credentials.json`, and place it in the
   project root (next to this README).
6. Run `python calendar_cli.py auth` — a browser opens, log in, approve. A
   `token.json` is saved so you stay logged in.

> `credentials.json` and `token.json` are secrets and are git-ignored.

## Run (Phase 4 — WhatsApp)

```powershell
python whatsapp_server.py     # starts the webhook server on port 5000
```

Then text the Twilio sandbox number from WhatsApp and Sara replies.

## WhatsApp (Twilio sandbox) setup (one time, ~10 min)

1. Create a free account at <https://www.twilio.com/try-twilio>.
2. In the Twilio Console: **Messaging -> Try it out -> Send a WhatsApp message**.
   This opens the **WhatsApp sandbox**.
3. From WhatsApp on your phone, send the shown **`join <two-words>`** message to
   the sandbox number. You should get a confirmation that you've joined.
4. Expose your local server to the internet with a tunnel. Either:
   - **ngrok** (needs a free account + authtoken): `ngrok http 5000`
   - **cloudflared** (no account): `cloudflared tunnel --url http://localhost:5000`

   Copy the public `https://...` URL it prints.
5. Back in the sandbox settings, set **"When a message comes in"** to:
   ```
   https://<your-public-url>/whatsapp
   ```
   Method **POST**. Save.
6. Start the server (`python whatsapp_server.py`), then text the sandbox number
   from WhatsApp. Sara greets you and can book / cancel / answer questions.

> Notes: the sandbox session expires after ~72 hours of inactivity (just re-send
> the `join` code). Conversations are kept in memory, so restarting the server
> resets them. Text "reset" to start a conversation over.

## Run (Phase 5 — voice in the browser)

```powershell
python voice_server.py
```

Open <http://localhost:5000> in **Chrome or Edge**, click **Start call**, then
tap to speak. The whole loop is local and free:
`mic -> Whisper (STT) -> gemma2 -> Piper (TTS) -> speaker`.

Voice assets live under `tools/` (the Piper binary + voice, git-ignored). The
Whisper model downloads automatically on first run. Settings (model size,
language, voice) are in [app/config.py](app/config.py). Whisper uses the GPU if
available and falls back to CPU automatically.

**A note on GPU vs CPU for Whisper (important on 8 GB cards):** Whisper *can*
run on the GPU (~0.2s vs ~3s per utterance) by installing the CUDA libraries:

```powershell
pip install nvidia-cublas-cu12 nvidia-cudnn-cu12   # then set WHISPER_DEVICE="cuda"/"auto"
```

But on an 8 GB GPU this is a **net loss**: Whisper steals VRAM from gemma2,
forcing the LLM partly onto the CPU and making replies take *minutes*. The LLM
is the latency bottleneck, not STT, so the GPU is far better spent entirely on
gemma. `WHISPER_DEVICE` defaults to `"cpu"` for this reason. Only use GPU
Whisper if the LLM runs elsewhere or you have a larger card.

**Tuning LLM speed:** `OLLAMA_NUM_CTX` (in config) caps the context window so
gemma fits in VRAM. If `ollama ps` shows a CPU/GPU split (offloading), close
other GPU apps or lower this value.

## Self-hosting (Phase 6 — run everything 24/7)

`server.py` runs all channels (WhatsApp + voice) in one process on port 5000, so
a single tunnel exposes everything. `start.ps1` launches it together with the
public tunnel:

```powershell
.\start.ps1
```

This opens the server in its own window and starts the tunnel in the current
one. Copy the printed `https://...trycloudflare.com` URL and set your Twilio
WhatsApp webhook to `<that-url>/whatsapp`. Open the same base URL (or
`http://localhost:5000`) for the voice demo. Check `/health` for status.

Notes:
- The PC must stay on, and Ollama must be running (it normally auto-starts).
- The quick-tunnel URL changes each restart — re-paste it into Twilio when it
  does. (A stable URL needs a Cloudflare-managed domain, a small yearly cost.)
- **Security:** while the tunnel is up, `/whatsapp` and `/voice` are publicly
  reachable by anyone with the URL. For always-on use, add Twilio request-
  signature validation so only Twilio can drive the webhook.
- **Auto-start on boot (optional):** create a Windows Task Scheduler task that
  runs `start.ps1` at logon.

## Customizing the business

Everything a business would change (name, hours, services, receptionist name,
address) lives in [app/config.py](app/config.py). The model used is also set
there (`CHAT_MODEL`).

## Project layout

```
app/
  config.py            # business profile + model/calendar/voice settings
  brain.py             # plain conversational receptionist (raw chat)
  calendar_service.py  # Google Calendar: availability, book, cancel
  dialog.py            # booking dialogue manager (LLM + calendar + dates)
  speech.py            # Whisper STT + Piper TTS (local)
cli.py                 # terminal interface (booking by default, --raw for chat)
calendar_cli.py        # direct calendar test commands
whatsapp_server.py     # WhatsApp only (dev/testing)
voice_server.py        # voice only (dev/testing)
server.py              # ALL channels together (self-hosting entry point)
start.ps1              # launch server + public tunnel
static/index.html      # voice demo web page
tools/                 # Piper binary + voices, cloudflared (git-ignored)
```
