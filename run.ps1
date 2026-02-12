$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$scriptPath = Join-Path $scriptDir 'automated_loading.py'
$slicerExe = 'C:/Users/theod/AppData/Local/slicer.org/3D Slicer 5.10.0/Slicer.exe'

if (-not (Test-Path $slicerExe)) {
    throw "Slicer.exe not found at: $slicerExe"
}

if (-not (Test-Path $scriptPath)) {
    throw "Script not found at: $scriptPath"
}

& $slicerExe --python-script $scriptPath
