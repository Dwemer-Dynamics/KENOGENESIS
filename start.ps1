param(
    [Parameter(Mandatory = $true)][string]$Workspace,
    [string]$Python = 'python',
    [int]$Port = 8766
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $Workspace)) {
    New-Item -ItemType Directory -Path $Workspace | Out-Null
}
Push-Location $PSScriptRoot
try {
    & $Python -m kenogenesis --workspace (Resolve-Path -LiteralPath $Workspace).Path serve --port $Port
    if ($LASTEXITCODE -ne 0) { throw "KENOGENESIS exited with code $LASTEXITCODE" }
}
finally { Pop-Location }
