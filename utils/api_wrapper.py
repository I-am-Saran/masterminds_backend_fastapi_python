"""
API Wrapper Utility
Simplifies error handling in API endpoints
"""

from functools import wraps
from typing import Callable, Any, Optional
from fastapi import HTTPException
from utils.error_handler import handle_api_error


def with_error_handling(
    endpoint_path: str,
    operation: Optional[str] = None,
    return_error_dict: bool = False,
    **default_context
):
    """
    Decorator to wrap API endpoints with comprehensive error handling.
    
    Args:
        endpoint_path: The API endpoint path (e.g., "/api/users")
        operation: Optional operation name for logging
        return_error_dict: If True, returns error dict instead of raising HTTPException
        **default_context: Additional context to include in error logs
    
    Usage:
        @with_error_handling("/api/users", "get_users", table="users")
        async def get_users():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            op_name = operation or func.__name__
            endpoint = endpoint_path or f"/api/{op_name}"
            
            try:
                return await func(*args, **kwargs)
            except HTTPException:
                # Re-raise HTTP exceptions as-is
                raise
            except Exception as e:
                # Build context from function arguments and default context
                context = {
                    "operation": op_name,
                    "function": func.__name__,
                    **default_context
                }
                
                # Add relevant kwargs to context (excluding sensitive data)
                safe_kwargs = {k: v for k, v in kwargs.items() 
                             if k not in ['password', 'token', 'authorization', 'Authorization']}
                if safe_kwargs:
                    context["parameters"] = safe_kwargs
                
                # Handle and format error
                error_response, status_code = handle_api_error(
                    e,
                    endpoint,
                    context,
                    include_traceback=False,
                    user_message=f"Error in {op_name}: {str(e)}"
                )
                
                if return_error_dict:
                    # Return error dict (for endpoints that return {"data": ..., "error": ...})
                    return error_response
                else:
                    # Raise HTTPException (for standard endpoints)
                    raise HTTPException(status_code=status_code, detail=error_response["error"])
        
        return wrapper
    return decorator

