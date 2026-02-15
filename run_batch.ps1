param(
    [string]$Root = 'C:/Users/theod/Documents/uio/_masteroppgave/data/stroma/ExampleTiles',
    [string]$SlicerExe = 'C:/Users/theod/AppData/Local/slicer.org/3D Slicer 5.10.0/Slicer.exe',
    [string]$OutputScene,
    [int]$MaxTilesPerCase,
    [string]$HeFolder = 'HE',
    [string]$Ext = '.png',
    [switch]$NoSave
)

$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$scriptPath = Join-Path $scriptDir 'automated_loading_batch.py'

if (-not (Test-Path $SlicerExe)) {
    throw "Slicer.exe not found at: $SlicerExe"
}

if (-not (Test-Path $scriptPath)) {
    throw "Script not found at: $scriptPath"
}

if (-not (Test-Path $Root)) {
    throw "Root folder not found at: $Root"
}

$args = @(
    '--python-script', $scriptPath,
    '--',
    '--root', $Root,
    '--he-folder', $HeFolder,
    '--ext', $Ext
)

if ($PSBoundParameters.ContainsKey('OutputScene') -and $OutputScene) {
    $args += @('--output-scene', $OutputScene)
}

if ($PSBoundParameters.ContainsKey('MaxTilesPerCase')) {
    $args += @('--max-tiles-per-case', [string]$MaxTilesPerCase)
}

if ($NoSave.IsPresent) {
    $args += '--no-save'
}

& $SlicerExe @args
