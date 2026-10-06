$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$taskBundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
if (Test-Path -LiteralPath $taskPython) {
    & $taskPython app.py --demo
} elseif (Test-Path -LiteralPath $taskBundledPython) {
    & $taskBundledPython app.py --demo
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 app.py --demo
} else {
    & python app.py --demo
}
