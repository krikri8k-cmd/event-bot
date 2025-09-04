# Lists available models
$ErrorActionPreference = "Stop"
if (-not $env:OPENAI_API_KEY) { Write-Error "OPENAI_API_KEY is not set"; exit 2 }

$headers = @{ Authorization = "Bearer $env:OPENAI_API_KEY" }
Invoke-RestMethod `
  -Uri "https://api.openai.com/v1/models" `
  -Method Get `
  -Headers $headers `
| ConvertTo-Json -Depth 10
