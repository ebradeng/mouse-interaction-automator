# Mouse Interaction Automator - Windows one-click installer
# All app files and virtual environment are installed under current user's LOCALAPPDATA.
# If a usable Python is unavailable, use Windows Package Manager (winget) to install it.
# Python packages are installed only into the app-specific virtual environment.
$ErrorActionPreference = 'Stop'

function Test-PythonCommand {
    param([string] $Executable, [string[]] $Prefix = @())
    try {
        & $Executable @Prefix -c 'import sys, tkinter; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

function Find-CompatiblePython {
    $launcher = Get-Command 'py.exe' -ErrorAction SilentlyContinue
    if ($null -ne $launcher -and (Test-PythonCommand -Executable $launcher.Source -Prefix @('-3'))) {
        return @{ Executable = $launcher.Source; Prefix = @('-3') }
    }

    # After winget installs Python, the existing PowerShell process may not have the new PATH.
    $lookup = @()
    $lookup += Get-ChildItem -Path (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python3*\python.exe') -ErrorAction SilentlyContinue
    $lookup += Get-ChildItem -Path (Join-Path $env:ProgramFiles 'Python3*\python.exe') -ErrorAction SilentlyContinue
    $lookup += Get-ChildItem -Path (Join-Path $env:SystemDrive 'Python3*\python.exe') -ErrorAction SilentlyContinue
    foreach ($item in ($lookup | Sort-Object FullName -Descending)) {
        if (Test-PythonCommand -Executable $item.FullName) {
            return @{ Executable = $item.FullName; Prefix = @() }
        }
    }

    $python = Get-Command 'python.exe' -ErrorAction SilentlyContinue
    if ($null -ne $python -and (Test-PythonCommand -Executable $python.Source)) {
        return @{ Executable = $python.Source; Prefix = @() }
    }
    return $null
}

try {
    $sourceScript = Join-Path $PSScriptRoot 'mouse_interaction_automator.py'
    $requirements = Join-Path $PSScriptRoot 'requirements.txt'
    $sourceIcon = Join-Path $PSScriptRoot 'app.ico'
    if (!(Test-Path -LiteralPath $sourceScript) -or !(Test-Path -LiteralPath $requirements) -or !(Test-Path -LiteralPath $sourceIcon)) {
        throw 'Missing installer files. Extract the entire ZIP before running Install.cmd.'
    }

    Write-Host ''
    Write-Host 'Mouse Interaction Automator - Setup' -ForegroundColor Cyan
    Write-Host '-----------------------------------'
    $python = Find-CompatiblePython
    if ($null -eq $python) {
        $winget = Get-Command 'winget.exe' -ErrorAction SilentlyContinue
        if ($null -eq $winget) {
            throw 'Python 3.10+ with Tkinter was not found, and winget is unavailable. Install Python 3 from python.org or install Windows App Installer, then rerun Install.cmd.'
        }
        Write-Host 'Python not detected. Installing Python 3.13 through winget...'
        & $winget.Source install --id Python.Python.3.13 --exact --source winget --scope user --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) {
            throw ('winget could not install Python (exit code {0}).' -f $LASTEXITCODE)
        }
        $python = Find-CompatiblePython
        if ($null -eq $python) {
            throw 'Python installation finished, but Python could not be located. Sign out and back in, then rerun Install.cmd.'
        }
    } else {
        Write-Host 'Compatible Python detected.'
    }

    $appDir = Join-Path $env:LOCALAPPDATA 'RandomScrollClick'
    $venvDir = Join-Path $appDir '.venv'
    $venvPython = Join-Path $venvDir 'Scripts\python.exe'
    $venvPythonw = Join-Path $venvDir 'Scripts\pythonw.exe'
    New-Item -ItemType Directory -Path $appDir -Force | Out-Null

    if (!(Test-Path -LiteralPath $venvPython)) {
        Write-Host 'Creating isolated Python environment...'
        $pythonExecutable = $python.Executable
        $pythonPrefix = @($python.Prefix)
        & $pythonExecutable @pythonPrefix -m venv $venvDir
        if ($LASTEXITCODE -ne 0) { throw 'Failed to create the Python virtual environment.' }
    }

    Write-Host 'Installing / checking app dependencies...'
    & $venvPython -m pip install --disable-pip-version-check --no-input -r $requirements
    if ($LASTEXITCODE -ne 0) { throw 'Could not install application dependencies. Check your internet connection.' }

    $installedScript = Join-Path $appDir 'mouse_interaction_automator.py'
    $installedIcon = Join-Path $appDir 'app.ico'
    Copy-Item -LiteralPath $sourceScript -Destination $installedScript -Force
    Copy-Item -LiteralPath $sourceIcon -Destination $installedIcon -Force

    if (!(Test-Path -LiteralPath $venvPythonw)) { throw 'pythonw.exe was not found in the app environment.' }
    $wsh = New-Object -ComObject WScript.Shell
    $desktop = [Environment]::GetFolderPath('DesktopDirectory')
    $programs = [Environment]::GetFolderPath('Programs')
    foreach ($lnk in @((Join-Path $desktop 'MIA.lnk'), (Join-Path $programs 'Mouse Interaction Automator.lnk'))) {
        $shortcut = $wsh.CreateShortcut($lnk)
        $shortcut.TargetPath = $venvPythonw
        $shortcut.Arguments = ('"{0}"' -f $installedScript)
        $shortcut.WorkingDirectory = $appDir
        $shortcut.IconLocation = ('{0},0' -f $installedIcon)
        $shortcut.Description = 'Mouse Interaction Automator desktop automation'
        $shortcut.Save()
    }

    Write-Host ''
    Write-Host 'Installed! Desktop and Start Menu shortcuts created.' -ForegroundColor Green
    Write-Host ('App folder: {0}' -f $appDir)
    Write-Host 'Opening the application...'
    Start-Process -FilePath $venvPythonw -ArgumentList ('"{0}"' -f $installedScript) -WorkingDirectory $appDir
    exit 0
} catch {
    Write-Host ''
    Write-Host ('INSTALLATION FAILED: {0}' -f $_.Exception.Message) -ForegroundColor Red
    exit 1
}
