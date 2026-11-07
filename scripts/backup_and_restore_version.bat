@echo off
setlocal
set "GTAV=D:\steam\steamapps\common\Grand Theft Auto V"
for %%I in ("%~dp0..") do set "PROJECT_ROOT=%%~fI"
set "BACKUP=%PROJECT_ROOT%\version_backup"

echo GTA V Legacy version file utility
echo Game: %GTAV%
echo Backup: %BACKUP%
echo.
echo [1] Back up current version files
echo [2] Restore files from version_backup
echo [Q] Quit
choice /C 12Q /N /M "Select an option: "
if errorlevel 3 goto :eof
if errorlevel 2 goto restore
if errorlevel 1 goto backup

:backup
set "FAILED=0"
if not exist "%GTAV%\GTA5.exe" (
  echo ERROR: GTA5.exe was not found in the game folder.
  pause
  exit /b 1
)
if not exist "%GTAV%\update\" (
  echo ERROR: update folder was not found.
  pause
  exit /b 1
)
mkdir "%BACKUP%\update" 2>nul
for %%F in (GTA5.exe PlayGTAV.exe) do call :copy_one "%GTAV%\%%F" "%BACKUP%\%%F"
for %%F in (update.rpf update2.rpf) do call :copy_one "%GTAV%\update\%%F" "%BACKUP%\update\%%F"
if not "%FAILED%"=="0" (
  echo Backup finished with errors. Review the messages above.
  pause
  exit /b 1
)
echo Backup complete.
pause
exit /b 0

:restore
echo.
echo This will overwrite the matching files in the GTA V folder.
choice /C YN /N /M "Continue with restore? [Y/N] "
if errorlevel 2 exit /b 0
set "FAILED=0"
for %%F in (GTA5.exe PlayGTAV.exe) do call :restore_one "%BACKUP%\%%F" "%GTAV%\%%F"
if not exist "%GTAV%\update\" mkdir "%GTAV%\update"
for %%F in (update.rpf update2.rpf) do call :restore_one "%BACKUP%\update\%%F" "%GTAV%\update\%%F"
if not "%FAILED%"=="0" (
  echo Restore finished with errors. Review the messages above.
  pause
  exit /b 1
)
echo Restore complete.
pause
exit /b 0

:copy_one
if not exist "%~1" (
  echo ERROR: Missing source file: %~1
  set "FAILED=1"
  exit /b 0
)
copy /Y "%~1" "%~2" >nul
if errorlevel 1 (
  echo ERROR: Could not copy %~1
  set "FAILED=1"
) else echo Backed up: %~1
exit /b 0

:restore_one
if not exist "%~1" (
  echo ERROR: Missing backup file: %~1
  set "FAILED=1"
  exit /b 0
)
copy /Y "%~1" "%~2" >nul
if errorlevel 1 (
  echo ERROR: Could not restore %~2
  set "FAILED=1"
) else echo Restored: %~2
exit /b 0
