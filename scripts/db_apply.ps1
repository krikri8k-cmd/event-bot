Param(
  [string]$FilePath = "sql/2025_ics_sources_and_indexes.sql",
  [string]$DatabaseUrl = $Env:DATABASE_URL
)
if (-not $DatabaseUrl) {
  Write-Error "DATABASE_URL not set. Pass -DatabaseUrl or export env var."
  exit 2
}
python scripts/apply_sql.py $FilePath $DatabaseUrl
