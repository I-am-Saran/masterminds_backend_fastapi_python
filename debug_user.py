
import asyncio
from services.db_service import local_db as supabase
from services.rbac_service import get_user_roles

async def check_user():
    email = "superadmin@cavininfotech.com"
    print(f"Checking user: {email}")
    
    # Get User
    resp = supabase.table("users").select("*").eq("email", email).execute()
    users = resp.data or []
    
    if not users:
        print("User not found!")
        return

    user = users[0]
    print(f"User Found: ID={user.get('id')}, Tenant={user.get('tenant_id')}, Role (in users table)={user.get('role')}")
    
    # Get Roles assigned
    user_id = user.get('id')
    tenant_id = user.get('tenant_id')
    
    # Check user_roles table directly
    ur_resp = supabase.table("user_roles").select("*, roles(*)").eq("user_id", user_id).execute()
    user_roles = ur_resp.data or []
    
    print("\nAssigned Roles (user_roles table):")
    for ur in user_roles:
        role = ur.get('roles')
        role_name = role.get('role_name') if role else "Unknown"
        print(f" - Role ID: {ur.get('role_id')}, Role Name: {role_name}, Tenant: {ur.get('tenant_id')}")

    # Check using service
    print("\nRoles via rbac_service.get_user_roles:")
    service_roles = get_user_roles(user_id, tenant_id)
    print(service_roles)

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    loop.run_until_complete(check_user())
