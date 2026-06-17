# Start the AI receptionist for self-hosting: the unified server + a public
# tunnel for the WhatsApp webhook. Run from the project root:  .\start.ps1

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
$cloudflared = Join-Path $root "cloudflared.exe"

Write-Host "Starting AI receptionist..." -ForegroundColor Cyan

# 1. Make sure Ollama is up (it normally runs as a background service).
try { ollama ps | Out-Null } catch {
    Write-Host "  Ollama doesn't seem to be running. Start it first." -ForegroundColor Yellow
}

# 2. Launch the unified server in its own window (loads Whisper + warms gemma).
Write-Host "  Launching server (new window)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "& '$python' '$root\server.py'"

# 3. Start the public tunnel in THIS window so you can see and copy the URL.
Write-Host ""
Write-Host "Starting public tunnel. Copy the https://...trycloudflare.com URL below" -ForegroundColor Green
Write-Host "and set it (plus /whatsapp) as your Twilio sandbox webhook." -ForegroundColor Green
Write-Host "Note: this URL changes each time you restart the tunnel." -ForegroundColor DarkGray
Write-Host ""
& $cloudflared tunnel --url http://localhost:5000
