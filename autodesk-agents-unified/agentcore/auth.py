"""
Authentication Manager for Autodesk Platform Services

Handles OAuth token management, validation, and refresh for
real Autodesk API integration.
"""

import asyncio
import time
from typing import Optional, Dict, Any
from dataclasses import dataclass
import aiohttp
import jwt
from datetime import datetime, timedelta


@dataclass
class AuthContext:
    """Authentication context for API requests."""
    access_token: str
    token_type: str = "Bearer"
    expires_at: Optional[float] = None
    project_id: Optional[str] = None
    version_id: Optional[str] = None
    element_group_id: Optional[str] = None
    urn: Optional[str] = None
    
    def is_expired(self) -> bool:
        """Check if token is expired."""
        if not self.expires_at:
            return False
        return time.time() >= self.expires_at
    
    def to_headers(self) -> Dict[str, str]:
        """Convert to HTTP headers."""
        return {
            "Authorization": f"{self.token_type} {self.access_token}",
            "Content-Type": "application/json"
        }


class AuthenticationManager:
    """
    Manages authentication with Autodesk Platform Services.
    
    Handles client credentials flow, token caching, and automatic refresh.
    """
    
    def __init__(self, client_id: str, client_secret: str, logger=None):
        """Initialize authentication manager."""
        self.client_id = client_id
        self.client_secret = client_secret
        self.logger = logger
        
        # Token cache
        self._token_cache: Dict[str, AuthContext] = {}
        self._client_token: Optional[AuthContext] = None
        
        # Autodesk API endpoints
        self.auth_url = "https://developer.api.autodesk.com/authentication/v2/token"
        self.base_url = "https://developer.api.autodesk.com"
    
    async def get_client_token(self, scopes: str = "data:read") -> AuthContext:
        """
        Get client credentials token for API access.
        
        Args:
            scopes: OAuth scopes to request
            
        Returns:
            AuthContext with valid token
        """
        cache_key = f"client_{scopes}"
        
        # Check cache first
        if cache_key in self._token_cache:
            token = self._token_cache[cache_key]
            if not token.is_expired():
                return token
        
        # Request new token
        token = await self._request_client_token(scopes)
        self._token_cache[cache_key] = token
        
        if self.logger:
            self.logger.info("Client token obtained", extra={
                "scopes": scopes,
                "expires_at": token.expires_at
            })
        
        return token
    
    async def _request_client_token(self, scopes: str) -> AuthContext:
        """Request new client credentials token."""
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials",
            "scope": scopes
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(self.auth_url, data=data) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise ValueError(f"Authentication failed: {response.status} - {error_text}")
                
                token_data = await response.json()
        
        # Calculate expiration time (subtract 5 minutes for safety)
        expires_in = token_data.get("expires_in", 3600)
        expires_at = time.time() + expires_in - 300
        
        return AuthContext(
            access_token=token_data["access_token"],
            token_type=token_data.get("token_type", "Bearer"),
            expires_at=expires_at
        )
    
    async def validate_token(self, token: str) -> bool:
        """
        Validate an access token.
        
        Args:
            token: Access token to validate
            
        Returns:
            True if token is valid
        """
        try:
            # Try to decode without verification first to check structure
            decoded = jwt.decode(token, options={"verify_signature": False})
            
            # Check expiration
            exp = decoded.get("exp")
            if exp and time.time() >= exp:
                return False
            
            # For full validation, we'd need to verify signature with Autodesk's public key
            # For now, we'll do a simple API call to verify the token works
            return await self._verify_token_with_api(token)
            
        except jwt.InvalidTokenError:
            return False
    
    async def _verify_token_with_api(self, token: str) -> bool:
        """Verify token by making a test API call."""
        headers = {"Authorization": f"Bearer {token}"}
        
        try:
            async with aiohttp.ClientSession() as session:
                # Test with a simple API call
                async with session.get(
                    f"{self.base_url}/project/v1/hubs",
                    headers=headers
                ) as response:
                    return response.status in [200, 403]  # 403 means token is valid but no access
        except:
            return False
    
    async def refresh_token_if_needed(self, auth_context: AuthContext) -> AuthContext:
        """Refresh token if it's expired or about to expire."""
        if not auth_context.is_expired():
            return auth_context
        
        # For client credentials, we need to get a new token
        return await self.get_client_token()
    
    async def health_check(self) -> Dict[str, Any]:
        """Health check for authentication service."""
        try:
            # Try to get a client token
            token = await self.get_client_token("data:read")
            
            return {
                "status": "healthy",
                "token_cached": bool(self._token_cache),
                "token_expires_at": token.expires_at,
                "time_to_expiry": token.expires_at - time.time() if token.expires_at else None
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "error_type": type(e).__name__
            }
    
    def clear_cache(self) -> None:
        """Clear token cache."""
        self._token_cache.clear()
        self._client_token = None
        
        if self.logger:
            self.logger.info("Authentication cache cleared")