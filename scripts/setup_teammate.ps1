[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$DownloadDirectory,
    [string]$GamePath,
    [string]$LegacySaveUrl,
    [string]$ProfileId
)

$ErrorActionPreference = 'Stop'

function Find-GtaVPath {
    $candidates = [System.Collections.Generic.List[string]]::new()
    $steam = Get-ItemPropertyValue -Path 'HKCU:\Software\Valve\Steam' -Name SteamPath -ErrorAction SilentlyContinue
    if ($steam) {
        $candidates.Add((Join-Path $steam 'steamapps\common\Grand Theft Auto V'))
        $libraryFile = Join-Path $steam 'steamapps\libraryfolders.vdf'
        if (Test-Path -LiteralPath $libraryFile) {
            foreach ($line in Get-Content -LiteralPath $libraryFile) {
                if ($line -match '"path"\s+"([^"]+)"') {
                    $library = $Matches[1] -replace '\\\\', '\'
                    $candidates.Add((Join-Path $library 'steamapps\common\Grand Theft Auto V'))
                }
            }
        }
    }
    $candidates.Add('C:\Program Files (x86)\Steam\steamapps\common\Grand Theft Auto V')
    $candidates.Add('C:\Program Files\Steam\steamapps\common\Grand Theft Auto V')
    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if (Test-Path -LiteralPath (Join-Path $candidate 'GTA5.exe')) { return $candidate }
    }
    throw 'Could not find a Steam GTA V installation. Pass -GamePath explicitly.'
}

function Expand-ArchiveToTemp([string]$Archive) {
    $destination = Join-Path $env:TEMP ('gtav-ai-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $destination | Out-Null
    Expand-Archive -LiteralPath $Archive -DestinationPath $destination -Force
    return $destination
}

function Copy-RequiredFile([string]$Root, [string]$Name, [string]$Destination) {
    $file = Get-ChildItem -LiteralPath $Root -Filter $Name -File -Recurse | Select-Object -First 1
    if (-not $file) { throw "Required file '$Name' was not found in $Root" }
    Copy-Item -LiteralPath $file.FullName -Destination $Destination -Force
}

if (-not (Test-Path -LiteralPath $DownloadDirectory -PathType Container)) {
    throw "Download directory does not exist: $DownloadDirectory"
}
if (-not $GamePath) { $GamePath = Find-GtaVPath }
if (-not (Test-Path -LiteralPath (Join-Path $GamePath 'GTA5.exe'))) { throw "GTA5.exe was not found in $GamePath" }
$GamePath = (Resolve-Path -LiteralPath $GamePath).Path
$downloadRoot = (Resolve-Path -LiteralPath $DownloadDirectory).Path

$shvZip = Get-ChildItem -LiteralPath $downloadRoot -File -Filter '*ScriptHookV*.zip' | Select-Object -First 1
$rampageZip = Get-ChildItem -LiteralPath $downloadRoot -File -Filter '*Rampage*.zip' | Select-Object -First 1
if (-not $shvZip) { throw 'Place the official ScriptHookV ZIP in DownloadDirectory first.' }
if (-not $rampageZip) { throw 'Place the Rampage Legacy ZIP in DownloadDirectory first.' }

$shvRoot = Expand-ArchiveToTemp $shvZip.FullName
$rampageRoot = Expand-ArchiveToTemp $rampageZip.FullName
Copy-RequiredFile $shvRoot 'ScriptHookV.dll' $GamePath
Copy-RequiredFile $shvRoot 'dinput8.dll' $GamePath
$rampageAsi = Get-ChildItem -LiteralPath $rampageRoot -Filter 'Rampage.asi' -File -Recurse | Select-Object -First 1
if (-not $rampageAsi) { throw 'Rampage.asi was not found in the supplied archive.' }
Copy-Item -LiteralPath $rampageAsi.FullName -Destination $GamePath -Force
$rampageFiles = Get-ChildItem -LiteralPath $rampageRoot -Directory -Recurse | Where-Object Name -eq 'RampageFiles' | Select-Object -First 1
if ($rampageFiles) { Copy-Item -LiteralPath $rampageFiles.FullName -Destination $GamePath -Recurse -Force }

$release = Invoke-RestMethod -Uri 'https://api.github.com/repos/crosire/scripthookvdotnet/releases/tags/nightly' -Headers @{ 'User-Agent' = 'gtav-ai-copilot-setup' }
$asset = $release.assets | Where-Object { $_.name -match '\.zip$' } | Select-Object -First 1
if (-not $asset) { throw 'The SHVDN nightly release did not expose a ZIP asset.' }
$shvdnZip = Join-Path $env:TEMP ('shvdn-' + [guid]::NewGuid().ToString('N') + '.zip')
Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $shvdnZip
$shvdnRoot = Expand-ArchiveToTemp $shvdnZip
foreach ($name in @('ScriptHookVDotNet.asi', 'ScriptHookVDotNet.asi.config', 'ScriptHookVDotNet.dll', 'ScriptHookVDotNet2.dll', 'ScriptHookVDotNet3.dll')) {
    $file = Get-ChildItem -LiteralPath $shvdnRoot -Filter $name -File -Recurse | Select-Object -First 1
    if ($file) { Copy-Item -LiteralPath $file.FullName -Destination $GamePath -Force }
}
$loader = Get-ChildItem -LiteralPath $shvdnRoot -Filter 'ScriptHookVDotNet-Loader.asi' -File -Recurse | Select-Object -First 1
if ($loader) { Copy-Item -LiteralPath $loader.FullName -Destination $GamePath -Force }

$repoRoot = Split-Path -Parent $PSScriptRoot
$scriptsDir = Join-Path $GamePath 'scripts'
New-Item -ItemType Directory -Path $scriptsDir -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $repoRoot 'gtav-telemetry-mod\GTAVTelemetryServer.cs') -Destination $scriptsDir -Force

$profilesRoot = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'Rockstar Games\GTA V\Profiles'
if (-not (Test-Path -LiteralPath $profilesRoot)) { throw "Rockstar profile directory was not found: $profilesRoot" }
if (-not $ProfileId) {
    $profiles = Get-ChildItem -LiteralPath $profilesRoot -Directory
    if ($profiles.Count -eq 1) { $ProfileId = $profiles[0].Name }
    else { throw "Pass -ProfileId using one of these profile folder names: $($profiles.Name -join ', ')" }
}
$profilePath = Join-Path $profilesRoot $ProfileId
if (-not (Test-Path -LiteralPath $profilePath)) { throw "Profile folder does not exist: $profilePath" }
$saveFile = Get-ChildItem -LiteralPath $downloadRoot -File | Where-Object Name -match '^SGTA50000' | Select-Object -First 1
if ($saveFile) {
    $savePath = $saveFile.FullName
} elseif ($LegacySaveUrl) {
    $savePath = Join-Path $env:TEMP ('SGTA50000-' + [guid]::NewGuid().ToString('N'))
    Invoke-WebRequest -Uri $LegacySaveUrl -OutFile $savePath
} else {
    throw 'Place a legally obtained 100% Legacy SGTA50000 save in DownloadDirectory or pass -LegacySaveUrl.'
}
Copy-Item -LiteralPath $savePath -Destination $profilePath -Force

Remove-Item -LiteralPath $shvRoot, $rampageRoot, $shvdnRoot -Recurse -Force
Remove-Item -LiteralPath $shvdnZip -Force
Write-Host "Installed ScriptHookV, Rampage, SHVDN nightly and telemetry script to $GamePath"
Write-Host "Copied the selected Legacy save to $profilePath"
