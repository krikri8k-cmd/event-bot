param(
  [string]$Input = "Бали — лучший остров для серферов",
  [string]$Model = "text-embedding-3-small"
)

$ErrorActionPreference = "Stop"
if (-not $env:OPENAI_API_KEY) { Write-Error "OPENAI_API_KEY is not set"; exit 2 }

$headers = @{ Authorization = "Bearer $env:OPENAI_API_KEY" }
$body = @{ model = $Model; input = $Input }

$response = Invoke-RestMethod `
  -Uri "https://api.openai.com/v1/embeddings" `
  -Method Post `
  -Headers $headers `
  -ContentType "application/json" `
  -Body ($body | ConvertTo-Json)

"Embedding length: " + $response.data[0].embedding.Count
