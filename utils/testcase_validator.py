
from typing import List, Dict, Any, Tuple
import pandas as pd
import io

import re
import json

def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r'[^a-z0-9]+', '_', text)
    return text.strip('_')

# Define DB columns to map directly. Others go to custom_fields.
DB_COLUMNS = {
    "test_case_id", "project_id", "module", "sub_module", "priority", "testing_type",
    "test_scenario", "test_case_title", "test_case_description", "precondition",
    "test_steps", "test_data", "expected_result", "actual_result", "execution_status",
    "tester_email", "tester_name", "execution_date", "remarks", "bug_id",
    "use_case", "flow_type", "actor", "trigger_action", "email_notification", "exception_handling"
}

# Mapping of known Excel headers to DB columns
HEADER_MAPPING = {
    "Test Case ID": "test_case_id",
    "Project": "project_id", # Handled specially
    "Module": "module",
    "Sub Module": "sub_module",
    "Priority": "priority",
    "Testing Type": "testing_type",
    "Test Scenario": "test_scenario",
    "Test Case Title": "test_case_title",
    "Test Case Descriptions": "test_case_description",
    "Precondition": "precondition",
    "Test Steps": "test_steps",
    "Test Data": "test_data",
    "Expected Result": "expected_result",
    "Actual Result": "actual_result",
    "Execution Status": "execution_status",
    "Tester Name": "tester_email", # Kept as tester_email for logic, though there's also tester_name
    "Execution Date": "execution_date",
    "Remarks": "remarks",
    "Bug ID": "bug_id",
    "Use Case": "use_case",
    "Flow Type": "flow_type",
    "Actor": "actor",
    "Trigger/Action": "trigger_action",
    "Email/Notification": "email_notification",
    "Exception Handling": "exception_handling"
}

VALID_EXECUTION_STATUSES = [
    "Yet to Start",
    "Pass",
    "Fail",
    "Hold",
    "Postpond"
]

def validate_excel_file(file_content: bytes, valid_projects: Dict[str, str], valid_users: List[str]) -> Tuple[bool, List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Validates the uploaded Excel file dynamically.
    """
    try:
        df = pd.read_excel(io.BytesIO(file_content))
    except Exception as e:
        return False, [], [{"row": 0, "column": "File", "message": f"Invalid Excel file: {str(e)}"}]

    columns = df.columns.tolist()
    
    # Minimal mandatory columns
    if "Test Case ID" not in columns or "Project" not in columns:
        return False, [], [{"row": 0, "column": "Headers", "message": "Missing mandatory columns: 'Test Case ID' and 'Project' are required."}]

    errors = []
    processed_rows = []

    for index, row in df.iterrows():
        excel_row_num = index + 2
        row_data = {}
        row_has_error = False
        custom_fields = {}

        # 1. Project Validation
        project_name = str(row["Project"]).strip() if pd.notna(row["Project"]) else ""
        if not project_name:
             errors.append({"row": excel_row_num, "column": "Project", "message": "Project name is required"})
             row_has_error = True
        elif project_name.lower() not in valid_projects:
             errors.append({"row": excel_row_num, "column": "Project", "message": f"Project '{project_name}' not found in database"})
             row_has_error = True
        else:
            row_data["project_id"] = valid_projects[project_name.lower()]

        # Iterate all columns dynamically
        for col in columns:
            if col == "Project" or col == "S.No":
                continue
                
            val = row[col]
            # Handle NaN
            if pd.isna(val):
                val = None
            elif isinstance(val, str):
                val = val.strip()

            db_col = HEADER_MAPPING.get(col)
            
            # Special Validations
            if db_col == "test_case_id":
                if not val:
                    errors.append({"row": excel_row_num, "column": "Test Case ID", "message": "Test Case ID is required"})
                    row_has_error = True
                row_data["test_case_id"] = str(val) if val else ""
            
            elif db_col == "execution_status":
                status = val if val else "Yet to Start"
                if status not in VALID_EXECUTION_STATUSES:
                    errors.append({"row": excel_row_num, "column": "Execution Status", "message": f"Invalid value '{status}'. Allowed: {', '.join(VALID_EXECUTION_STATUSES)}"})
                    row_has_error = True
                row_data["execution_status"] = status
                
            elif db_col == "tester_email":
                tester_email = str(val) if val else ""
                if tester_email:
                    if tester_email.lower() not in valid_users:
                        errors.append({"row": excel_row_num, "column": "Tester Name", "message": f"Email '{tester_email}' not found in users table"})
                        row_has_error = True
                    row_data["tester_email"] = tester_email
                else:
                    row_data["tester_email"] = None
                    
            elif db_col == "execution_date":
                if val:
                    try:
                        row_data["execution_date"] = pd.to_datetime(val).date()
                    except:
                        row_data["execution_date"] = None
                else:
                    row_data["execution_date"] = None
                    
            elif db_col:
                # Other known columns
                row_data[db_col] = str(val) if val is not None else None
                
            else:
                # Unknown columns go to custom_fields
                if val is not None:
                    custom_fields[col] = str(val)

        row_data["custom_fields"] = json.dumps(custom_fields)
        row_data["excel_row_num"] = excel_row_num

        if not row_has_error:
            processed_rows.append(row_data)

    if errors:
        return False, [], errors
    
    return True, processed_rows, []
