@echo off
REM ───────────────────────────────────────────────────────────────
REM loadenv.bat — load all KEY=VALUE lines from .env into %ENV%
REM Usage in cmd.exe:
REM    C:\project> CALL loadenv.bat
REM    C:\project> echo %OAUTH2_PROXY_SCOPE%
REM ───────────────────────────────────────────────────────────────

REM Iterate over every non-blank line of .env
for /f "usebackq tokens=* delims=" %%L in (".env_local") do (
    REM skip lines starting with #
    echo %%L | findstr /b "#" >nul
    if errorlevel 1 (
        REM split on first “=” into %%A=key, %%B=value
        for /f "tokens=1* delims==" %%A in ("%%L") do (
            set "%%A=%%B"
        )
    )
)

REM Verify one variable
echo %DAGSTER_CODE_PORT%
