from fastapi import Header, HTTPException, Query, status


def get_current_owner(
    x_api_key: str = Header(default=None),
    api_key: str = Query(default=None)
) -> str:
    """
    API-key based authentication.
    
    For this portfolio demo, any non-empty key (min 16 chars) maps to itself as the owner namespace.
    This provides per-key data isolation without requiring a users table.
    
    In a production system, this would be replaced with proper OAuth/JWT authentication
    and a real users table, but the rest of the code wouldn't need to change.
    
    Note: The query parameter fallback is needed for EventSource, which doesn't support custom headers.
    """
    key = x_api_key or api_key
    if not key or len(key) < 16:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid API key. API key must be at least 16 characters."
        )
    return key
