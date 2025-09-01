param(
  [string]$Req = "requirements.txt"
)

Write-Host ">>> Install prebuilt lxml..." -ForegroundColor Cyan
pip install "lxml>=5.2.1" --only-binary=:all:

Write-Host ">>> Temporary force binary wheels for lxml" -ForegroundColor Cyan
$env:PIP_ONLY_BINARY = "lxml"

Write-Host ">>> Install project requirements..." -ForegroundColor Cyan
pip install -r $Req

Write-Host ">>> Unset PIP_ONLY_BINARY" -ForegroundColor Cyan
Remove-Item Env:\PIP_ONLY_BINARY -ErrorAction SilentlyContinue

Write-Host ">>> Done." -ForegroundColor Green
