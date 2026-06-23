# Error Handling Guide

All API endpoints should use the comprehensive error handling utility for detailed error logging and responses.

## Usage Pattern

### For endpoints that return `{"data": ..., "error": ...}` format:

```python
@app.get("/api/endpoint")
async def my_endpoint(...):
    endpoint = "/api/endpoint"
    try:
        # Your code here
        return {"data": result, "error": None}
    except HTTPException:
        raise
    except Exception as e:
        return handle_endpoint_error(e, endpoint, "operation_name", return_dict=True, **context)
```

### For endpoints that raise HTTPException:

```python
@app.post("/api/endpoint")
async def my_endpoint(...):
    endpoint = "/api/endpoint"
    try:
        # Your code here
        return result
    except HTTPException:
        raise
    except Exception as e:
        error_response, status_code = handle_api_error(
            e,
            endpoint,
            context={"operation": "operation_name", **additional_context},
            include_traceback=False,
            user_message="User-friendly error message"
        )
        raise HTTPException(status_code=status_code, detail=error_response["error"])
```

## Error Response Format

All errors return a structured format:

```json
{
  "data": null,
  "error": {
    "message": "User-friendly error message",
    "type": "ExceptionType",
    "category": "error_category",
    "timestamp": "2024-01-01T00:00:00",
    "context": {
      "operation": "operation_name",
      "additional": "context"
    }
  }
}
```

## Console Logging

All errors are automatically logged to:
- Console (stdout) with detailed information
- Log file: `backend/server.log`

The log includes:
- Timestamp
- Error type and message
- Endpoint path
- Context information
- Traceback (last 5 frames in console, full in log file)

## Functions Available

1. `handle_endpoint_error()` - Simple inline handler
2. `handle_api_error()` - Comprehensive handler with full control
3. `log_error()` - Log error without formatting response
4. `format_error_response()` - Format response without logging

