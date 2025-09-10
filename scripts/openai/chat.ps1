param(
  [string]$Prompt = "Привет! Скажи одну шутку.",
  [string]$Model  = "gpt-4o-mini"
)

$ErrorActionPreference = "Stop"
if (-not $env:OPENAI_API_KEY) { Write-Error "OPENAI_API_KEY is not set"; exit 2 }

$headers = @{ Authorization = "Bearer $env:OPENAI_API_KEY" }
$body = @{
  model    = $Model
  messages = @(@{ role = "user"; content = $Prompt })
}

$response = Invoke-RestMethod `
  -Uri "https://api.openai.com/v1/chat/completions" `
  -Method Post `
  -Headers $headers `
  -ContentType "application/json" `
  -Body ($body | ConvertTo-Json -Depth 5)

$response.choices[0].message.content
