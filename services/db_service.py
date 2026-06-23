"""
Database Service - Direct PostgreSQL connection service
Replaces Supabase client for local development
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.sql import Identifier, SQL, Composed
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID
from config import DB_URL


def serialize_param(value: Any) -> Any:
    """Convert complex types like UUID to string for database compatibility."""
    if isinstance(value, UUID):
        return str(value)
    return value


def get_connection():
    """Get a database connection."""
    return psycopg2.connect(DB_URL)


def table_exists(table_name: str) -> bool:
    """Return True if a public schema table exists."""
    try:
        row = execute_query(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = %s LIMIT 1",
            (table_name,),
            fetch_one=True,
        )
        return bool(row)
    except Exception:
        return False


def execute_query(query: str or SQL, params: tuple = None, fetch_one: bool = False, fetch_all: bool = True) -> Optional[Any]:
    """Execute a SQL query and return results."""
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # Handle both string queries and psycopg2 SQL objects
        if isinstance(query, SQL):
            cur.execute(query, params or ())
        else:
            cur.execute(query, params or ())
        
        query_str = str(query) if isinstance(query, SQL) else query
        is_modifying = query_str.strip().upper().startswith(('INSERT', 'UPDATE', 'DELETE', 'ALTER', 'CREATE', 'DROP'))

        if fetch_all is False:
            conn.commit()
            return None

        # Statements without a result set (e.g. DELETE without RETURNING)
        if cur.description is None:
            if is_modifying:
                conn.commit()
            return [] if fetch_all else None

        if fetch_one:
            result = cur.fetchone()
            result_dict = dict(result) if result else None
            # Commit modifying queries
            if is_modifying:
                conn.commit()
            return result_dict
        elif fetch_all:
            results = cur.fetchall()
            result_list = [dict(row) for row in results]
            if is_modifying:
                conn.commit()
            return result_list
        else:
            conn.commit()
            return None
    except Exception as e:
        if conn:
            conn.rollback()
        # Print more details for debugging
        if "tuple index out of range" in str(e).lower():
            query_str = str(query) if not isinstance(query, str) else query
            print(f"[DEBUG] Query: {query_str[:500] if isinstance(query_str, str) else 'N/A'}")
            print(f"[DEBUG] Params count: {len(params) if params else 0}")
            print(f"[DEBUG] Placeholders in query: {query_str.count('%s') if isinstance(query_str, str) else 'N/A'}")
        print(f"Database error: {e}")
        raise
    finally:
        if conn:
            conn.close()


def select_table(table_name: str, filters: Dict[str, Any] = None, order_by: str = None, limit: int = None) -> List[Dict[str, Any]]:
    """Select records from a table with optional filters."""
    query = f"SELECT * FROM {table_name}"
    params = []
    conditions = []
    
    if filters:
        for key, value in filters.items():
            if key == "is_deleted" and (value is False or value == "n" or str(value).lower() == "false"):
                conditions.append(f"({key} = %s OR {key} IS NULL)")
                params.append(serialize_param(value))
            elif isinstance(value, list):
                placeholders = ','.join(['%s'] * len(value))
                conditions.append(f"{key} IN ({placeholders})")
                params.extend([serialize_param(v) for v in value])
            else:
                conditions.append(f"{key} = %s")
                params.append(serialize_param(value))
    
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    
    if order_by:
        query += f" ORDER BY {order_by}"
    
    if limit:
        query += f" LIMIT {limit}"
    
    return execute_query(query, tuple(params) if params else None, fetch_all=True) or []


def insert_table(table_name: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Insert a record into a table."""
    # Filter out None values (except for required fields) and empty strings that should be NULL
    filtered_data = {}
    for key, value in data.items():
        # Keep the value if it's not None, or if it's a required field
        if value is not None:
            filtered_data[key] = value
        elif key in ["Bug ID", "tenant_id"]:  # Required fields that shouldn't be None
            filtered_data[key] = value
    
    if not filtered_data:
        return None
    
    # Use psycopg2's Identifier to properly quote column names
    columns = SQL(', ').join([Identifier(key) for key in filtered_data.keys()])
    # Use plain %s strings for placeholders (not SQL objects)
    placeholders = SQL(', ').join([SQL('%s')] * len(filtered_data))
    # Build query with proper formatting
    query = SQL("INSERT INTO {table} ({columns}) VALUES ({placeholders}) RETURNING *").format(
        table=Identifier(table_name),
        columns=columns,
        placeholders=placeholders
    )
    params = tuple(serialize_param(v) for v in filtered_data.values())
    
    # Convert query to string for execution with params
    # When using SQL composition, we need to use as_string() or execute with the Composed object directly
    # The issue is that psycopg2 expects placeholders to be %s strings, not SQL objects
    # So we'll build the query string manually for proper parameter binding
    # Escape % characters in column names by doubling them (%% becomes % in SQL)
    quoted_column_names = []
    for key in filtered_data.keys():
        # Double any % characters in the column name to escape them for psycopg2
        escaped_key = key.replace('%', '%%')
        quoted_column_names.append(f'"{escaped_key}"')
    column_names = ', '.join(quoted_column_names)
    placeholder_str = ', '.join(['%s'] * len(filtered_data))
    # Use string concatenation to avoid f-string interpretation of % characters
    query_str = 'INSERT INTO "' + table_name + '" (' + column_names + ') VALUES (' + placeholder_str + ') RETURNING *'
    
    # Debug: Print query and param count if they don't match
    if len(params) != len(filtered_data):
        print(f"[DEBUG] Mismatch: {len(params)} params vs {len(filtered_data)} columns")
        print(f"[DEBUG] Query: {query_str[:200]}...")
        print(f"[DEBUG] Columns: {list(filtered_data.keys())[:10]}")
    
    return execute_query(query_str, params, fetch_one=True)


