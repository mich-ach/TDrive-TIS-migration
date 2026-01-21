"""Software line mapping logic.

This module handles the matching between Excel software lines and TIS artifact data.
"""

import logging
import re
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class MappingHandler:
    """Handles software line matching and mapping creation."""

    @staticmethod
    def clean_software_line(sw_line: str) -> str:
        """
        Clean software line for matching:
        - Remove everything after underscore, space, dash, or opening bracket
        - Remove special characters (dots, etc.)
        - Return uppercase for case-insensitive matching

        Examples:
            "MED17.1.10-6.1" -> "MED17110" (split at dash, remove dots)
            "MG1CS001_test" -> "MG1CS001" (split at underscore)
        """
        if not sw_line:
            return ""

        # First, take everything before underscore, space, dash, or opening bracket
        cleaned = re.split(r'[_\s\-\(\[\{]', sw_line)[0]

        # Remove special characters (dots, etc.)
        cleaned = re.sub(r'[^a-zA-Z0-9]', '', cleaned)

        return cleaned.strip().upper()

    def create_mapping(
        self,
        software_lines: List[str],
        json_data: Dict[str, Any],
        master_data: Dict[str, Dict[str, str]]
    ) -> Dict[str, Any]:
        """
        Create mapping between software lines and latest artifacts JSON data.

        Uses flexible matching by cleaning software line names.

        Args:
            software_lines: List of software lines from Excel
            json_data: Parsed JSON data from TIS artifacts export
            master_data: Additional master data for each software line

        Returns:
            Dictionary mapping software lines to their TIS data
        """
        # Log debug info about master data
        logger.info("Master data info:")
        logger.info(f"  Total entries in master data: {len(master_data)}")
        logger.debug("Sample master data entries:")
        for key in list(master_data.keys())[:3]:
            logger.debug(f"  {key}: {master_data[key]}")

        mapping = {}

        # Create lookup dictionary for json data with cleaned keys
        json_lookup = self._build_json_lookup(json_data)

        # Log lookup table for debugging
        self._log_lookup_examples(json_data)

        # Process each software line
        for sw_line in software_lines:
            mapping[sw_line] = self._create_mapping_entry(
                sw_line, json_lookup, master_data
            )

        # Log matching statistics
        self._log_matching_stats(software_lines, mapping)

        return mapping

    def _build_json_lookup(self, json_data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Build a lookup dictionary with cleaned keys for fast matching."""
        json_lookup = {}

        for project_name, project_data in json_data.items():
            for sw_line in project_data.get('software_lines', {}):
                cleaned_key = self.clean_software_line(sw_line)
                if cleaned_key:
                    json_lookup[cleaned_key] = {
                        'original_key': sw_line,
                        'project_name': project_name,
                        'project_data': project_data
                    }

        return json_lookup

    def _create_mapping_entry(
        self,
        sw_line: str,
        json_lookup: Dict[str, Dict[str, Any]],
        master_data: Dict[str, Dict[str, str]]
    ) -> Dict[str, Any]:
        """Create a mapping entry for a single software line."""
        # Get master data for this software line
        line_master_data = master_data.get(sw_line, {
            "ECU - HW Variante": "",
            "Project class": ""
        })

        entry = {
            'project': None,
            'project_rid': None,
            'found': False,
            'software_line_rid': None,
            'latest_artifact': None,
            'master_data': line_master_data,
            'matched_with': None
        }

        # Clean the software line for matching
        cleaned_sw_line = self.clean_software_line(sw_line)

        if cleaned_sw_line in json_lookup:
            match_data = json_lookup[cleaned_sw_line]
            original_key = match_data['original_key']
            project_name = match_data['project_name']
            project_data = match_data['project_data']
            sw_line_data = project_data['software_lines'][original_key]

            entry.update({
                'project': project_name,
                'project_rid': project_data.get('project_rid'),
                'found': True,
                'software_line_rid': sw_line_data.get('software_line_rid'),
                'latest_artifact': sw_line_data.get('latest_artifact'),
                'matched_with': original_key
            })

        return entry

    def _log_lookup_examples(self, json_data: Dict[str, Any]) -> None:
        """Log examples from the lookup table for debugging."""
        if json_data:
            first_project = list(json_data.items())[0][1]
            sw_lines_sample = list(first_project.get('software_lines', {}).keys())[:10]
            logger.debug("Lookup table examples:")
            for original in sw_lines_sample:
                logger.debug(
                    f"  Original: {original} -> Cleaned: {self.clean_software_line(original)}"
                )

    def _log_matching_stats(
        self, software_lines: List[str], mapping: Dict[str, Any]
    ) -> None:
        """Log statistics about the matching results."""
        matches = sum(1 for m in mapping.values() if m['found'])

        logger.info("Matching Statistics:")
        logger.info(f"  Total software lines: {len(software_lines)}")
        logger.info(f"  Found matches: {matches}")
        logger.info(f"  Missing matches: {len(software_lines) - matches}")

        # Log examples of matches at debug level
        matched_examples = [
            (sw_line, data['matched_with'])
            for sw_line, data in mapping.items()
            if data['found'] and sw_line != data['matched_with']
        ][:5]

        if matched_examples:
            logger.debug("Example matches (original -> matched):")
            for original, matched in matched_examples:
                logger.debug(f"  '{original}' -> '{matched}'")
