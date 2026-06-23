
from typing import List, Dict, Any, Optional
from services.db_service import execute_query, insert_table, update_table, get_connection as get_db_connection
from datetime import datetime
import psycopg2
from psycopg2.extras import Json

class TestcaseService:
    
    @staticmethod
    def get_projects_with_testcases(tenant_id: str) -> List[Dict[str, Any]]:
        query = """
            SELECT 
                p.id as project_id,
                p.project_name,
                COUNT(t.id) as testcase_count,
                MAX(t.updated_at) as last_updated
            FROM projects p
            LEFT JOIN testcases t ON p.id = t.project_id AND (t.is_deleted = FALSE OR t.is_deleted IS NULL)
            WHERE p.tenant_id = %s
            GROUP BY p.id, p.project_name
            ORDER BY p.project_name
        """
        return execute_query(query, (tenant_id,), fetch_all=True) or []

    @staticmethod
    def get_project_testcases(project_id: str, filters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        query = """
            SELECT 
                t.id, t.test_case_id, t.project_id, t.module, t.sub_module, t.priority, 
                t.execution_status, t.tester_email, t.execution_date, t.use_case, 
                t.flow_type, t.actor, t.trigger_action, t.test_case_title, t.testing_type,
                u.full_name as tester_name
            FROM testcases t
            LEFT JOIN users u ON t.tester_email = u.email
            WHERE t.project_id = %s AND (t.is_deleted = FALSE OR t.is_deleted IS NULL)
        """
        params = [project_id]
        
        # Apply filters
        if filters:
            if filters.get("execution_status"):
                query += " AND t.execution_status = %s"
                params.append(filters["execution_status"])
            if filters.get("priority"):
                query += " AND t.priority = %s"
                params.append(filters["priority"])
            if filters.get("tester_email"): # Filter by email or name? Prompt says "Tester"
                query += " AND t.tester_email = %s"
                params.append(filters["tester_email"])
            if filters.get("module"):
                query += " AND t.module = %s"
                params.append(filters["module"])
            # Date filter logic can be complex (range vs specific date), simplistic for now
            if filters.get("date"):
                query += " AND t.execution_date = %s"
                params.append(filters["date"])

        query += " ORDER BY t.test_case_id"
        
        return execute_query(query, tuple(params), fetch_all=True) or []

    @staticmethod
    def get_project_filter_options(project_id: str) -> Dict[str, List[str]]:
        """Get distinct modules and testers for a project."""
        
        # Get modules
        modules_query = """
            SELECT DISTINCT module 
            FROM testcases 
            WHERE project_id = %s AND (is_deleted = FALSE OR is_deleted IS NULL) AND module IS NOT NULL AND module != ''
            ORDER BY module
        """
        modules = execute_query(modules_query, (project_id,), fetch_all=True) or []
        
        # Get testers (email and name)
        testers_query = """
            SELECT DISTINCT t.tester_email, u.full_name
            FROM testcases t
            LEFT JOIN users u ON t.tester_email = u.email
            WHERE t.project_id = %s AND (t.is_deleted = FALSE OR t.is_deleted IS NULL) AND t.tester_email IS NOT NULL
            ORDER BY u.full_name
        """
        testers = execute_query(testers_query, (project_id,), fetch_all=True) or []
        
        return {
            "modules": [m["module"] for m in modules],
            "testers": [{"email": t["tester_email"], "name": t["full_name"] or t["tester_email"]} for t in testers]
        }

    @staticmethod
    def get_testcase_details(testcase_id: str) -> Optional[Dict[str, Any]]:
        query = "SELECT * FROM testcases WHERE id = %s AND (is_deleted = FALSE OR is_deleted IS NULL)"
        rows = execute_query(query, (testcase_id,), fetch_all=True)
        return rows[0] if rows else None

    @staticmethod
    def create_bulk_testcases(rows: List[Dict[str, Any]], tenant_id: str):
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            for row in rows:
                # Ensure tenant_id is added
                row['tenant_id'] = tenant_id
                
                # Using insert_table logic manually to support bulk inside transaction
                # But insert_table commits by default? No, db_service.insert_table creates its own connection/cursor usually.
                # I should write raw SQL for transaction safety here.
                
                columns = list(row.keys())
                values = [row[col] for col in columns]
                placeholders = ",".join(["%s"] * len(values))
                col_str = ",".join(columns)
                
                query = f"INSERT INTO testcases ({col_str}) VALUES ({placeholders})"
                cur.execute(query, tuple(values))
            
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cur.close()
            conn.close()

    @staticmethod
    def update_testcase(testcase_id: str, updates: Dict[str, Any], user: Dict[str, Any]):
        # Get old values for activity log
        old_data = TestcaseService.get_testcase_details(testcase_id)
        if not old_data:
            raise ValueError("Testcase not found")

        # Update
        update_table("testcases", updates, {"id": testcase_id})
        
        # Log activity
        for key, new_val in updates.items():
            old_val = old_data.get(key)
            
            # Normalize for comparison (treat None as empty string)
            normalized_old = str(old_val) if old_val is not None else ""
            normalized_new = str(new_val) if new_val is not None else ""
            
            # Also handle 'None' string literal if it somehow got in
            if normalized_old == 'None': normalized_old = ""
            if normalized_new == 'None': normalized_new = ""

            if normalized_old != normalized_new:
                TestcaseService.log_activity(
                    testcase_id, 
                    user, 
                    "Update", 
                    f"Changed {key} from '{old_val}' to '{new_val}'"
                )

    @staticmethod
    def delete_testcase(testcase_id: str):
        # Soft delete using update_table which handles commit correctly
        update_table("testcases", {"is_deleted": True}, {"id": testcase_id})

    @staticmethod
    def log_activity(testcase_id: str, user: Dict[str, Any], action: str, details: str):
        data = {
            "testcase_id": testcase_id,
            "user_id": user.get("id"),
            "user_name": user.get("full_name") or user.get("email"),
            "action": action,
            "details": details,
            "timestamp": datetime.now()
        }
        insert_table("testcase_activity_logs", data)

    @staticmethod
    def get_activity_logs(testcase_id: str):
        query = "SELECT * FROM testcase_activity_logs WHERE testcase_id = %s ORDER BY timestamp DESC"
        return execute_query(query, (testcase_id,), fetch_all=True)

    @staticmethod
    def add_comment(testcase_id: str, user: Dict[str, Any], comment: str):
        data = {
            "testcase_id": testcase_id,
            "user_id": user.get("id"),
            "user_name": user.get("full_name") or user.get("email"),
            "comment": comment,
            "created_at": datetime.now()
        }
        insert_table("testcase_comments", data)

    @staticmethod
    def get_comments(testcase_id: str):
        query = "SELECT * FROM testcase_comments WHERE testcase_id = %s ORDER BY created_at DESC"
        return execute_query(query, (testcase_id,), fetch_all=True)

    @staticmethod
    def get_valid_projects_map(tenant_id: str):
        query = "SELECT id, project_name FROM projects WHERE tenant_id = %s"
        rows = execute_query(query, (tenant_id,), fetch_all=True) or []
        # Return map: lowercase name -> id
        return {r["project_name"].lower(): r["id"] for r in rows if r.get("project_name")}

    @staticmethod
    def get_valid_users_list(tenant_id: str):
        query = "SELECT email FROM users WHERE tenant_id = %s"
        rows = execute_query(query, (tenant_id,), fetch_all=True) or []
        return [r["email"].lower() for r in rows if r.get("email")]

    @staticmethod
    def check_existing_testcase_ids(testcase_ids: List[str], tenant_id: str) -> List[str]:
        if not testcase_ids:
            return []
        
        placeholders = ",".join(["%s"] * len(testcase_ids))
        query = f"SELECT test_case_id FROM testcases WHERE tenant_id = %s AND test_case_id IN ({placeholders})"
        
        params = [tenant_id] + testcase_ids
        rows = execute_query(query, tuple(params), fetch_all=True) or []
        
        return [r["test_case_id"] for r in rows]
