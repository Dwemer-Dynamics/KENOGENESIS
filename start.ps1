# Start the KENOGENESIS loopback browser from this source folder. Installs nothing and changes no settings.
# A private workspace folder is required; it is created if it does not exist yet.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateNotNullOrEmpty()][string]$Workspace,
    # Optional explicit interpreter: a python.exe path, or a command name such as python3.
    [string]$Python,
    [ValidateRange(1, 65535)][int]$Port = 8766,
    [switch]$OpenBrowser
)

$ErrorActionPreference = 'Stop'

function Stop-Launcher([string]$Message, [int]$Code) {
    Write-Host "KENOGENESIS: $Message" -ForegroundColor Red
    exit $Code
}

# Each candidate is an executable plus fixed leading arguments (py needs -3). Arguments are passed as an array,
# so paths with spaces, apostrophes or $ are never re-parsed by the shell.
function Get-Candidate([string]$Name, [string[]]$Prefix) {
    if (Test-Path -LiteralPath $Name -PathType Leaf) {
        return @{ Exe = (Resolve-Path -LiteralPath $Name).Path; Prefix = $Prefix; Label = $Name }
    }
    $command = Get-Command -Name $Name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($command) { return @{ Exe = $command.Source; Prefix = $Prefix; Label = $Name } }
    return $null
}

# Returns the interpreter's version text when it is Python 3.11 or newer, otherwise $null.
function Test-Candidate($Candidate) {
    $prefix = @($Candidate.Prefix)
    try {
        # No double quotes in the probe: Windows PowerShell 5.1 does not escape them for native programs.
        $version = & $Candidate.Exe @prefix -c 'import sys; print(''.''.join(map(str, sys.version_info[:3]))); sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>$null
        if ($LASTEXITCODE -eq 0) { return "$version".Trim() }
    } catch { }
    return $null
}

if ($Python) {
    $candidate = Get-Candidate $Python @()
    if (-not $candidate) { Stop-Launcher "The interpreter given with -Python was not found: $Python" 2 }
    $version = Test-Candidate $candidate
    if (-not $version) { Stop-Launcher "The interpreter given with -Python is not Python 3.11 or newer, or did not run: $($candidate.Exe)" 2 }
    $chosen = $candidate
} else {
    $candidates = @(
        (Get-Candidate (Join-Path $PSScriptRoot '.venv\Scripts\python.exe') @()),
        (Get-Candidate 'py' @('-3')),
        (Get-Candidate 'python' @())
    ) | Where-Object { $_ }
    $chosen = $null
    foreach ($candidate in $candidates) {
        $version = Test-Candidate $candidate
        if ($version) { $chosen = $candidate; break }
    }
    if (-not $chosen) {
        Stop-Launcher 'Python 3.11 or newer was not found (.venv\Scripts\python.exe, py -3 or python). Install it, or pass -Python <path to python.exe>.' 2
    }
}

try {
    if (-not (Test-Path -LiteralPath $Workspace)) {
        New-Item -ItemType Directory -Path $Workspace | Out-Null
    } elseif (-not (Test-Path -LiteralPath $Workspace -PathType Container)) {
        Stop-Launcher "The workspace exists but is not a folder: $Workspace" 2
    }
    $workspacePath = (Resolve-Path -LiteralPath $Workspace).Path
} catch {
    Stop-Launcher "The workspace folder could not be created or read: $Workspace ($($_.Exception.Message))" 2
}

$serveArgs = @('-m', 'kenogenesis', '--workspace', $workspacePath, 'serve', '--port', "$Port")
if ($OpenBrowser) { $serveArgs += '--open-browser' }
$prefix = @($chosen.Prefix)
Write-Host "Python:    $($chosen.Exe) $($prefix -join ' ') ($version)"
Write-Host "Workspace: $workspacePath"
Write-Host 'Keep this window open. Press Ctrl+C to stop KENOGENESIS.'
Push-Location -LiteralPath $PSScriptRoot
try {
    & $chosen.Exe @prefix @serveArgs
    $resultCode = $LASTEXITCODE
} finally { Pop-Location }
if ($resultCode -ne 0) { Write-Host "KENOGENESIS exited with code $resultCode." -ForegroundColor Red }
exit $resultCode
