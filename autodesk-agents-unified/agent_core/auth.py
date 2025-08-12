"""
Authentication management for AgentCore framework.
"""

import jwt
from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime, timezone


@dataclass
class AuthContext:
    """Authentication context for agent requests."""
    access_token: str
    project_id: Optional[str] = None
    version_id: Optional[str] = None
    element_group_id: Optional[str] = None
    urn: Optional[str] = None
    user_id: Optional[str] = None
    expires_at: Optional[datetime] = None


class AuthenticationManager:
    """Manages authentication and authorization for agents."""
    
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._token_cache: Dict[str, AuthContext] = {}
    
    async def validate_token(self, token: str) -> AuthContext:
        """Validate an access token and return auth context."""
        if not self.enabled:
            # Return a mock auth context when auth is disabled
            return AuthContext(access_token=token)
        
        # Check cache first
        if token in self._token_cache:
            auth_context = self._token_cache[token]
            if auth_context.expires_at and auth_context.expires_at > datetime.now(timezone.utc):
                return auth_context
        
        # Validate token (simplified - in production would validate with OAuth provider)
        try:
            # For now, just decode without verification for development
            # In production, this would validate signature and expiration
            decoded = jwt.decode(token, options={"verify_signature": False})
            
            auth_context = AuthContext(
                access_token=token,
                user_id=decoded.get('sub'),
                expires_at=datetime.fromtimestamp(decoded.get('exp', 0), timezone.utc) if decoded.get('exp') else None
            )
            
            # Cache the validated token
            self._token_cache[token] = auth_context
            return auth_context
            
        except jwt.InvalidTokenError as e:
            raise ValueError(f"Invalid access token: {e}")
    
    def extract_auth_context(self, headers: Dict[str, str], query_params: Dict[str, Any]) -> AuthContext:
        """Extract authentication context from request headers and parameters."""
        # Extract token from Authorization header
        auth_header = headers.get('authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]
        else:
            token = query_params.get('access_token', '')
        
        if not token:
            raise ValueError("No access token provided")
        
        # Create auth context with additional parameters
        auth_context = AuthContext(
            access_token=token,
            project_id=query_params.get('project_id'),
            version_id=query_params.get('version_id'), 
            element_group_id=query_params.get('element_group_id'),
            urn=query_params.get('urn')
        )
        
        return auth_context
    
    def is_authorized(self, auth_context: AuthContext, required_permissions: list = None) -> bool:
        """Check if the auth context has required permissions."""
        if not self.enabled:
            return True
        
        # Basic authorization check - in production would check against permission system
        if not auth_context.access_token:
            return False
        
        # For now, just check that token exists
        # In production, would validate specific permissions
        return True
    
    def clear_token_cache(self) -> None:
        """Clear the token cache."""
        self._token_cache.clear()