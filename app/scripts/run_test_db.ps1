<#!
.SYNOPSIS
Run the backend test suite against the dedicated Neon test branch.

.DESCRIPTION
Fetches a direct, branch-specific connection string at runtime. No password is
stored in this script or the repository. The pytest fixtures intentionally
drop and recreate the public schema, so this must only target platter-test.
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$branch = "platter-test"
$database = "platter_test"
$appDir = Split-Path -Parent $PSScriptRoot
$python = Join-Path $appDir ".venv\\Scripts\\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Missing $python. Install dependencies first."
}

$connectionString = (
    & npx.cmd -y neonctl@latest connection-string $branch --database-name $database
).Trim()

if ($LASTEXITCODE -ne 0 -or -not $connectionString.StartsWith("postgres")) {
    throw "Could not retrieve a direct connection string for $branch/$database. Run 'neon auth' and confirm the workspace is linked."
}

$env:TEST_DATABASE_URL = $connectionString
Push-Location $appDir
try {
    & $python -m pytest -q
    exit $LASTEXITCODE
}
finally {
    Pop-Location
    Remove-Item Env:TEST_DATABASE_URL -ErrorAction SilentlyContinue
}
