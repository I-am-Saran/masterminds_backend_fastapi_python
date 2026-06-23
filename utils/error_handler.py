"""
Error Handler Utility
Provides detailed error logging and formatted error responses for API endpoints
"""

import traceback
import sys
import logging
import os
from typing import Dict, Any, Optional
from fastapi import HTTPException
from datetime import datetime

# Get the backend directory path (where this file is located: backend/utils/error_handler.py)
# So backend directory is the parent of utils
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(BACKEND_DIR, 'logs')
LOG_FILE = os.path.join(LOG_DIR, 'server.log')

os.makedirs(LOG_DIR, exist_ok=True)

# File logging only in production (or LOG_TO_FILE=1). Writing logs under the
# project tree during dev triggers uvicorn reload loops.
_environment = os.getenv('ENVIRONMENT', 'development').lower()
_log_to_file = os.getenv('LOG_TO_FILE', '').lower() in ('1', 'true', 'yes')
_handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
if _environment == 'production' or _log_to_file:
    _handlers.append(logging.FileHandler(LOG_FILE, encoding='utf-8'))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=_handlers,
    force=True,
)

logger = logging.getLogger(__name__)


def get_detailed_error_info(exception: Exception, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Extract detailed error information from an exception.
    
    Args:
        exception: The exception object
        context: Optional context dictionary with additional information
    
    Returns:
        Dictionary with detailed error information
    """
    exc_type, exc_value, exc_traceback = sys.exc_info()
    
    # Get full traceback
    tb_lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
    full_traceback = ''.join(tb_lines)
    
    # Get simplified traceback (last few frames)
    simplified_tb = traceback.format_tb(exc_traceback)
    last_frames = simplified_tb[-5:] if len(simplified_tb) > 5 else simplified_tb
    
    error_info = {
        "error_type": type(exception).__name__,
        "error_message": str(exception),
        "error_module": getattr(exception, '__module__', 'unknown'),
        "traceback": {
            "full": full_traceback,
            "last_frames": ''.join(last_frames),
        },
        "timestamp": datetime.utcnow().isoformat(),
    }
    
    # Add context if provided
    if context:
        error_info["context"] = context
    
    # Add specific error details based on exception type
    if isinstance(exception, HTTPException):
        error_info["http_status"] = exception.status_code
        error_info["http_detail"] = exception.detail
    elif isinstance(exception, ValueError):
        error_info["error_category"] = "validation_error"
    elif isinstance(exception, KeyError):
        error_info["error_category"] = "missing_key"
        error_info["missing_key"] = str(exception)
    elif isinstance(exception, AttributeError):
        error_info["error_category"] = "attribute_error"
        error_info["attribute"] = str(exception)
    elif isinstance(exception, TypeError):
        error_info["error_category"] = "type_error"
    else:
        error_info["error_category"] = "general_error"
    
    return error_info


def log_error(exception: Exception, context: Optional[Dict[str, Any]] = None, endpoint: Optional[str] = None):
    """
    Log detailed error information to console and log file.
    
    Args:
        exception: The exception object
        context: Optional context dictionary
        endpoint: Optional API endpoint path
    """
    error_info = get_detailed_error_info(exception, context)
    
    # Build log message
    log_parts = [
        f"\n{'='*80}",
        f"ERROR OCCURRED",
        f"{'='*80}",
        f"Timestamp: {error_info['timestamp']}",
        f"Error Type: {error_info['error_type']}",
        f"Error Message: {error_info['error_message']}",
    ]
    
    if endpoint:
        log_parts.append(f"Endpoint: {endpoint}")
    
    if context:
        log_parts.append(f"Context: {context}")
    
    log_parts.extend([
        f"\nTraceback (last 5 frames):",
        f"{error_info['traceback']['last_frames']}",
        f"{'='*80}\n"
    ])
    
    log_message = '\n'.join(log_parts)
    
    # Log to console
    logger.error(log_message)
    print(log_message)  # Also print to stdout for immediate visibility
    
    # Log full traceback to file
    logger.debug(f"Full traceback:\n{error_info['traceback']['full']}")


def format_error_response(
    exception: Exception,
    context: Optional[Dict[str, Any]] = None,
    include_traceback: bool = False,
    user_message: Optional[str] = None
) -> Dict[str, Any]:
    """
    Format a detailed error response for API endpoints.
    
    Args:
        exception: The exception object
        context: Optional context dictionary
        include_traceback: Whether to include traceback in response (default: False for security)
        user_message: Optional user-friendly error message
    
    Returns:
        Dictionary with error response structure
    """
    error_info = get_detailed_error_info(exception, context)
    
    # Determine HTTP status code
    if isinstance(exception, HTTPException):
        status_code = exception.status_code
        detail = exception.detail
    else:
        status_code = 500
        detail = user_message or "An internal server error occurred"
    
    response = {
        "data": None,
        "error": {
            "message": detail,
            "type": error_info["error_type"],
            "category": error_info.get("error_category", "general_error"),
            "timestamp": error_info["timestamp"],
        }
    }
    
    # Add context if provided
    if context:
        response["error"]["context"] = context
    
    # Include traceback only if explicitly requested (for development)
    if include_traceback:
        response["error"]["traceback"] = error_info["traceback"]["last_frames"]
        response["error"]["full_traceback"] = error_info["traceback"]["full"]
    
    return response, status_code


def handle_api_error(
    exception: Exception,
    endpoint: str,
    context: Optional[Dict[str, Any]] = None,
    include_traceback: bool = False,
    user_message: Optional[str] = None
) -> Dict[str, Any]:
    """
    Comprehensive error handler for API endpoints.
    Logs the error and returns a formatted response.
    
    Args:
        exception: The exception object
        endpoint: API endpoint path
        context: Optional context dictionary
        include_traceback: Whether to include traceback in response
        user_message: Optional user-friendly error message
    
    Returns:
        Dictionary with error response structure
    """
    # Log the error
    log_error(exception, context, endpoint)
    
    # Format and return error response
    response, status_code = format_error_response(
        exception,
        context,
        include_traceback,
        user_message
    )
    
    return response, status_code


def safe_api_call(func):
    """
    Decorator to wrap API endpoint functions with comprehensive error handling.
    
    Usage:
        @safe_api_call
        async def my_endpoint(...):
            ...
    """
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except HTTPException:
            # Re-raise HTTP exceptions as-is
            raise
        except Exception as e:
            # Get endpoint name from function
            endpoint = f"{func.__module__}.{func.__name__}"
            
            # Build context
            context = {
                "function": func.__name__,
                "args_count": len(args),
                "kwargs_keys": list(kwargs.keys()) if kwargs else [],
            }
            
            # Handle and format error
            response, status_code = handle_api_error(
                e,
                endpoint,
                context,
                include_traceback=False,  # Don't expose traceback in production
                user_message=f"Error in {func.__name__}: {str(e)}"
            )
            
            # Return error response
            from fastapi import HTTPException
            raise HTTPException(status_code=status_code, detail=response["error"])
    
    return wrapper


def api_error_handler(endpoint_path: str, operation: str = None, **context_kwargs):
    """
    Context manager for handling errors in API endpoints.
    
    Usage:
        with api_error_handler("/api/users", "get_users", user_id=user_id):
            # your code here
            return result
    
    Or use as a wrapper:
        @api_error_handler("/api/users", "get_users")
        async def get_users():
            ...
    """
    class APIErrorHandler:
        def __init__(self, endpoint, operation, **ctx):
            self.endpoint = endpoint
            self.operation = operation or "unknown_operation"
            self.context = ctx
            self.exception = None
        
        def __enter__(self):
            return self
        
        def __exit__(self, exc_type, exc_value, traceback):
            if exc_type is not None and exc_type != HTTPException:
                self.exception = exc_value
                context = {
                    "operation": self.operation,
                    **self.context
                }
                error_response, status_code = handle_api_error(
                    exc_value,
                    self.endpoint,
                    context,
                    include_traceback=False,
                    user_message=f"Error in {self.operation}: {str(exc_value)}"
                )
                # Re-raise as HTTPException
                raise HTTPException(status_code=status_code, detail=error_response["error"])
            return False  # Don't suppress exceptions
    
    return APIErrorHandler(endpoint_path, operation, **context_kwargs)


def handle_endpoint_error(
    exception: Exception,
    endpoint: str,
    operation: str = None,
    return_dict: bool = False,
    **context
) -> Any:
    """
    Simple inline error handler for API endpoints.
    
    Args:
        exception: The exception object
        endpoint: API endpoint path
        operation: Operation name
        return_dict: If True, returns error dict; if False, raises HTTPException
        **context: Additional context for logging
    
    Returns:
        Error dict if return_dict=True, otherwise raises HTTPException
    
    Usage:
        try:
            # your code
        except Exception as e:
            return handle_endpoint_error(e, "/api/users", "get_users", return_dict=True, user_id=user_id)
    """
    op_name = operation or "unknown_operation"
    ctx = {"operation": op_name, **context}
    
    error_response, status_code = handle_api_error(
        exception,
        endpoint,
        ctx,
        include_traceback=False,
        user_message=f"Error in {op_name}: {str(exception)}"
    )
    
    if return_dict:
        return error_response
    else:
        raise HTTPException(status_code=status_code, detail=error_response["error"])

