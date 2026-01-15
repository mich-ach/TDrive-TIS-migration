# TIS Version Extractor Tool

This tool extracts LCO and VeMoX versions from TIS for software lines listed in a master Excel file. It matches software lines from your Excel file with TIS data and generates a comprehensive report showing version information and artifacts.

## Setup and Usage

1. **Prerequisites**
   - Anaconda or Miniconda must be installed
   - Network access to TIS (Bosch network or VPN)
   - Windows operating system

2. **Installation**
   - Extract all files maintaining the following structure:
     ```
  your_directory/
  ├── install_and_run.bat
  ├── Series_Maintenance_Project_List.xlsx
  └── src/
      ├── requirements.txt
      ├── run_workflow.py
      ├── config.py
      ├── tis_artifact_extractor.py
      ├── excel_handler.py
      └── version_parser.py
     ```
   - Place your master Excel file in the root directory (same level as install_and_run.bat)
   - The Excel file name must contain "Series_Maintenance_Project_List"

3. **Running the Tool**
   - Double-click `install_and_run.bat`
   - The script will automatically:
     1. Create a conda environment 'tis_version_extractor' if needed
     2. Install all required packages from src/requirements.txt
     3. Locate your Excel file in the root directory
     4. Extract version information from TIS - This might take a while so be patient and grab a coffee/matcha
     5. Generate and open a detailed report

4. **Output**
   - An Excel report will be generated in the output directory showing:
     - Original master data from your Excel file (white columns)
     - TIS software line status (blue column)
     - Latest artifact information (green when found, red when not found)
   - The report includes:
     - Software line matching status
     - LCO versions
     - VeMoX versions
     - Labcar types
     - Direct TIS links
   - The report will automatically open when complete

5. **Color Coding in Report**
   - White columns: Original data from your Excel file
   - Blue column: TIS software line status
   - Green rows: Found artifacts in TIS
   - Red rows: No artifacts found
   - Grey rows: Software line not found in TIS

6. **Troubleshooting**
   - If the script fails to run:
     - Ensure Anaconda/Miniconda is installed and in your PATH
     - Verify you're connected to the Bosch network or VPN
     - Check that your Excel file is in the root directory
     - Confirm the Excel file name contains "Series_Maintenance_Project_List"
     - Look for error messages in the command window
   - If the report is empty:
     - Verify your Excel file contains the correct column headers
     - Check TIS connectivity
     - Ensure the software lines in your Excel exist in TIS

## Directory Structure


project_root/
├── install_and_run.bat # Installation and execution script
├── Series_Maintenance_Project_List.xlsx # Your input Excel file
│
└── src/
├── requirements.txt # Python package requirements
├── run_workflow.py # Main workflow script
├── config.py # Configuration settings
├── tis_artifact_extractor.py # TIS data extraction
├── excel_handler.py # Excel processing
└── version_parser.py # Version parsing utilities