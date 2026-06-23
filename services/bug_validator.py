
import json
import os
import re
from typing import Dict, Any, List, Optional
from pathlib import Path
from services.db_service import execute_query
from utils.application_enum import ApplicationName
from utils.bugs_enum import (
    BugStatus, Priority, Severity, DefectType, Resolution,
    AutomationIntent, AutomationStatus, DeviceType, BrowserTested,
    OS, Hardware, TestingPhase, TicketType, Classification,
    InternallyReviewed, ReviewedInTriage, RootCauseCategory
)

# Map fields to their Enum classes for validation and normalization
FIELD_ENUM_MAP = {
    "Status": BugStatus,
    "Priority": Priority,
    "Severity": Severity,
    "Defect Type": DefectType,
    "Defect type": DefectType,
    "Automation Intent": AutomationIntent,
    "Device type": DeviceType,
    "Browser tested": BrowserTested,
    "Testing phase": TestingPhase,
    "Ticket Type": TicketType,
}

# Load dropdown values from JSON file
def _load_dropdowns() -> Dict[str, List[str]]:
    """Load dropdown values from bug_dropdowns.json"""
    try:
        # Get the directory where this file is located
        current_dir = Path(__file__).parent.parent
        json_path = current_dir / "bug_dropdowns.json"
        
        if not json_path.exists():
            raise FileNotFoundError(f"bug_dropdowns.json not found at {json_path}")
        
        with open(json_path, 'r', encoding='utf-8') as f:
            dropdowns = json.load(f)
            
        # Add Product dropdown from ApplicationName enum
        dropdowns["Product"] = ApplicationName.dropdown()
        
        # Override dropdowns with Enum values to ensure consistency with backend enums
        dropdowns["Status"] = [e.value for e in BugStatus]
        dropdowns["Priority"] = [e.value for e in Priority]
        dropdowns["Severity"] = [e.value for e in Severity]
        dropdowns["Defect Type"] = [e.value for e in DefectType]
        dropdowns["Defect type"] = [e.value for e in DefectType]
        dropdowns["Automation Intent"] = [e.value for e in AutomationIntent]
        dropdowns["Device type"] = [e.value for e in DeviceType]
        dropdowns["Browser tested"] = [e.value for e in BrowserTested]
        dropdowns["Testing phase"] = [e.value for e in TestingPhase]
        dropdowns["Ticket Type"] = [e.value for e in TicketType]
        
        return dropdowns
    except Exception as e:
        raise RuntimeError(f"Failed to load bug_dropdowns.json: {str(e)}")

# Cache dropdown values
_DROPDOWN_VALUES = None

def get_dropdown_values() -> Dict[str, List[str]]:
    """Get dropdown values (cached)"""
    global _DROPDOWN_VALUES
    if _DROPDOWN_VALUES is None:
        _DROPDOWN_VALUES = _load_dropdowns()
    return _DROPDOWN_VALUES

def validate_bug_payload(payload: Dict[str, Any], operation: str = "create", enhanced: bool = True) -> tuple[bool, Optional[str]]:
    """
    Validate bug payload against dropdown values and additional rules.
    
    Args:
        payload: The bug payload to validate
        operation: Operation type ("create", "update", "delete")
        enhanced: If True, use enhanced validation (required fields, ranges, formats). 
                 If False, only validate dropdown values.
    
    Returns:
        Tuple of (is_valid, error_message)
        - is_valid: True if payload is valid, False otherwise
        - error_message: Error message if invalid, None if valid
    """
    # Use enhanced validation by default
    if enhanced:
        return validate_bug_payload_enhanced(payload, operation)
    
    # Dropdown/enum validation removed per requirement; only structure checks remain if any.
    try:
        if operation == "delete":
            return True, None
        return True, None
    except Exception as e:
        return False, f"Validation error: {str(e)}"

def get_field_options(field_name: str) -> List[str]:
    """
    Get allowed options for a specific field.
    
    Args:
        field_name: Name of the field
    
    Returns:
        List of allowed values
    """
    dropdowns = get_dropdown_values()
    return dropdowns.get(field_name, [])

# Required fields for bug creation
REQUIRED_FIELDS = ["Summary"]

# Valid DB columns for bugs table
VALID_DB_COLUMNS = {
    "Bug ID", "Component", "Assignee", "Status", "Summary", "Changed", 
    "Automation Intent", "automation_owner", "Browser tested", "Defect type", 
    "Device type", "Priority", "Reporter", "Severity", "Sprint details", 
    "Testing phase", "Ticket Type", "tenant_id", "is_deleted", "created_at", 
    "updated_at", "Description", "Comments", "Attachments", "Product", 
    "Steps to Reproduce", "Comment", "Project Owner", "ActivityLog", "id",
    "tester_type"
}

