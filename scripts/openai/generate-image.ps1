param(
  [string]$Prompt = "A neon futuristic beach bar at sunset, isometric, vibrant",
  [string]$Out    = "image.png",
  [string]$Size   = "1024x1024",
  [string]$Model  = "gpt-image-1"
)

$ErrorActionPreference = "Stop"
if (-not $env:OPENAI_API_KEY) { Write-Error "OPENAI_API_KEY is not set"; exit 2 }

$headers = @{ Authorization = "Bearer $env:OPENAI_API_KEY" }
$body = @{
  model            = $Model
  prompt           = $Prompt
  size             = $Size
  response_format  = "b64_json"
}

$response = Invoke-RestMethod `
  -Uri "https://api.openai.com/v1/images/generations" `
  -Method Post `
  -Headers $headers `
  -ContentType "application/json" `
  -Body ($body | ConvertTo-Json)

$b64 = $response.data[0].b64_json
[IO.File]::WriteAllBytes($Out, [Convert]::FromBase64String($b64))
Write-Host "Saved $Out"
