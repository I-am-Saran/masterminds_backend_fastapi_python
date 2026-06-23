"""
Certification payload validator - validates request payloads against dropdown values
before insert, update, or delete operations.

Per aig.md guidelines: All certification CRUD operations must validate payloads
against certification_dropdowns.json before database operations.
"""
import json
import os
from typing import Dict, Any, List, Optional
from pathlib import Path

# Load dropdown values from JSON file
def _load_dropdowns() -> Dict[str, List[str]]:
    """Load dropdown values from certification_dropdowns.json"""
    try:
        # Get the directory where this file is located
        current_dir = Path(__file__).parent.parent
        json_path = current_dir / "certification_dropdowns.json"
        
        if not json_path.exists():
            raise FileNotFoundError(f"certification_dropdowns.json not found at {json_path}")
        
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        raise RuntimeError(f"Failed to load certification_dropdowns.json: {str(e)}")

# Cache dropdown values
_DROPDOWN_VALUES = None

def get_dropdown_values() -> Dict[str, List[str]]:
    """Get dropdown values, loading from file if not cached"""
    global _DROPDOWN_VALUES
    if _DROPDOWN_VALUES is None:
        _DROPDOWN_VALUES = _load_dropdowns()
    return _DROPDOWN_VALUES

def validate_certification_payload(payload: Dict[str, Any], operation: str = "create") -> tuple[bool, Optional[str]]:
    """
    Validate certification payload against dropdown values.
    
    Args:
        payload: The certification payload to validate
        operation: Operation type ("create", "update", "delete")
    
    Returns:
        Tuple of (is_valid, error_message)
        - is_valid: True if payload is valid, False otherwise
        - error_message: Error message if invalid, None if valid
    """
    try:
        # For delete operations, we don't need to validate the payload
        if operation == "delete":
            return True, None
        
        dropdowns = get_dropdown_values()
        errors = []
        
        # Required fields for create operation
        if operation == "create":
            if not payload.get("name"):
                errors.append("Required field 'name' is missing or empty")
            if not payload.get("certification_type"):
                errors.append("Required field 'certification_type' is missing or empty")
            if not payload.get("status"):
                errors.append("Required field 'status' is missing or empty")
        
        # Validate dropdown values
        for field_name, allowed_values in dropdowns.items():
            if field_name in payload:
                value = payload[field_name]
                
                # Skip validation if value is empty/None (unless required)
                if value is None or value == "":
                    if operation == "create" and field_name in ["certification_type", "status"]:
                        continue  # Already checked above
                    continue
                
                # Convert to string for comparison
                value_str = str(value).strip()
                
                # Check if value is in allowed list
                if value_str not in allowed_values:
                    errors.append(
                        f"Invalid value '{value_str}' for field '{field_name}'. "
                        f"Allowed values: {', '.join(allowed_values)}"
                    )
        
        if errors:
            return False, "; ".join(errors)
        
        return True, None
    
    except Exception as e:
        return False, f"Validation error: {str(e)}"

def get_field_options(field_name: str) -> List[str]:
    """
    Get allowed options for a specific field.
    
    Args:
        field_name: Name of the field (e.g., "certification_type", "status")
    
    Returns:
        List of allowed values for the field
    """
    try:
        dropdowns = get_dropdown_values()
        return dropdowns.get(field_name, [])
    except Exception:
        return []







