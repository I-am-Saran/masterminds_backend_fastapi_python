
import psycopg2
import os
import sys
from dotenv import load_dotenv

# Add parent directory to path to import config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# Load environment variables
load_dotenv()

DB_URL = config.DB_URL

def create_tables():
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        
        print("Creating testcases table...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS testcases (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                test_case_id VARCHAR(50) NOT NULL,
                project_id UUID REFERENCES projects(id),
                module VARCHAR(255),
                sub_module VARCHAR(255),
                priority VARCHAR(50),
                testing_type VARCHAR(50),
                test_scenario TEXT,
                test_case_title TEXT,
                test_case_description TEXT,
                precondition TEXT,
                test_steps TEXT,
                test_data TEXT,
                expected_result TEXT,
                actual_result TEXT,
                execution_status VARCHAR(50) DEFAULT 'Yet to Start',
                tester_email VARCHAR(255),
                execution_date DATE,
                remarks TEXT,
                bug_id VARCHAR(255),
                tenant_id UUID,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                UNIQUE(test_case_id, project_id)
            );
        """)

        print("Creating testcase_activity_logs table...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS testcase_activity_logs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                testcase_id UUID REFERENCES testcases(id) ON DELETE CASCADE,
                user_id TEXT REFERENCES users(id),
                user_name VARCHAR(255),
                action VARCHAR(255),
                details TEXT,
                timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
        """)

        print("Creating testcase_comments table...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS testcase_comments (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                testcase_id UUID REFERENCES testcases(id) ON DELETE CASCADE,
                user_id TEXT REFERENCES users(id),
                user_name VARCHAR(255),
                comment TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
        """)

        # Add indexes
        print("Adding indexes...")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_testcases_project_id ON testcases(project_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_testcases_execution_status ON testcases(execution_status);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_testcases_tester_email ON testcases(tester_email);")

        conn.commit()
        print("Tables created successfully.")
        
    except Exception as e:
        print(f"Error creating tables: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            cur.close()
            conn.close()

if __name__ == "__main__":
    create_tables()
