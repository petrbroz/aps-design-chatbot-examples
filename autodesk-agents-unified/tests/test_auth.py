"""
Unit tests for authentication management.
"""

import pytest
import jwt
from datetime import datetime, timezone, timedelta
from agent_core.auth import AuthenticationManager, AuthContext


class TestAuthenticationManager:
    """Test authentication management functionality."""
    
    def test_auth_manager_initialization(self):
        """Test authentication manager initialization."""
        auth_manager = AuthenticationManager(enabled=True)
        assert auth_manager.enabled is True
        
        auth_manager_disabled = AuthenticationManager(enabled=False)
        assert auth_manager_disabled.enabled is False
    
    @pytest.mark.asyncio
    async def test_validate_token_disabled_auth(self):
        """Test token validation when auth is disabled."""
        auth_manager = AuthenticationManager(enabled=False)
        
        auth_context = await auth_manager.validate_token("dummy_token")
        
        assert auth_context.access_token == "dummy_token"
        assert auth_context.user_id is None
    
    @pytest.mark.asyncio
    async def test_validate_token_enabled_auth(self):
        """Test token validation when auth is enabled."""
        auth_manager = AuthenticationManager(enabled=True)
        
        # Create a mock JWT token
        payload = {
            'sub': 'user123',
            'exp': int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())
        }
        token = jwt.encode(payload, 'secret', algorithm='HS256')
        
        auth_context = await auth_manager.validate_token(token)
        
        assert auth_context.access_token == token
        assert auth_context.user_id == 'user123'
        assert auth_context.expires_at is not None
    
    @pytest.mark.asyncio
    async def test_validate_invalid_token(self):
        """Test validation of invalid token."""
        auth_manager = AuthenticationManager(enabled=True)
        
        with pytest.raises(ValueError, match="Invalid access token"):
            await auth_manager.validate_token("invalid_token")
    
    def test_extract_auth_context_from_headers(self):
        """Test extracting auth context from request headers."""
        auth_manager = AuthenticationManager()
        
        headers = {'authorization': 'Bearer test_token'}
        query_params = {
            'project_id': 'proj123',
            'version_id': 'ver456',
            'urn': 'urn:test'
        }
        
        auth_context = auth_manager.extract_auth_context(headers, query_params)
        
        assert auth_context.access_token == 'test_token'
        assert auth_context.project_id == 'proj123'
        assert auth_context.version_id == 'ver456'
        assert auth_context.urn == 'urn:test'
    
    def test_extract_auth_context_from_query_params(self):
        """Test extracting auth context from query parameters."""
        auth_manager = AuthenticationManager()
        
        headers = {}
        query_params = {
            'access_token': 'query_token',
            'element_group_id': 'group789'
        }
        
        auth_context = auth_manager.extract_auth_context(headers, query_params)
        
        assert auth_context.access_token == 'query_token'
        assert auth_context.element_group_id == 'group789'
    
    def test_extract_auth_context_no_token(self):
        """Test extracting auth context when no token is provided."""
        auth_manager = AuthenticationManager()
        
        headers = {}
        query_params = {}
        
        with pytest.raises(ValueError, match="No access token provided"):
            auth_manager.extract_auth_context(headers, query_params)
    
    def test_is_authorized_disabled_auth(self):
        """Test authorization check when auth is disabled."""
        auth_manager = AuthenticationManager(enabled=False)
        auth_context = AuthContext(access_token="test_token")
        
        assert auth_manager.is_authorized(auth_context) is True
    
    def test_is_authorized_enabled_auth(self):
        """Test authorization check when auth is enabled."""
        auth_manager = AuthenticationManager(enabled=True)
        
        # Test with valid token
        auth_context = AuthContext(access_token="valid_token")
        assert auth_manager.is_authorized(auth_context) is True
        
        # Test with no token
        auth_context_no_token = AuthContext(access_token="")
        assert auth_manager.is_authorized(auth_context_no_token) is False
    
    @pytest.mark.asyncio
    async def test_token_caching(self):
        """Test token caching functionality."""
        auth_manager = AuthenticationManager(enabled=True)
        
        # Create a mock JWT token
        payload = {
            'sub': 'user123',
            'exp': int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())
        }
        token = jwt.encode(payload, 'secret', algorithm='HS256')
        
        # First validation should cache the token
        auth_context1 = await auth_manager.validate_token(token)
        
        # Second validation should use cached result
        auth_context2 = await auth_manager.validate_token(token)
        
        assert auth_context1.user_id == auth_context2.user_id
        assert token in auth_manager._token_cache
    
    def test_clear_token_cache(self):
        """Test clearing token cache."""
        auth_manager = AuthenticationManager()
        
        # Add something to cache
        auth_manager._token_cache['test_token'] = AuthContext(access_token='test_token')
        
        assert len(auth_manager._token_cache) == 1
        
        auth_manager.clear_token_cache()
        
        assert len(auth_manager._token_cache) == 0