"""Path and naming validation for TIS artifacts.

This module provides classes and functions to validate artifact paths against
expected conventions and naming patterns defined in config.json.

Classes:
    PathValidator: Validates artifact paths and names against conventions

The validation is config-driven:
- path_convention: Component-specific path structures with variable values
- naming_convention.patterns: Regex patterns for artifact name validation
"""

import logging
import re
from typing import Tuple, List, Dict, Optional

from Models import DeviationType

from config import (
    PATH_CONVENTION_ENABLED,
    PATH_CONVENTIONS,
    NAMING_CONVENTION_ENABLED,
    NAMING_CONVENTION_PATTERNS,
)

logger = logging.getLogger(__name__)

# Get CSP/SWB patterns from path convention (fallback to defaults)
CSP_SWB_SUBFOLDERS = PATH_CONVENTIONS.get("vVeh_LCO", {}).get("CSP_SWB_contains", ["CSP", "SWB"])
CSP_SWB_PATTERN = re.compile(r"(" + "|".join(CSP_SWB_SUBFOLDERS) + ")", re.IGNORECASE)


class PathValidator:
    """
    Validates artifact paths against expected conventions.

    Configuration is loaded from config.json path_convention section.
    Each component_name has its own expected_structure and variable values.
    """

    def __init__(self):
        """Initialize the path validator with compiled naming patterns."""
        self._compiled_patterns = self._compile_naming_patterns()

    def _compile_naming_patterns(self) -> Dict:
        """Compile naming convention patterns from config."""
        compiled = {}
        if NAMING_CONVENTION_ENABLED and NAMING_CONVENTION_PATTERNS:
            for pattern_name, pattern_config in NAMING_CONVENTION_PATTERNS.items():
                try:
                    compiled[pattern_name] = {
                        'regex': re.compile(pattern_config['pattern']),
                        'description': pattern_config.get('description', ''),
                        'example': pattern_config.get('example', '')
                    }
                except re.error as e:
                    logger.warning(f"Invalid regex for pattern '{pattern_name}': {e}")
        return compiled

    def validate_path(
        self,
        path: str,
        artifact_name: str = None,
        component_name: str = None
    ) -> Tuple[DeviationType, str, str]:
        """
        Validate artifact path against expected convention.

        Args:
            path: The artifact's path (e.g., "Project/SWLine/Model/HiL/CSP/...")
            artifact_name: The artifact's name (for naming validation)
            component_name: The component type name (for component-specific validation)

        Returns:
            Tuple of (DeviationType, details, expected_path_hint)
        """
        if not PATH_CONVENTION_ENABLED:
            return (DeviationType.VALID, "", "")

        path_parts = path.split('/') if path else []

        if len(path_parts) < 2:
            return (
                DeviationType.WRONG_LOCATION,
                "Path too short",
                "[Project]/[SWLine]/..."
            )

        project = path_parts[0]
        sw_line = path_parts[1] if len(path_parts) > 1 else "Unknown"

        # Get component-specific path convention
        convention = self._get_path_convention(component_name)
        expected_structure = convention.get("expected_structure", "") if convention else ""

        # Validate based on expected structure
        if expected_structure:
            return self._validate_against_structure(
                path_parts, project, sw_line, expected_structure, convention, component_name
            )

        # Fallback: generic Model/HiL|SiL validation for unknown components
        if 'Model' not in path_parts:
            return (
                DeviationType.MISSING_MODEL,
                "Artifact not under 'Model' folder",
                f"{project}/{sw_line}/Model/..."
            )

        model_index = path_parts.index('Model')
        remaining = path_parts[model_index + 1:]

        is_hil_path = 'HiL' in remaining
        is_sil_path = 'SiL' in remaining

        if not is_hil_path and not is_sil_path:
            if remaining and any(sf in remaining[0] for sf in CSP_SWB_SUBFOLDERS):
                return (
                    DeviationType.CSP_SWB_UNDER_MODEL,
                    f"{remaining[0]} directly under Model (missing HiL)",
                    f"{project}/{sw_line}/Model/HiL/{remaining[0]}/..."
                )
            return (
                DeviationType.MISSING_HIL,
                "Missing 'HiL' or 'SiL' folder after Model",
                f"{project}/{sw_line}/Model/HiL|SiL/[subfolder]/..."
            )

        if is_hil_path:
            result = self._validate_hil_path(
                remaining, project, sw_line, expected_structure, []
            )
            if result[0] != DeviationType.VALID:
                return result

        if is_sil_path:
            result = self._validate_sil_path(
                remaining, project, sw_line, expected_structure, []
            )
            if result[0] != DeviationType.VALID:
                return result

        return (DeviationType.VALID, "", "")

    def _validate_against_structure(
        self,
        path_parts: List[str],
        project: str,
        sw_line: str,
        expected_structure: str,
        convention: Dict,
        component_name: str
    ) -> Tuple[DeviationType, str, str]:
        """Validate path against expected structure with variable substitution."""
        # Parse expected structure to get required folders
        # Format: {Project}/{SoftwareLine}/Model/SiL/vVeh/{CSP_SWB}/{LabcarType}/.../{artifact}
        # or: {Project}/{SoftwareLine}/Test/{TestType}/.../{artifact}

        structure_parts = expected_structure.split('/')
        # Skip {Project}, {SoftwareLine}, ..., {artifact} placeholders
        required_folders = []
        variables_in_path = {}

        for i, part in enumerate(structure_parts):
            if part.startswith('{') and part.endswith('}'):
                var_name = part[1:-1]
                if var_name not in ('Project', 'SoftwareLine', 'artifact', '...'):
                    # This is a variable like {TestType} or {CSP_SWB}
                    variables_in_path[i] = var_name
            elif part != '...':
                required_folders.append(part)

        # Check required folders exist in path
        for folder in required_folders:
            if folder not in path_parts:
                return (
                    DeviationType.WRONG_LOCATION,
                    f"Missing required folder '{folder}' in path",
                    expected_structure
                )

        # Validate variables have allowed values
        for var_name in variables_in_path.values():
            # Check for _contains suffix (partial matching)
            contains_key = f"{var_name}_contains"
            if contains_key in convention:
                allowed_values = convention[contains_key]
                actual_value = self._find_variable_value_in_path(
                    path_parts, required_folders, var_name, structure_parts
                )
                if actual_value:
                    # Check if actual_value contains any of the allowed values
                    matches = any(av.lower() in actual_value.lower() for av in allowed_values)
                    if not matches:
                        return (
                            DeviationType.INVALID_SUBFOLDER,
                            f"Invalid {var_name} '{actual_value}' (must contain: {' or '.join(allowed_values)})",
                            expected_structure
                        )
            else:
                # Exact match
                allowed_values = convention.get(var_name, [])
                if allowed_values:
                    actual_value = self._find_variable_value_in_path(
                        path_parts, required_folders, var_name, structure_parts
                    )
                    if actual_value and actual_value not in allowed_values:
                        return (
                            DeviationType.INVALID_SUBFOLDER,
                            f"Invalid {var_name} '{actual_value}' (allowed: {', '.join(allowed_values)})",
                            expected_structure
                        )

        return (DeviationType.VALID, "", "")

    def _find_variable_value_in_path(
        self,
        path_parts: List[str],
        required_folders: List[str],
        var_name: str,
        structure_parts: List[str]
    ) -> Optional[str]:
        """Find the actual value of a variable in the path based on structure position."""
        # Find position of variable in structure (after last required folder before it)
        for i, part in enumerate(structure_parts):
            if part == f'{{{var_name}}}':
                # Find the folder before this variable in structure and count intermediate variables
                prev_folder = None
                steps_after_anchor = 1  # Start at 1 (next item after anchor)
                for j in range(i - 1, -1, -1):
                    struct_part = structure_parts[j]
                    if not struct_part.startswith('{') and struct_part != '...':
                        prev_folder = struct_part
                        break
                    elif struct_part.startswith('{') and struct_part.endswith('}'):
                        # Count intermediate variables to skip
                        steps_after_anchor += 1

                if prev_folder and prev_folder in path_parts:
                    prev_index = path_parts.index(prev_folder)
                    target_index = prev_index + steps_after_anchor
                    if target_index < len(path_parts):
                        return path_parts[target_index]
        return None

    def _validate_hil_path(
        self,
        remaining: List[str],
        project: str,
        sw_line: str,
        expected_structure: str,
        expected_subfolders: List[str]
    ) -> Tuple[DeviationType, str, str]:
        """Validate HiL path structure."""
        hil_index = remaining.index('HiL')
        after_hil = remaining[hil_index + 1:]

        if not after_hil:
            return (
                DeviationType.MISSING_CSP_SWB,
                "Missing subfolder after HiL",
                expected_structure or f"{project}/{sw_line}/Model/HiL/[CSP|SWB]/..."
            )

        first_after_hil = after_hil[0]
        check_subfolders = expected_subfolders if expected_subfolders else CSP_SWB_SUBFOLDERS
        is_valid_subfolder = any(
            sf.lower() in first_after_hil.lower()
            for sf in check_subfolders
        )
        if not is_valid_subfolder:
            return (
                DeviationType.INVALID_SUBFOLDER,
                f"Invalid subfolder '{first_after_hil}' after HiL",
                expected_structure or f"{project}/{sw_line}/Model/HiL/[{'/'.join(check_subfolders)}]/..."
            )

        return (DeviationType.VALID, "", "")

    def _validate_sil_path(
        self,
        remaining: List[str],
        project: str,
        sw_line: str,
        expected_structure: str,
        expected_subfolders: List[str]
    ) -> Tuple[DeviationType, str, str]:
        """Validate SiL path structure."""
        sil_index = remaining.index('SiL')
        after_sil = remaining[sil_index + 1:]

        if not after_sil:
            return (
                DeviationType.MISSING_SIL,
                "Missing subfolder after SiL",
                expected_structure or f"{project}/{sw_line}/Model/SiL/[subfolder]/..."
            )

        if expected_subfolders:
            first_after_sil = after_sil[0]
            is_valid_subfolder = any(
                sf.lower() in first_after_sil.lower()
                for sf in expected_subfolders
            )
            if not is_valid_subfolder:
                return (
                    DeviationType.INVALID_SUBFOLDER,
                    f"Invalid subfolder '{first_after_sil}' after SiL (expected: {', '.join(expected_subfolders)})",
                    expected_structure or f"{project}/{sw_line}/Model/SiL/[{'/'.join(expected_subfolders)}]/..."
                )

        return (DeviationType.VALID, "", "")

    def _get_path_convention(self, component_name: str) -> Optional[Dict]:
        """Get path convention config for a component_name."""
        if not component_name:
            return None

        # Direct match
        if component_name in PATH_CONVENTIONS:
            return PATH_CONVENTIONS[component_name]

        # Prefix match
        for pattern, config in PATH_CONVENTIONS.items():
            if component_name.startswith(pattern):
                return config

        return None

    def _get_allowed_values(self, component_name: str, variable_name: str) -> List[str]:
        """Get allowed values for a variable in the path convention."""
        convention = self._get_path_convention(component_name)
        if not convention:
            return []
        return convention.get(variable_name, [])

    def _get_expected_structure(self, component_name: str) -> str:
        """Get expected path structure for a component_name."""
        convention = self._get_path_convention(component_name)
        if not convention:
            return ""
        return convention.get("expected_structure", "")

    def validate_naming_convention(
        self,
        artifact_name: str
    ) -> Tuple[bool, Optional[str], Optional[Dict], Optional[str]]:
        """
        Validate artifact name against configured patterns.

        Args:
            artifact_name: The artifact's name to validate

        Returns:
            Tuple of (is_valid, matched_pattern_name, matched_groups, error_message)
        """
        if not NAMING_CONVENTION_ENABLED or not self._compiled_patterns:
            return (True, None, None, None)

        for pattern_name, pattern_data in self._compiled_patterns.items():
            match = pattern_data['regex'].match(artifact_name)
            if match:
                return (True, pattern_name, match.groupdict(), None)

        return (False, None, None, "Name does not match any known pattern")

    def get_simulation_type(self, path: str) -> Optional[str]:
        """
        Determine simulation type from path.

        Args:
            path: The artifact's path

        Returns:
            'HiL', 'SiL', or None if not determinable
        """
        if not path:
            return None

        path_parts = path.split('/')
        if 'HiL' in path_parts:
            return 'HiL'
        if 'SiL' in path_parts:
            return 'SiL'
        return None

    def validate_test_type(
        self,
        component_name: str,
        test_type_attribute: Optional[str],
        upload_path: str
    ) -> Tuple[DeviationType, str, str]:
        """
        Validate that testType attribute matches the path Test/{TestType}.

        This validation is component-specific and only applies to certain
        component types (e.g., 'test_ECU-TEST').

        Args:
            component_name: The component type name
            test_type_attribute: The testType value from the API attribute
            upload_path: The artifact's upload path

        Returns:
            Tuple of (DeviationType, details, expected_path_hint)
        """
        # List of component types that require test_type validation
        test_type_components = ['test_ECU-TEST']

        # Only validate for specific component types
        if not component_name or component_name not in test_type_components:
            return (DeviationType.VALID, "", "")

        # Extract test type from path (looking for Test/{TestType} pattern)
        test_type_from_path = self._extract_test_type_from_path(upload_path)

        # If no test type in path or attribute, nothing to validate
        if not test_type_from_path and not test_type_attribute:
            return (DeviationType.VALID, "", "")

        # Check for mismatch
        if test_type_from_path and test_type_attribute:
            if test_type_from_path != test_type_attribute:
                return (
                    DeviationType.TEST_TYPE_MISMATCH,
                    f"testType attribute '{test_type_attribute}' does not match path 'Test/{test_type_from_path}'",
                    f"Expected testType='{test_type_from_path}' based on path, or move artifact to Test/{test_type_attribute}/"
                )

        return (DeviationType.VALID, "", "")

    def _extract_test_type_from_path(self, path: str) -> Optional[str]:
        """
        Extract test type from path by looking for Test/{TestType} pattern.

        Args:
            path: The artifact's upload path

        Returns:
            The test type string if found, None otherwise
        """
        if not path:
            return None

        path_parts = path.split('/')
        for i, part in enumerate(path_parts):
            if part == 'Test' and i + 1 < len(path_parts):
                return path_parts[i + 1]
        return None

    def validate_test_config_software_line(
        self,
        component_name: str,
        test_configuration: Optional[str],
        testbench_configuration: Optional[str],
        software_line: str
    ) -> Tuple[DeviationType, str, str]:
        """
        Validate that P-number in test configuration matches software line.

        The test configuration path contains a P-number (e.g., P2405) that should
        match the last 4 digits of the cleaned software line name.

        Cleaning rules for software line:
        - Remove content in parentheses ()
        - Take value before underscore _
        - Extract continuous alphanumeric string
        - Compare last 4 digits with P-number

        Args:
            component_name: The component type name
            test_configuration: The testConfiguration attribute value (path)
            testbench_configuration: The testbenchConfiguration attribute value (path)
            software_line: The software line name

        Returns:
            Tuple of (DeviationType, details, expected_path_hint)
        """
        # Only validate for test_ECU-TEST components
        if component_name != 'test_ECU-TEST':
            return (DeviationType.VALID, "", "")

        # Extract P-number from test configuration path
        config_path = test_configuration or testbench_configuration
        if not config_path:
            return (DeviationType.VALID, "", "")

        p_number = self._extract_p_number_from_config(config_path)
        if not p_number:
            return (DeviationType.VALID, "", "")

        # Clean software line and get last 4 digits
        sw_line_digits = self._extract_sw_line_digits(software_line)
        if not sw_line_digits:
            return (DeviationType.VALID, "", "")

        # Compare P-number with software line digits
        if p_number != sw_line_digits:
            return (
                DeviationType.TEST_CONFIG_SW_LINE_MISMATCH,
                f"Test config P-number 'P{p_number}' does not match software line '{software_line}' (expected P{sw_line_digits})",
                f"testConfiguration path should contain P{sw_line_digits} for software line '{software_line}'"
            )

        return (DeviationType.VALID, "", "")

    def _extract_p_number_from_config(self, config_path: str) -> Optional[str]:
        """
        Extract P-number from test configuration path.

        Looks for pattern like P1234 or P2405 in the path.

        Args:
            config_path: The testConfiguration or testbenchConfiguration path

        Returns:
            The 4-digit number after P, or None if not found
        """
        if not config_path:
            return None

        # Look for P followed by 4 digits
        match = re.search(r'[/\\]?P(\d{4})[/\\]', config_path)
        if match:
            return match.group(1)

        # Also try without path separators (in case P-number is at end)
        match = re.search(r'P(\d{4})(?:[/\\]|$)', config_path)
        if match:
            return match.group(1)

        return None

    def _extract_sw_line_digits(self, software_line: str) -> Optional[str]:
        """
        Extract last 4 digits from cleaned software line name.

        Cleaning rules:
        1. Remove content in parentheses ()
        2. Take value before underscore _
        3. Extract continuous alphanumeric string
        4. Return last 4 digits

        Args:
            software_line: The software line name

        Returns:
            The last 4 digits of the cleaned name, or None if not found
        """
        if not software_line:
            return None

        # Remove content in parentheses
        cleaned = re.sub(r'\([^)]*\)', '', software_line)

        # Take value before underscore
        if '_' in cleaned:
            cleaned = cleaned.split('_')[0]

        # Extract continuous alphanumeric string (remove any remaining non-alphanumeric)
        cleaned = re.sub(r'[^a-zA-Z0-9]', '', cleaned)

        # Get last 4 digits from the cleaned string
        digits = re.sub(r'[^0-9]', '', cleaned)
        if len(digits) >= 4:
            return digits[-4:]

        return None