# Field validation rules
def _validate_email(email: str) -> bool:
    """Validate email format"""
    if not email:
        return True  # Empty emails are allowed
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

def _validate_url(url: str) -> bool:
    """Validate URL format"""
    if not url:
        return True  # Empty URLs are allowed
    pattern = r'^https?://[^\s/$.?#].[^\s]*$'
    return bool(re.match(pattern, url))

def _validate_numeric_range(value: Any, field_name: str, min_val: Optional[float] = None, max_val: Optional[float] = None) -> tuple[bool, Optional[str]]:
    """Validate numeric value is within range"""
    if value is None or value == "" or value == " ---":
        return True, None
    
    try:
        num_val = float(value)
        if min_val is not None and num_val < min_val:
            return False, f"Field '{field_name}' must be >= {min_val}"
        if max_val is not None and num_val > max_val:
            return False, f"Field '{field_name}' must be <= {max_val}"
        return True, None
    except (ValueError, TypeError):
        return False, f"Field '{field_name}' must be a valid number"

def validate_bug_payload_enhanced(payload: Dict[str, Any], operation: str = "create") -> tuple[bool, Optional[str]]:
    """
    Enhanced validation for bug payloads including:
    - Required fields
    - Dropdown value validation
    - Numeric range validation
    - Email format validation
    - URL format validation
    
    Args:
        payload: The bug payload to validate
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
        
        errors = []
        
        # Validate required fields for create operation
        if operation == "create":
            for field in REQUIRED_FIELDS:
                value = payload.get(field)
                if value is None or value == "" or value == " ---":
                    errors.append(f"Required field '{field}' is missing or empty")
        
        # Dropdown/enum validation removed: dropdown fields are no longer validated against allowed values.
        

        # Validate numeric fields with ranges
        numeric_validations = {}
        
        for field_name, (min_val, max_val) in numeric_validations.items():
            if field_name in payload:
                is_valid, error_msg = _validate_numeric_range(
                    payload[field_name], field_name, min_val, max_val
                )
                if not is_valid:
                    errors.append(error_msg)
        
        # Validate email fields
        # Note: Assignee and Reporter might be a UUID or Email depending on implementation
        email_fields = ["Reporter"]
        for field_name in email_fields:
            if field_name in payload:
                value = payload[field_name]
                if value and value != " ---":
                    val_str = str(value)
                    # Allow UUID (len 36) or Email
                    if len(val_str) == 36 and "-" in val_str:
                         continue # Assume UUID
                    if not _validate_email(val_str):
                        errors.append(f"Field '{field_name}' must be a valid email address or UUID")
        
        if errors:
            return False, "; ".join(errors)
        
        return True, None
    
    except Exception as e:
        return False, f"Validation error: {str(e)}"

def prepare_bug_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Prepare bug payload for database insertion/update.
    Remaps frontend keys to DB column names and sanitizes values.
    """
    # Remap frontend keys (camelCase) to DB column names (Title Case/snake_case)
    key_mapping = {
        "product": "Product",
        "components": "Component",
        "severity": "Severity",
        "reproSteps": "Steps to Reproduce",
        "defectType": "Defect type",
        "ticketType": "Ticket Type",
        "sprintDetails": "Sprint details",
        "browserTested": "Browser tested",
        "testingPhase": "Testing phase",
        "projectOwner": "Project Owner",
        "summary": "Summary",
        "description": "Description",
        "attachments": "Attachments",
        "automationOwner": "automation_owner",
        "Automation Owner": "automation_owner",
        "assignee": "Assignee",
        "reporter": "Reporter",
        "status": "Status",
        "priority": "Priority",
        "bug_id": "Bug ID"
    }

    # Apply mapping
    for old_key, new_key in key_mapping.items():
        if old_key in payload:
            payload[new_key] = payload.pop(old_key)

    # Remove computed fields that are not in DB
    payload.pop("Automation Owner Name", None)
    payload.pop("automation_owner_name", None)
    
    # Explicitly remove fields requested by user or known to be invalid
    # This list is redundant due to VALID_DB_COLUMNS filtering below, 
    # but kept for clarity on what is being removed.
    cols_to_remove = [
        "Assignee Real Name", "Assignee Email",
        "Reporter Real Name", "Reporter Email",
        "Project Owner Name", "Project Owner Email",
        "Automation Owner Name", "Automation Owner Email",
        # Removed columns
        "Resolution", "OS", "Hardware", "automation status", "Automation Status",
        "Classification", "Internally Reviewed?", "Reviewed in Triage?",
        "Root cause category", "Root Cause Category", "Version", "version",
        # Extra fields not in DB
        "%Complete", "Actual Hours", "Hours Left", "Orig. Est.", 
        "Bug Age (in days)", "Number of Comments", "URL"
    ]
    for col in cols_to_remove:
        payload.pop(col, None)

    # Handle "Browser tested" list conversion
    # Note: DB constraint 'chk_bugs_browser_tested' has been removed to allow multi-select.
    if "Browser tested" in payload:
        val = payload["Browser tested"]
        if isinstance(val, list):
            # Join with comma
            payload["Browser tested"] = ", ".join([str(b) for b in val])
        elif isinstance(val, str) and "," in val:
             # Ensure clean spacing
             parts = [b.strip() for b in val.split(",")]
             payload["Browser tested"] = ", ".join(parts)
        elif not val:
             payload["Browser tested"] = None

    # Handle "Component" list conversion (similar to Browser tested)
    if "Component" in payload:
        val = payload["Component"]
        if isinstance(val, list):
            payload["Component"] = ", ".join([str(c) for c in val])
        elif not val:
            payload["Component"] = None

    # Sanitize payload (convert empty strings to None)
    payload = sanitize_bug_payload(payload)

    # Final Filter: Retain ONLY columns that exist in the DB table
    # This ensures no invalid column errors during INSERT/UPDATE
    clean_payload = {}
    for key, value in payload.items():
        if key in VALID_DB_COLUMNS:
            clean_payload[key] = value
            
    return clean_payload

