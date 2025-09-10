param(
  [Parameter(Mandatory=$true)][string]$File,
  [string]$Model = "whisper-1"
)

$ErrorActionPreference = "Stop"
if (-not $env:OPENAI_API_KEY) { Write-Error "OPENAI_API_KEY is not set"; exit 2 }
if (-not (Test-Path $File))   { Write-Error "File not found: $File"; exit 3 }

$headers = @{ Authorization = "Bearer $env:OPENAI_API_KEY" }

Invoke-RestMethod `
  -Uri "https://api.openai.com/v1/audio/transcriptions" `
  -Method Post `
  -Headers $headers `
  -Form @{ model=$Model; file = Get-Item $File }
