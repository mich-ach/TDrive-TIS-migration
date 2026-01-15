from pathlib import Path
import datetime
from typing import Tuple, Optional
import shutil
import config

class DirectoryHandler:
    @staticmethod
    def initialize_directories(excel_path: Path) -> Tuple[Path, Path, Path]:
        """
        Initialize output directories and copy Excel file.
        """
        try:
            # Validate input Excel file
            if not excel_path.exists():
                raise ValueError(f"Excel file not found: {excel_path}")

            # Ensure output directory exists
            config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

            # Create timestamped run directory
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            run_dir = config.OUTPUT_DIR / f"run_{timestamp}"
            run_dir.mkdir(parents=True, exist_ok=True)

            # Copy Excel file to run directory
            excel_copy_path = run_dir / excel_path.name
            shutil.copy2(excel_path, excel_copy_path)

            # Update global config - this is crucial
            config.CURRENT_RUN_DIR = run_dir
            
            # Debug print to verify the update
            print(f"DEBUG: Set config.CURRENT_RUN_DIR to: {config.CURRENT_RUN_DIR}")

            return config.OUTPUT_DIR, run_dir, excel_copy_path

        except Exception as e:
            config.CURRENT_RUN_DIR = None  # Reset on failure
            raise ValueError(f"Failed to initialize directories: {str(e)}")

    @staticmethod
    def get_output_file_path(prefix: str, extension: str) -> Path:
        """
        Generate timestamped output file path.
        
        Args:
            prefix: Prefix for the output file
            extension: File extension (without dot)
            
        Returns:
            Path object for the output file
            
        Raises:
            ValueError: If run directory is not initialized
        """
        # Always check the current state from config module
        if not config.CURRENT_RUN_DIR or not config.CURRENT_RUN_DIR.exists():
            raise ValueError(f"Run directory not initialized or doesn't exist! Current value: {config.CURRENT_RUN_DIR}")
            
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        output_path = config.CURRENT_RUN_DIR / f"{prefix}_{timestamp}.{extension}"
        
        # Debug print
        print(f"DEBUG: Generated output path: {output_path}")
        
        return output_path

    @staticmethod
    def validate_project_structure() -> bool:
        """
        Validate that all required directories exist or can be created.
        
        Returns:
            bool: True if structure is valid, False otherwise
        """
        try:
            # Check if source directory exists
            if not config.SCRIPT_DIR.exists():
                print(f"Error: Source directory not found at {config.SCRIPT_DIR}")
                return False

            # Create output directory if it doesn't exist
            config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

            # Verify write permissions
            test_file = config.OUTPUT_DIR / ".test_write"
            try:
                test_file.touch()
                test_file.unlink()
            except Exception as e:
                print(f"Error: No write permission in output directory: {e}")
                return False

            return True

        except Exception as e:
            print(f"Error validating project structure: {e}")
            return False

    @staticmethod
    def cleanup_old_runs(max_runs: int = 999) -> None:
        """
        Clean up old run directories, keeping only the most recent ones.
        
        Args:
            max_runs: Maximum number of run directories to keep
        """
        try:
            if not config.OUTPUT_DIR.exists():
                return

            # Get all run directories sorted by creation time
            run_dirs = sorted(
                [d for d in config.OUTPUT_DIR.glob("run_*") if d.is_dir()],
                key=lambda x: x.stat().st_mtime,
                reverse=True
            )

            # Remove excess directories
            for old_dir in run_dirs[max_runs:]:
                try:
                    shutil.rmtree(old_dir)
                    print(f"Cleaned up old run directory: {old_dir}")
                except Exception as e:
                    print(f"Warning: Failed to remove old directory {old_dir}: {e}")

        except Exception as e:
            print(f"Warning: Failed to clean up old runs: {e}")

    @staticmethod
    def reset_run_directory() -> None:
        """Reset the current run directory in case of errors."""
        config.CURRENT_RUN_DIR = None
        
    @staticmethod
    def get_current_run_dir() -> Optional[Path]:
        """Get the current run directory safely."""
        return config.CURRENT_RUN_DIR
    
    @staticmethod
    def ensure_run_directory_set() -> bool:
        """Ensure run directory is properly set and exists."""
        return (config.CURRENT_RUN_DIR is not None and 
                isinstance(config.CURRENT_RUN_DIR, Path) and 
                config.CURRENT_RUN_DIR.exists())