def validate_path_simple(path: str) -> Tuple[DeviationType, str, str]:
    """
    Simple path validation without component-specific logic.

    This is a standalone function for use without PathValidator instance.

    Args:
        path: The artifact's path

    Returns:
        Tuple of (DeviationType, details, expected_path_hint)
    """
    path_parts = path.split('/')

    if len(path_parts) < 2:
        return (
            DeviationType.WRONG_LOCATION,
            "Path too short",
            "[Project]/[SWLine]/Model/HiL/[CSP|SWB]/..."
        )

    project_name = path_parts[0]
    sw_line = path_parts[1] if len(path_parts) > 1 else "Unknown"

    if 'Model' not in path_parts:
        return (
            DeviationType.MISSING_MODEL,
            "Artifact not under 'Model' folder",
            f"{project_name}/{sw_line}/Model/HiL/[CSP|SWB]/..."
        )

    model_index = path_parts.index('Model')
    remaining_after_model = path_parts[model_index + 1:]

    if 'HiL' not in remaining_after_model:
        if remaining_after_model and CSP_SWB_PATTERN.search(remaining_after_model[0]):
            return (
                DeviationType.CSP_SWB_UNDER_MODEL,
                "CSP/SWB directly under Model (missing HiL)",
                f"{project_name}/{sw_line}/Model/HiL/{remaining_after_model[0]}/..."
            )
        return (
            DeviationType.MISSING_HIL,
            "Missing 'HiL' folder after Model",
            f"{project_name}/{sw_line}/Model/HiL/[CSP|SWB]/..."
        )

    hil_index = remaining_after_model.index('HiL')
    remaining_after_hil = remaining_after_model[hil_index + 1:]

    if not remaining_after_hil or not CSP_SWB_PATTERN.search(remaining_after_hil[0]):
        return (
            DeviationType.MISSING_CSP_SWB,
            "Missing CSP/SWB folder after HiL",
            f"{project_name}/{sw_line}/Model/HiL/[CSP|SWB]/..."
        )

    return (DeviationType.VALID, "", "")
