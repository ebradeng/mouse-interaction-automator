$ErrorActionPreference = 'Stop'
try {
    $desktop = [Environment]::GetFolderPath('DesktopDirectory')
    $programs = [Environment]::GetFolderPath('Programs')
    $appDir = Join-Path $env:LOCALAPPDATA 'RandomScrollClick'
    Write-Host 'Close Mouse Interaction Automator before uninstalling.'
    foreach ($shortcutPath in @((Join-Path $desktop 'MIA.lnk'), (Join-Path $desktop 'Mouse Interaction Automator.lnk'), (Join-Path $programs 'Mouse Interaction Automator.lnk'))) {
        if (Test-Path -LiteralPath $shortcutPath) { Remove-Item -LiteralPath $shortcutPath -Force }
    }
    if (Test-Path -LiteralPath $appDir) { Remove-Item -LiteralPath $appDir -Recurse -Force }
    Write-Host 'Mouse Interaction Automator has been removed. Existing Python installations were left unchanged.' -ForegroundColor Green
} catch {
    Write-Host ('Uninstall failed: {0}' -f $_.Exception.Message) -ForegroundColor Red
    exit 1
}
