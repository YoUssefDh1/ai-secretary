# Downloads the local binaries this project needs but does not commit:
# the Piper TTS engine + voice, and the cloudflared tunnel. Run once after
# cloning:  .\fetch-tools.ps1

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
New-Item -ItemType Directory -Force -Path "$root\tools\voices" | Out-Null

Write-Host "Downloading cloudflared (tunnel)..." -ForegroundColor Cyan
Invoke-WebRequest "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" `
    -OutFile "$root\cloudflared.exe"

Write-Host "Downloading Piper (TTS engine)..." -ForegroundColor Cyan
$piperZip = "$root\tools\piper_windows_amd64.zip"
Invoke-WebRequest "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_windows_amd64.zip" `
    -OutFile $piperZip
Expand-Archive -Force $piperZip "$root\tools"
Remove-Item $piperZip

Write-Host "Downloading Piper voice (en_US-lessac-medium)..." -ForegroundColor Cyan
$base = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium"
Invoke-WebRequest "$base/en_US-lessac-medium.onnx" -OutFile "$root\tools\voices\en_US-lessac-medium.onnx"
Invoke-WebRequest "$base/en_US-lessac-medium.onnx.json" -OutFile "$root\tools\voices\en_US-lessac-medium.onnx.json"

Write-Host "Done. Tools are in .\tools and .\cloudflared.exe" -ForegroundColor Green
