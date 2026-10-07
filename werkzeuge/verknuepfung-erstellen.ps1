# Legt Verknüpfungen für Mitschrift auf dem Desktop und im Startmenü an.
# Einmalig ausführen, im Repo:  .\werkzeuge\verknuepfung-erstellen.ps1
# Die Verknüpfung zeigt auf die .venv im Repo – Updates wirken also sofort.

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$exe  = Join-Path $repo ".venv\Scripts\mitschrift-app.exe"
$icon = Join-Path $repo "src\mitschrift\ui\mitschrift.ico"

if (-not (Test-Path $exe)) {
    Write-Host "Nicht gefunden: $exe" -ForegroundColor Red
    Write-Host 'Zuerst im Repo die .venv aktivieren und  pip install -e ".[dev]"  ausführen.'
    exit 1
}

$shell = New-Object -ComObject WScript.Shell
$ordner = @(
    [Environment]::GetFolderPath("Desktop"),
    [Environment]::GetFolderPath("Programs")   # Startmenü
)
foreach ($ziel in $ordner) {
    $pfad = Join-Path $ziel "Mitschrift.lnk"
    $lnk = $shell.CreateShortcut($pfad)
    $lnk.TargetPath       = $exe
    $lnk.WorkingDirectory = $repo
    $lnk.IconLocation     = "$icon,0"
    $lnk.Description      = "Gespräche aufnehmen und transkribieren"
    $lnk.Save()
    Write-Host "Verknüpfung erstellt: $pfad"
}
Write-Host ""
Write-Host "Fertig. Mitschrift lässt sich jetzt per Doppelklick oder über das Startmenü öffnen."
Write-Host "Tipp: Im Startmenü per Rechtsklick an die Taskleiste anheften."
