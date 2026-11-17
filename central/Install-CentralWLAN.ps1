<#
  Sintratec Central über WLAN mit dem Kit Control verbinden.

  Installieren:   Rechtsklick > "Mit PowerShell ausführen"
                  oder:  powershell -ExecutionPolicy Bypass -File Install-CentralWLAN.ps1
  Feste Adresse:  ... -File Install-CentralWLAN.ps1 -IP 192.168.1.48
  Rückgängig:     ... -File Install-CentralWLAN.ps1 -Uninstall

  Ersetzt in Central nur die USB-Bibliothek usb4java-1.2.0.jar. Das Original wird gesichert.
#>
param(
  [string]$IP = "",
  [switch]$Uninstall
)
$ErrorActionPreference = "Stop"

$lib = Join-Path $env:LOCALAPPDATA "Sintratec\Central64\app\lib"
if (-not (Test-Path $lib)) {
  $alt = Get-ChildItem -Path "$env:LOCALAPPDATA","$env:ProgramFiles","${env:ProgramFiles(x86)}" -Recurse -Filter "usb4java-1.2.0.jar" -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($alt) { $lib = $alt.DirectoryName } else { throw "Sintratec Central wurde nicht gefunden." }
}
$target = Join-Path $lib "usb4java-1.2.0.jar"
$backup = Join-Path $lib "usb4java-1.2.0.jar.original"
$ours   = Join-Path $PSScriptRoot "usb4java-1.2.0.jar"
$cfg    = Join-Path $env:USERPROFILE "kit-control.txt"

if (Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Path -and $_.Path -like "*Sintratec*" }) {
  throw "Bitte Sintratec Central zuerst schließen."
}

if ($Uninstall) {
  if (Test-Path $backup) { Copy-Item $backup $target -Force; Remove-Item $backup }
  if (Test-Path $cfg) { Remove-Item $cfg }
  Write-Host "Original wiederhergestellt. Central nutzt wieder USB." -ForegroundColor Green
  exit 0
}

if (-not (Test-Path $ours)) { throw "usb4java-1.2.0.jar muss neben diesem Skript liegen." }
if (-not (Test-Path $backup)) { Copy-Item $target $backup }
Copy-Item $ours $target -Force

if ($IP) {
  "host=$IP" | Set-Content -Path $cfg -Encoding ASCII
  Write-Host "Feste Adresse: $IP"
} elseif (Test-Path $cfg) {
  Remove-Item $cfg
}

Write-Host ""
Write-Host "Fertig. Central sucht den Kit jetzt im WLAN." -ForegroundColor Green
Write-Host "Den Kit am Pi per USB anschließen, Central starten und wie gewohnt verbinden."
Write-Host "Findet Central nichts: Skript mit -IP <IP des Pi> erneut ausführen (IP steht am Display unter System)."
