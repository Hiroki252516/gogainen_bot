$ErrorActionPreference = "Stop"

$rootDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$envFile = Join-Path $rootDir ".env"
$listenUrl = "ws://127.0.0.1:4500"

if (Test-Path $envFile) {
    foreach ($line in Get-Content -LiteralPath $envFile) {
        if ($line -match '^\s*CODEX_APP_SERVER_LISTEN_URL\s*=\s*(.*?)\s*$') {
            $listenUrl = $matches[1].Trim().Trim('"').Trim("'")
        }
    }
}

& codex app-server --listen $listenUrl
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
