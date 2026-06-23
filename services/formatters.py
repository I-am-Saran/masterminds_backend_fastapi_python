import json
def normalize_control(row, include_comments_and_tasks=True):
    # map raw DB columns to stable snake_case keys used by frontend
    normalized = {
        "sno": row.get("sno") or row.get("S.No") or row.get("sno_") or row.get("sno"),
        "id": row.get("id") or row.get("ID"),
        "code": row.get("code") or row.get("Code"),
        "summary": row.get("summary") or row.get("Summary"),
        "guidance": row.get("guidance") or row.get("Guidance"),
        # "uuid": row.get("uuid") or row.get("UUID"),
        "analyze_comments": row.get("analyze_comments") or row.get("Analyze Comments"),
        "observations_action_item": row.get("observations_action_item") or row.get("Observations/Action Item") or row.get("observations_action_item"),
        "responsible_team": row.get("responsible_team") or row.get("Reponsible Team") or row.get("Responsible Team"),
        "owner": row.get("owner") or row.get("Owner"),
        "audit_owner": row.get("audit_owner") or row.get("Audit Owner"),
        "department": row.get("department") or row.get("Department"),
        "organization": row.get("organization") or row.get("Organization"),
        "organization_id": row.get("organization_id"),
        "control_domain": row.get("control_domain") or row.get("Control_Domain") or row.get("Control Domain"),
        "requirement": row.get("requirement") or row.get("Requirement") or row.get("Requirement (Security Controls)"),
        "description": row.get("description") or row.get("Description"),
        "ISO_27001": row.get("ISO_27001") or row.get("ISO 27001"),
        "NIST_CSF": row.get("NIST_CSF") or row.get("NIST CSF"),
        "SOC_2": row.get("SOC_2") or row.get("SOC 2"),
        "GDPR": row.get("GDPR"),
        "IT_Act_2000": row.get("IT_Act_2000") or row.get("IT Act 2000"),
        "PCI_DSS": row.get("PCI_DSS") or row.get("PCI DSS"),
        "HIPAA": row.get("HIPAA"),
        "Priority": row.get("Priority") or row.get("priority"),
        "Status": row.get("Status"),
        "Review_Date": row.get("review_date") or row.get("Review_Date") or row.get("Review Date"),
        "last_review_date": row.get("last_review_date") or row.get("Last Review Date") or row.get("Last_Review_Date"),
        "Audit_Review_Status": row.get("Audit_Review_Status") or row.get("Audit Review Status"),
        "Plan": row.get("Plan"),
        "Do": row.get("Do"),
        "Check": row.get("Check"),
        "Act": row.get("Act"),
        "Date": row.get("Date"),
        "Comments_1": row.get("Comments_1") or row.get("Comments2") or row.get("Comments 2"),
        "certification": row.get("certification"),
        "updated_at": row.get("updated_at"),
    }
    env_raw = row.get("Environment")
    if isinstance(env_raw, str):
        try:
            normalized["Environment"] = json.loads(env_raw)
        except Exception:
            normalized["Environment"] = env_raw
    elif env_raw is not None:
        normalized["Environment"] = env_raw
    
    # Only include Comments and task if explicitly requested (for detail view)
    if include_comments_and_tasks:
        normalized["Comments"] = row.get("Comments") or row.get("comments")
        normalized["task"] = row.get("task")
    
    return normalized

def normalize_control_list(row):
    """Normalize control for list endpoints - excludes Comments and task to reduce payload size."""
    return normalize_control(row, include_comments_and_tasks=False)

def normalize_action(row):
    """Normalize action row from database to frontend format."""
    return {
        "id": row.get("id"),
        "control_id": row.get("control_id"),
        "action_name": row.get("action_name"),
        "action_description": row.get("action_description"),
        "action_priority": row.get("action_priority"),
        "action_status": row.get("action_status"),
        "action_type": row.get("action_type"),
        "assigned_to": row.get("assigned_to"),
        "due_date": row.get("due_date"),
        "notes": row.get("notes"),
        "comments": row.get("comments"),
        "tenant_id": row.get("tenant_id"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "is_deleted": row.get("is_deleted", False),
        "deleted_at": row.get("deleted_at"),
        "deleted_by": row.get("deleted_by"),
    }
