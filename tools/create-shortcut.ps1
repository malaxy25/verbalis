# Creates shortcuts for Verbalis on the desktop and in the Start menu.
# Run once inside the repo:  .\tools\create-shortcut.ps1
# The shortcut points to the .venv in the repo – updates take effect immediately.

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$exe  = Join-Path $repo ".venv\Scripts\verbalis-app.exe"
$icon = Join-Path $repo "src\verbalis\ui\verbalis.ico"

if (-not (Test-Path $exe)) {
    Write-Host "Not found: $exe" -ForegroundColor Red
    Write-Host 'Activate the .venv in the repo and run  pip install -e ".[dev]"  first.'
    exit 1
}

$shell = New-Object -ComObject WScript.Shell
$folders = @(
    [Environment]::GetFolderPath("Desktop"),
    [Environment]::GetFolderPath("Programs")   # Start menu
)
foreach ($folder in $folders) {
    # Remove the shortcut of the old name (Mitschrift, up to version 0.6)
    $old = Join-Path $folder "Mitschrift.lnk"
    if (Test-Path $old) {
        Remove-Item $old
        Write-Host "Removed old shortcut: $old"
    }
    $path = Join-Path $folder "Verbalis.lnk"
    $lnk = $shell.CreateShortcut($path)
    $lnk.TargetPath       = $exe
    $lnk.WorkingDirectory = $repo
    $lnk.IconLocation     = "$icon,0"
    $lnk.Description      = "Record and transcribe conversations"
    $lnk.Save()
    Write-Host "Shortcut created: $path"
}
Write-Host ""
Write-Host "Done. Verbalis now opens by double-click or from the Start menu."
Write-Host "Tip: right-click it in the Start menu to pin it to the taskbar."
