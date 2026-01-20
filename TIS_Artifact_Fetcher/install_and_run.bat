@echo off
setlocal EnableDelayedExpansion

:: Configuration
set CONDA_ENV_NAME=tis_version_extractor
set REQUIRED_PYTHON_VERSION=3.9
set SCRIPT_DIR=%~dp0
set SRC_DIR=%SCRIPT_DIR%src

echo === TIS Version Extractor Setup ===
echo.

:: Check if conda is available
where conda >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Error: Conda is not installed or not in PATH!
    echo Please install Anaconda or Miniconda first.
    pause
    exit /b 1
)

:: Check if src directory exists
if not exist "%SRC_DIR%" (
    echo Error: src directory not found!
    echo Please ensure the src directory exists with all required Python files.
    pause
    exit /b 1
)

:: Check if requirements.txt exists
if not exist "%SRC_DIR%\requirements.txt" (
    echo Error: requirements.txt not found in src directory!
    echo Please ensure requirements.txt is in the src directory.
    pause
    exit /b 1
)

:: Check if environment exists
conda env list | find "%CONDA_ENV_NAME%" >nul
if %ERRORLEVEL% neq 0 (
    echo Creating new conda environment '%CONDA_ENV_NAME%'...
    call conda create -n %CONDA_ENV_NAME% python=%REQUIRED_PYTHON_VERSION% -y
    
    if !ERRORLEVEL! neq 0 (
        echo Error: Failed to create conda environment!
        pause
        exit /b 1
    )
)

:: Activate environment
echo.
echo Activating conda environment...
call conda activate %CONDA_ENV_NAME%
if !ERRORLEVEL! neq 0 (
    echo Error: Failed to activate conda environment!
    pause
    exit /b 1
)

:: Install required packages from requirements.txt
echo.
echo Installing required packages...
pip install -r "%SRC_DIR%\requirements.txt"
if !ERRORLEVEL! neq 0 (
    echo Error: Failed to install required packages!
    pause
    exit /b 1
)

:: Find first Excel file in current directory
set "EXCEL_FILE="
for %%F in (*.xlsx) do (
    set "EXCEL_FILE=%%F"
    goto :found_excel
)
:found_excel

if not defined EXCEL_FILE (
    echo.
    echo Error: No Excel file found!
    echo Please place an Excel file in this directory.
    pause
    exit /b 1
)

echo.
echo Found Excel file: %EXCEL_FILE%
echo.

:: Set PYTHONPATH to include the src directory
set "PYTHONPATH=%SRC_DIR%;%PYTHONPATH%"
echo Python path set to: %PYTHONPATH%

:: Run script
echo Running main script...
python "%SRC_DIR%\run_workflow.py" "%EXCEL_FILE%"
if %ERRORLEVEL% neq 0 (
    echo.
    echo Error: Script execution failed!
    pause
    exit /b 1
)

echo.
echo Execution completed successfully!
echo Press any key to exit...
pause >nul