def update_table(table_name: str, data: Dict[str, Any], filters: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Update records in a table."""
    def quote_column(col: str) -> str:
        """Quote column name if it contains special characters or is case-sensitive."""
        if col.startswith('"') and col.endswith('"'):
            return col  # Already quoted
        # Quote if contains spaces, special chars, starts with capital, or contains %
        if ' ' in col or '-' in col or col[0].isupper() or '%' in col or '(' in col or ')' in col:
            return f'"{col}"'
        return col
    
    set_clause = ', '.join([f"{quote_column(key)} = %s" for key in data.keys()])
    where_clause = ' AND '.join([f"{quote_column(key)} = %s" for key in filters.keys()])
    query = f"UPDATE {table_name} SET {set_clause} WHERE {where_clause} RETURNING *"
    params = tuple(serialize_param(v) for v in list(data.values()) + list(filters.values()))
    return execute_query(query, params, fetch_one=True)


def delete_table(table_name: str, filters: Dict[str, Any]) -> Tuple[bool, int]:
    """Delete records from a table.
    
    Returns:
        Tuple of (success: bool, rowcount: int)
    """
    def quote_column(col: str) -> str:
        """Quote column name if it contains special characters or is case-sensitive."""
        if col.startswith('"') and col.endswith('"'):
            return col  # Already quoted
        # Quote if contains spaces, special chars, starts with capital, or contains %
        if ' ' in col or '-' in col or col[0].isupper() or '%' in col or '(' in col or ')' in col:
            return f'"{col}"'
        return col
    
    where_clause = ' AND '.join([f"{quote_column(key)} = %s" for key in filters.keys()])
    query = f"DELETE FROM {table_name} WHERE {where_clause}"
    params = tuple(serialize_param(v) for v in filters.values())
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(query, params)
        rowcount = cur.rowcount
        conn.commit()
        return (True, rowcount)
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"Delete error: {e}")
        return (False, 0)
    finally:
        if conn:
            conn.close()


# Compatibility layer to mimic Supabase table API
class TableProxy:
    """Proxy class to mimic Supabase table API for easier migration."""
    
    def __init__(self, table_name: str):
        self.table_name = table_name
        self.reset()
    
    def reset(self):
        """Reset query state."""
        self._filters = {}
        self._order_by = None
        self._limit = None
        self._select_cols = "*"
        self._ilike_filters = {}
        if hasattr(self, '_update_data'):
            delattr(self, '_update_data')
        if hasattr(self, '_insert_data'):
            delattr(self, '_insert_data')
        if hasattr(self, '_returning'):
            delattr(self, '_returning')
        if hasattr(self, '_count_mode'):
            delattr(self, '_count_mode')
        if hasattr(self, '_delete_mode'):
            delattr(self, '_delete_mode')
        if hasattr(self, '_neq_filters'):
            delattr(self, '_neq_filters')
        if hasattr(self, '_in_filters'):
            delattr(self, '_in_filters')
    
    def select(self, columns: str = "*", count: str = None):
        """Select columns. count parameter is ignored for local DB (Supabase compatibility)."""
        self._select_cols = columns
        self._count_mode = count  # Store but don't use for now
        return self
    
    def eq(self, column: str, value: Any):
        """Add equality filter."""
        self._filters[column] = value
        return self
    
    def ilike(self, column: str, pattern: str):
        """Add ILIKE filter."""
        # Store ILIKE filters separately
        if not hasattr(self, '_ilike_filters'):
            self._ilike_filters = {}
        self._ilike_filters[column] = pattern
        return self
    
    def neq(self, column: str, value: Any):
        """Add inequality filter."""
        if not hasattr(self, '_neq_filters'):
            self._neq_filters = {}
        self._neq_filters[column] = value
        return self
    
    def in_(self, column: str, values: List[Any]):
        """Add IN filter."""
        if not hasattr(self, '_in_filters'):
            self._in_filters = {}
        self._in_filters[column] = values
        return self
    
    def order(self, column: str, desc: bool = False):
        """Add ordering."""
        direction = "DESC" if desc else "ASC"
        # Quote column name to handle case-sensitive identifiers (e.g., "Changed", "Bug ID")
        quoted_column = f'"{column}"' if not column.startswith('"') else column
        self._order_by = f"{quoted_column} {direction}"
        return self
    
    def limit(self, count: int):
        """Add limit."""
        self._limit = count
        return self
    
    def execute(self):
        """Execute the query, update, insert, or delete."""
        # Check if this is an insert operation
        if hasattr(self, '_insert_data'):
            return self._execute_insert()
        # Check if this is an update operation
        if hasattr(self, '_update_data'):
            return self._execute_update()
        # Check if this is a delete operation
        if hasattr(self, '_delete_mode'):
            return self._execute_delete()
        
        # Handle joins in select (e.g., "*, roles(*)")
        select_cols = self._select_cols
        if "(*)" in select_cols:
            # Simple join handling - for now, just select all from main table
            # TODO: Implement proper joins if needed
            select_cols = "*"
        
        # Build query
        query = f"SELECT {select_cols} FROM {self.table_name}"
        params = []
        conditions = []
        
        # Helper function to quote column names for PostgreSQL
        def quote_column(col: str) -> str:
            """Quote column name if it contains special characters or is case-sensitive."""
            if col.startswith('"') and col.endswith('"'):
                return col  # Already quoted
            # Quote if contains spaces, special chars, starts with capital, or contains %
            if ' ' in col or '-' in col or col[0].isupper() or '%' in col or '(' in col or ')' in col:
                return f'"{col}"'
            return col
        
        for key, value in self._filters.items():
            quoted_key = quote_column(key)
            if key == "is_deleted" and (value is False or value == "n" or str(value).lower() == "false"):
                conditions.append(f"({quoted_key} = %s OR {quoted_key} IS NULL)")
                params.append(serialize_param(value))
            else:
                conditions.append(f"{quoted_key} = %s")
                params.append(serialize_param(value))
        
        # Handle ILIKE filters
        if hasattr(self, '_ilike_filters') and self._ilike_filters:
            for col, pattern in self._ilike_filters.items():
                quoted_col = quote_column(col)
                conditions.append(f"{quoted_col} ILIKE %s")
                params.append(serialize_param(pattern))
        
        # Handle NEQ filters
        if hasattr(self, '_neq_filters') and self._neq_filters:
            for col, val in self._neq_filters.items():
                quoted_col = quote_column(col)
                conditions.append(f"{quoted_col} != %s")
                params.append(serialize_param(val))
        
        # Handle IN filters
        if hasattr(self, '_in_filters') and self._in_filters:
            for col, vals in self._in_filters.items():
                if not vals:
                    # If list is empty, condition is always false (1=0)
                    conditions.append("1=0")
                    continue
                quoted_col = quote_column(col)
                placeholders = ', '.join(['%s'] * len(vals))
                conditions.append(f"{quoted_col} IN ({placeholders})")
                params.extend([serialize_param(v) for v in vals])
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        if self._order_by:
            query += f" ORDER BY {self._order_by}"
        
        if self._limit:
            query += f" LIMIT {self._limit}"
        
        results = execute_query(query, tuple(params) if params else None, fetch_all=True) or []
        
        # Get count if count mode is enabled
        count_value = None
        if hasattr(self, '_count_mode') and self._count_mode:
            # Execute a COUNT query
            count_query = f"SELECT COUNT(*) as count FROM {self.table_name}"
            count_params = []
            count_conditions = []
            
            # Helper function to quote column names for PostgreSQL
            def quote_column(col: str) -> str:
                """Quote column name if it contains special characters or is case-sensitive."""
                if col.startswith('"') and col.endswith('"'):
                    return col  # Already quoted
                # Quote if it contains spaces, special chars, or starts with capital letter
                if ' ' in col or '-' in col or col[0].isupper():
                    return f'"{col}"'
                return col
            
            for key, value in self._filters.items():
                quoted_key = quote_column(key)
                if key == "is_deleted" and (value is False or value == "n" or str(value).lower() == "false"):
                    count_conditions.append(f"({quoted_key} = %s OR {quoted_key} IS NULL)")
                    count_params.append(serialize_param(value))
                else:
                    count_conditions.append(f"{quoted_key} = %s")
                    count_params.append(serialize_param(value))
            
            if hasattr(self, '_ilike_filters') and self._ilike_filters:
                for col, pattern in self._ilike_filters.items():
                    quoted_col = quote_column(col)
                    count_conditions.append(f"{quoted_col} ILIKE %s")
                    count_params.append(serialize_param(pattern))
            
            if hasattr(self, '_neq_filters') and self._neq_filters:
                for col, val in self._neq_filters.items():
                    quoted_col = quote_column(col)
                    count_conditions.append(f"{quoted_col} != %s")
                    count_params.append(serialize_param(val))
            
            if hasattr(self, '_in_filters') and self._in_filters:
                for col, vals in self._in_filters.items():
                    if not vals:
                        count_conditions.append("1=0")
                        continue
                    quoted_col = quote_column(col)
                    placeholders = ', '.join(['%s'] * len(vals))
                    count_conditions.append(f"{quoted_col} IN ({placeholders})")
                    count_params.extend([serialize_param(v) for v in vals])
            
            if count_conditions:
                count_query += " WHERE " + " AND ".join(count_conditions)
            
            try:
                count_result = execute_query(count_query, tuple(count_params) if count_params else None, fetch_one=True)
                if count_result:
                    count_value = count_result.get('count', len(results))
            except:
                count_value = len(results)
        
        # Reset state for next query
        self.reset()
        
        # Return object that mimics Supabase response
        class Response:
            def __init__(self, data, count=None):
                self.data = data
                self.error = None
                self.count = count
        
        return Response(results, count_value)
    
    def insert(self, data: Dict[str, Any] or List[Dict[str, Any]], returning: str = None):
        """Insert data. returning parameter is accepted for Supabase compatibility but always returns data."""
        # Store insert data and return self to allow chaining with .execute()
        self._insert_data = data
        self._returning = returning
        return self
    
    def _execute_insert(self):
        """Internal method to execute the insert."""
        try:
            data = self._insert_data
            if isinstance(data, list):
                # Insert multiple records
                results = []
                for item in data:
                    result = insert_table(self.table_name, item)
                    if result:
                        results.append(result)
                class Response:
                    def __init__(self, data):
                        self.data = data
                        self.error = None
                response = Response(results)
            else:
                result = insert_table(self.table_name, data)
                class Response:
                    def __init__(self, data):
                        self.data = [data] if data else []
                        self.error = None
                response = Response(result)
            self.reset()
            return response
        except Exception as e:
            self.reset()
            class Response:
                def __init__(self, data, error):
                    self.data = data
                    self.error = error
            return Response(None, str(e))
    
    def update(self, data: Dict[str, Any]):
        """Update data. Note: filters must be set BEFORE calling update(). Returns self for chaining."""
        # Store update data and return self to allow chaining
        # The actual update will happen in execute()
        self._update_data = data
        return self
    
    def _execute_update(self):
        """Internal method to execute the update."""
        try:
            # Update requires filters to be set
            if not self._filters:
                raise ValueError("Update requires filters (use .eq() before .update())")
            
            if not hasattr(self, '_update_data'):
                raise ValueError("Update data not set (call .update() first)")
            
            # Store filters and update data before reset
            filters = self._filters.copy()
            update_data = self._update_data
            self.reset()
            
            result = update_table(self.table_name, update_data, filters)
            class Response:
                def __init__(self, data):
                    self.data = [data] if data else []
                    self.error = None
            return Response(result)
        except Exception as e:
            self.reset()
            class Response:
                def __init__(self, data, error):
                    self.data = data
                    self.error = error
            return Response(None, str(e))
    
    def delete(self):
        """Delete data. Note: filters must be set BEFORE calling delete(). Returns self for chaining."""
        # Store delete intent and return self to allow chaining
        # The actual delete will happen in execute()
        self._delete_mode = True
        return self
    
    def _execute_delete(self):
        """Internal method to execute the delete."""
        try:
            # Delete requires filters to be set
            if not self._filters:
                raise ValueError("Delete requires filters (use .eq() before .delete())")
            
            # Store filters before reset
            filters = self._filters.copy()
            self.reset()
            
            success, rowcount = delete_table(self.table_name, filters)
            class Response:
                def __init__(self, data, error, rowcount=0):
                    self.data = data
                    self.error = error
                    self.rowcount = rowcount
            
            # Determine error message
            if not success:
                error_msg = "Delete operation failed"
            elif rowcount == 0:
                error_msg = f"Delete operation succeeded but no rows were deleted (0 rows affected)"
            else:
                error_msg = None
            
            return Response(None, error_msg, rowcount)
        except Exception as e:
            self.reset()
            class Response:
                def __init__(self, data, error, rowcount=0):
                    self.data = data
                    self.error = error
                    self.rowcount = rowcount
            return Response(None, str(e), 0)


# Compatibility class to mimic Supabase client
class LocalDBClient:
    """Local database client that mimics Supabase API."""
    
    def table(self, table_name: str):
        """Get a table proxy."""
        return TableProxy(table_name)
    
    def from_(self, table_name: str):
        """Alias for table()."""
        return self.table(table_name)


# Create a global instance
local_db = LocalDBClient()

