param(
  [string]$Text  = "Привет! Это тест синтеза речи.",
  [string]$Out   = "speech.mp3",
  [string]$Voice = "alloy",
  [string]$Model = "tts-1"
)

$ErrorActionPreference = "Stop"
if (-not $env:OPENAI_API_KEY) { Write-Error "OPENAI_API_KEY is not set"; exit 2 }

$headers = @{ Authorization = "Bearer $env:OPENAI_API_KEY" }
$body = @{
  model  = $Model
  voice  = $Voice
  input  = $Text
  format = "mp3"
}

Invoke-RestMethod `
  -Uri "https://api.openai.com/v1/audio/speech" `
  -Method Post `
  -Headers $headers `
  -ContentType "application/json" `
  -Body ($body | ConvertTo-Json) `
  -OutFile $Out

Write-Host "Saved $Out"
