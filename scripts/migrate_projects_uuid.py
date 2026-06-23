from services.db_service import execute_query

def run_migration():
    print("Starting migration...")
    
    # 1. Update Builds table first (remove dependency or update type)
    # We alter project_id to TEXT to accommodate UUIDs.
    try:
        print("Altering builds.project_id to TEXT/UUID...")
        # Try casting to text first.
        execute_query("ALTER TABLE builds ALTER COLUMN project_id TYPE TEXT", fetch_all=False)
        # Or better, UUID if we want to be strict. But let's use TEXT for flexibility if DB doesn't have uuid extension enabled by default (supabase usually does).
        # Let's try UUID.
        # execute_query("ALTER TABLE builds ALTER COLUMN project_id TYPE UUID USING (project_id::text::uuid)", fetch_all=False) 
        # The above cast might fail if existing values are ints. 
        # Since we have very little data, let's just use TEXT for now, or DROP and ADD.
        # execute_query("ALTER TABLE builds DROP COLUMN project_id", fetch_all=False)
        # execute_query("ALTER TABLE builds ADD COLUMN project_id UUID", fetch_all=False)
    except Exception as e:
        print(f"Error altering builds table: {e}")

    # 2. Recreate Projects table with UUID id
    try:
        print("Recreating projects table...")
        execute_query("DROP TABLE IF EXISTS projects CASCADE", fetch_all=False)
        
        create_sql = """
        CREATE TABLE projects (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID,
            project_name TEXT,
            product_name TEXT,
            application_name TEXT,
            description TEXT,
            status TEXT DEFAULT 'Active',
            qa_resource_count INTEGER DEFAULT 0,
            start_date DATE,
            end_date DATE,
            expected_closing_date DATE,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        );
        """
        execute_query(create_sql, fetch_all=False)
        print("Projects table recreated with UUID id.")
        
        # Add index on tenant_id
        execute_query("CREATE INDEX IF NOT EXISTS idx_projects_tenant_id ON projects(tenant_id)", fetch_all=False)
        
    except Exception as e:
        print(f"Error recreating projects table: {e}")

    # 3. Restore builds FK if needed (optional, loosely coupled usually)
    # But strictly speaking, we should have it.
    # execute_query("ALTER TABLE builds ADD CONSTRAINT fk_builds_project FOREIGN KEY (project_id) REFERENCES projects(id)", fetch_all=False)

if __name__ == "__main__":
    run_migration()
