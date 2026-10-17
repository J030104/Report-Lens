[CmdletBinding()]
param([string]$Package, [string]$Config)
$ErrorActionPreference = 'Stop'
$reportLensPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $reportLensPython)) {
    throw 'Install first: python -m venv .venv, then .venv\Scripts\python.exe -m pip install -e .'
}
Push-Location -LiteralPath $PSScriptRoot
try {
    if ($Package) {
        & $reportLensPython -m reportlens gui $Package
    } elseif ($Config) {
        & $reportLensPython -m reportlens gui --config $Config
    } elseif (Test-Path -LiteralPath 'local.reportlens.json') {
        & $reportLensPython -m reportlens gui --config local.reportlens.json
    } else {
        & $reportLensPython -m reportlens gui examples/public-demo/garden-review.reportlens
    }
} finally { Pop-Location }
