from services.db_service import execute_query

def run_fix():
    print("Fixing builds table...")
    try:
        # Drop FK if it still exists (it shouldn't if cascade worked, but just in case)
        execute_query("ALTER TABLE builds DROP CONSTRAINT IF EXISTS builds_project_id_fkey", fetch_all=False)
        
        # Now alter column
        print("Altering builds.project_id to TEXT...")
        execute_query("ALTER TABLE builds ALTER COLUMN project_id TYPE TEXT", fetch_all=False)
        print("Success.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    run_fix()
