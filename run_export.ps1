param(
    [Parameter(Mandatory=$true)]
    [string]$Scene,

    [string]$Root = 'C:/Users/theod/Documents/uio/_masteroppgave/data/stroma/ExampleTiles',
    [string]$SlicerExe = 'C:/Users/theod/AppData/Local/slicer.org/3D Slicer 5.10.0/Slicer.exe',
    [string]$Tag = '_edited',
    [string]$HeFolder = 'HE',
    [string]$Ext = '.png'
)

$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$scriptPath = Join-Path $scriptDir 'export_segmentations.py'

if (-not (Test-Path $SlicerExe)) {
    throw "Slicer.exe not found at: $SlicerExe"
}

if (-not (Test-Path $scriptPath)) {
    throw "Export script not found at: $scriptPath"
}

if (-not (Test-Path $Scene)) {
    throw "Scene file not found at: $Scene"
}

if (-not (Test-Path $Root)) {
    throw "Root folder not found at: $Root"
}

$slicerArgs = @(
    '--no-main-window',
    '--python-script', $scriptPath,
    '--',
    '--scene', $Scene,
    '--root', $Root,
    '--tag', $Tag,
    '--he-folder', $HeFolder,
    '--ext', $Ext
)

Write-Host "Exporting segmentations from: $Scene"
Write-Host "Back to:                      $Root"
Write-Host "Filename tag:                 $Tag"
Write-Host ""

& $SlicerExe @slicerArgs