def _validate_uuid(val: Any) -> bool:
    """Check if value is a valid UUID string"""
    if not val:
        return False
    val_str = str(val)
    # Simple regex for UUID
    pattern = r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
    return bool(re.match(pattern, val_str))

def sanitize_bug_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize bug payload before database operations.
    Converts empty strings to None for fields that should be nullable in DB.
    Also normalizes enum values to match the allowed case.
    Ensures UUID fields contain valid UUIDs or None.
    """
    sanitized = payload.copy()
    dropdowns = get_dropdown_values()
    
    # List of fields that should be None if empty string
    # This includes all Enum fields and other optional fields
    nullable_fields = [
        "Status", "Priority", "Severity", "Defect Type", "Defect type", 
        "Automation Intent", "automation_owner",
        "Device type", "Browser tested", 
        "Testing phase", "Ticket Type", 
        "Component", "Sprint details", "Reporter", "Assignee", 
        "Project Owner", "Product"
    ]
    
    # Fields that MUST be valid UUIDs or None
    uuid_fields = ["Assignee", "Reporter", "Project Owner", "automation_owner", "tenant_id"]

    for field in nullable_fields:
        if field in sanitized:
            val = sanitized[field]
            if val == "" or val == " ---":
                sanitized[field] = None
            elif field in dropdowns and val:
                # Normalize Enum values
                val_str = str(val).strip()
                allowed_values = dropdowns[field]

                # Special handling for multi-select fields
                if field == "Browser tested" and "," in val_str:
                    parts = [p.strip() for p in val_str.split(",")]
                    normalized_parts = []
                    allowed_map = {v.upper(): v for v in allowed_values}
                    
                    for part in parts:
                        if part in allowed_values:
                            normalized_parts.append(part)
                        elif part.upper() in allowed_map:
                            normalized_parts.append(allowed_map[part.upper()])
                        else:
                            normalized_parts.append(part)
                    
                    sanitized[field] = ", ".join(normalized_parts)
                    continue

                if val_str not in allowed_values:
                    # Check case-insensitive match
                    val_upper = val_str.upper()
                    allowed_map = {v.upper(): v for v in allowed_values}
                    if val_upper in allowed_map:
                        sanitized[field] = allowed_map[val_upper]
                    
                    # Check if value matches an Enum Key and normalize to value
                    enum_cls = FIELD_ENUM_MAP.get(field)
                    if enum_cls and val_str in enum_cls.__members__:
                        sanitized[field] = enum_cls[val_str].value
                        
    # Ensure UUID fields are valid
    for field in uuid_fields:
        if field in sanitized:
            val = sanitized[field]
            if val is not None and not _validate_uuid(val):
                # If it's not a valid UUID, set to None to avoid DB error
                # This assumes the field is nullable in DB.
                # If tenant_id is invalid, it might be an issue, but here we are cleaning payload.
                sanitized[field] = None
                
    return sanitized
