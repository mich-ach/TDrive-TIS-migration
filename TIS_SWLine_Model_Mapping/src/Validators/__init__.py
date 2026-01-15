"""Path and naming validation for TIS artifacts.

This module provides classes and functions to validate artifact paths against
expected conventions and naming patterns.

Classes:
    PathValidator: Validates artifact paths against expected conventions

Functions:
    validate_path_simple: Simple path validation without component-specific logic
"""

import re
import logging
from typing import Tuple, List, Dict, Optional

from Models import DeviationType

from config import (
    PATH_CONVENTION_ENABLED,
    PATH_EXPECTED_STRUCTURE,
    PATH_MODEL_SUBFOLDERS,
    PATH_VALID_SUBFOLDERS_HIL,
    NAMING_CONVENTION_ENABLED,
    NAMING_CONVENTION_PATTERNS,
)

logger = logging.getLogger(__name__)

# Expected path patterns
CSP_SWB_PATTERN = re.compile(r"(CSP|SWB)", re.IGNORECASE)


class PathValidator:
    """Validates artifact paths against expected conventions."""

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
                "[Project]/[SWLine]/Model/HiL|SiL/[subfolder]/..."
            )

        project = path_parts[0]
        sw_line = path_parts[1] if len(path_parts) > 1 else "Unknown"

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

        expected_structure = self._get_expected_structure(component_name)
        model_subfolders = self._get_model_subfolders(component_name)

        if not is_hil_path and not is_sil_path:
            if remaining and any(sf in remaining[0] for sf in PATH_VALID_SUBFOLDERS_HIL):
                return (
                    DeviationType.CSP_SWB_UNDER_MODEL,
                    f"{remaining[0]} directly under Model (missing HiL)",
                    f"{project}/{sw_line}/Model/HiL/{remaining[0]}/..."
                )
            return (
                DeviationType.MISSING_HIL,
                "Missing 'HiL' or 'SiL' folder after Model",
                expected_structure or f"{project}/{sw_line}/Model/HiL|SiL/[subfolder]/..."
            )

        if is_hil_path:
            result = self._validate_hil_path(
                remaining, project, sw_line, expected_structure, model_subfolders
            )
            if result[0] != DeviationType.VALID:
                return result

        if is_sil_path:
            result = self._validate_sil_path(
                remaining, project, sw_line, expected_structure, model_subfolders
            )
            if result[0] != DeviationType.VALID:
                return result

        return (DeviationType.VALID, "", "")

    def _validate_hil_path(
        self,
        remaining: List[str],
        project: str,
        sw_line: str,
        expected_structure: str,
        model_subfolders: List[str]
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
        check_subfolders = model_subfolders if model_subfolders else PATH_VALID_SUBFOLDERS_HIL
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
        model_subfolders: List[str]
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

        if model_subfolders:
            first_after_sil = after_sil[0]
            is_valid_subfolder = any(
                sf.lower() in first_after_sil.lower()
                for sf in model_subfolders
            )
            if not is_valid_subfolder:
                return (
                    DeviationType.INVALID_SUBFOLDER,
                    f"Invalid subfolder '{first_after_sil}' after SiL (expected: {', '.join(model_subfolders)})",
                    expected_structure or f"{project}/{sw_line}/Model/SiL/[{'/'.join(model_subfolders)}]/..."
                )

        return (DeviationType.VALID, "", "")

    def _get_model_subfolders(self, component_name: str) -> List[str]:
        """Get expected model subfolders for a component_name by matching patterns."""
        if not component_name:
            return []

        if component_name in PATH_MODEL_SUBFOLDERS:
            return PATH_MODEL_SUBFOLDERS[component_name]

        for pattern, subfolders in PATH_MODEL_SUBFOLDERS.items():
            if pattern.startswith('_comment'):
                continue
            if component_name.startswith(pattern):
                return subfolders

        if 'MDL' in component_name and 'SiL' not in component_name:
            return PATH_VALID_SUBFOLDERS_HIL

        return []

    def _get_expected_structure(self, component_name: str) -> str:
        """Get expected path structure for a component_name."""
        if not component_name:
            return ""

        if component_name in PATH_EXPECTED_STRUCTURE:
            return PATH_EXPECTED_STRUCTURE[component_name]

        for pattern, structure in PATH_EXPECTED_STRUCTURE.items():
            if pattern.startswith('_comment'):
                continue
            if component_name.startswith(pattern):
                return structure

        return ""

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
