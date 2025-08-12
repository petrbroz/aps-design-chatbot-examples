"""
API Gateway for the AgentCore framework with backward compatibility.

This module provides a FastAPI-based gateway that maintains backward compatibility
with existing client applications while routing requests to the unified agent architecture.
"""

import os
import base64
import time
import uuid
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from .models import AgentRequest, AgentResponse, ErrorResponse, ErrorCode
from .auth import AuthContext, AuthenticationManager
from .orchestrator import StrandsOrchestrator


class PromptPayload(BaseModel):
    """Base payload model for prompt requests."""
    prompt: str = Field(..., description="The user prompt to process")


class ModelPropertiesPayload(PromptPayload):
    """Payload for Model Properties agent requests."""
    project_id: str = Field(..., description="The project ID")
    version_id: str = Field(..., description="The version ID")


class AECDataModelPayload(PromptPayload):
    """Payload for AEC Data Model agent requests."""
    element_group_id: str = Field(..., description="The element group ID")


class ModelDerivativesPayload(PromptPayload):
    """Payload for Model Derivatives agent requests."""
    urn: str = Field(..., description="The URN of the model")


class BackwardCompatibleResponse(BaseModel):
    """Backward compatible response format."""
    responses: list[str] = Field(..., description="List of response messages")


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """
    Authentication middleware for validating tokens and extracting auth context.
    
    This middleware validates OAuth tokens and adds authentication context
    to the request state for use by downstream handlers.
    """
    
    def __init__(self, app, auth_manager: AuthenticationManager, excluded_paths: Optional[List[str]] = None):
        """
        Initialize the authentication middleware.
        
        Args:
            app: The FastAPI application
            auth_manager: The authentication manager instance
            excluded_paths: List of paths to exclude from authentication
        """
        super().__init__(app)
        self.auth_manager = auth_manager
        self.excluded_paths = excluded_paths or ["/health", "/status", "/docs", "/redoc", "/openapi.json"]
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Process the request through authentication middleware.
        
        Args:
            request: The incoming request
            call_next: The next middleware/handler in the chain
            
        Returns:
            Response: The response from downstream handlers
        """
        # Skip authentication for excluded paths
        if request.url.path in self.excluded_paths:
            return await call_next(request)
        
        # Skip authentication if disabled
        if not self.auth_manager.enabled:
            return await call_next(request)
        
        try:
            # Extract and validate authentication
            auth_context = self.auth_manager.extract_auth_context(
                dict(request.headers),
                dict(request.query_params)
            )
            
            # Validate the token
            validated_auth = await self.auth_manager.validate_token(auth_context.access_token)
            
            # Add auth context to request state
            request.state.auth_context = validated_auth
            
            return await call_next(request)
            
        except ValueError as e:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": str(e)}
            )
        except Exception as e:
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": "Authentication error"}
            )


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Request logging middleware for monitoring and debugging.
    
    This middleware logs all incoming requests and responses with
    detailed information for monitoring and debugging purposes.
    """
    
    def __init__(self, app, logger, log_request_body: bool = False, log_response_body: bool = False):
        """
        Initialize the request logging middleware.
        
        Args:
            app: The FastAPI application
            logger: The logger instance to use
            log_request_body: Whether to log request bodies
            log_response_body: Whether to log response bodies
        """
        super().__init__(app)
        self.logger = logger
        self.log_request_body = log_request_body
        self.log_response_body = log_response_body
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Process the request through logging middleware.
        
        Args:
            request: The incoming request
            call_next: The next middleware/handler in the chain
            
        Returns:
            Response: The response from downstream handlers
        """
        start_time = time.time()
        request_id = getattr(request.state, 'request_id', str(uuid.uuid4()))
        
        # Log request details
        request_info = {
            "request_id": request_id,
            "method": request.method,
            "url": str(request.url),
            "path": request.url.path,
            "query_params": dict(request.query_params),
            "headers": dict(request.headers),
            "client_ip": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent")
        }
        
        # Optionally log request body
        if self.log_request_body and request.method in ["POST", "PUT", "PATCH"]:
            try:
                body = await request.body()
                if body:
                    request_info["body_size"] = len(body)
                    # Don't log the actual body content for security reasons
            except Exception:
                pass
        
        self.logger.info("Incoming request", **request_info)
        
        try:
            response = await call_next(request)
            
            execution_time = time.time() - start_time
            
            # Log response details
            response_info = {
                "request_id": request_id,
                "status_code": response.status_code,
                "execution_time": execution_time,
                "response_headers": dict(response.headers)
            }
            
            self.logger.info("Request completed", **response_info)
            
            return response
            
        except Exception as e:
            execution_time = time.time() - start_time
            
            self.logger.error(
                "Request failed",
                request_id=request_id,
                execution_time=execution_time,
                error=str(e),
                exception_type=type(e).__name__
            )
            raise


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Security headers middleware for adding security-related HTTP headers.
    
    This middleware adds various security headers to responses to improve
    the security posture of the application.
    """
    
    def __init__(self, app, custom_headers: Optional[Dict[str, str]] = None):
        """
        Initialize the security headers middleware.
        
        Args:
            app: The FastAPI application
            custom_headers: Optional custom headers to add
        """
        super().__init__(app)
        
        # Default security headers
        self.security_headers = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Content-Security-Policy": "default-src 'self'",
        }
        
        # Add custom headers if provided
        if custom_headers:
            self.security_headers.update(custom_headers)
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Process the request through security headers middleware.
        
        Args:
            request: The incoming request
            call_next: The next middleware/handler in the chain
            
        Returns:
            Response: The response with security headers added
        """
        response = await call_next(request)
        
        # Add security headers to response
        for header_name, header_value in self.security_headers.items():
            response.headers[header_name] = header_value
        
        return response


class APIGateway:
    """
    FastAPI-based API Gateway for the AgentCore framework.
    
    Provides backward-compatible endpoints for all three agent types while
    routing requests to the unified Strands orchestrator.
    """
    
    def __init__(self, strands: StrandsOrchestrator, static_dir: Optional[str] = None, 
                 cors_origins: Optional[List[str]] = None, trusted_hosts: Optional[List[str]] = None,
                 security_headers: Optional[Dict[str, str]] = None):
        """
        Initialize the API Gateway.
        
        Args:
            strands: The Strands orchestrator instance
            static_dir: Optional directory for static files
            cors_origins: Optional list of allowed CORS origins
            trusted_hosts: Optional list of trusted host patterns
            security_headers: Optional custom security headers
        """
        self.strands = strands
        self.agent_core = strands.agent_core
        self.auth_manager = self.agent_core.auth_manager
        self.static_dir = static_dir
        self.cors_origins = cors_origins or ["*"]
        self.trusted_hosts = trusted_hosts or ["*"]
        self.security_headers = security_headers
        
        # Create FastAPI app
        self.app = FastAPI(
            title="Autodesk Agents Unified API",
            description="Unified API for Autodesk Data Agents",
            version="1.0.0"
        )
        
        # Setup middleware and routes
        self._setup_middleware()
        self._setup_routes()
        self._setup_static_files()
        
        # Request tracking
        self._request_count = 0
        self._start_time = datetime.utcnow()
        
        # HTTP Bearer security scheme for OpenAPI docs
        self.security = HTTPBearer(auto_error=False)
    
    def _setup_middleware(self) -> None:
        """Setup FastAPI middleware in the correct order."""
        
        # 1. Trusted Host middleware (first for security)
        if self.trusted_hosts and self.trusted_hosts != ["*"]:
            self.app.add_middleware(
                TrustedHostMiddleware,
                allowed_hosts=self.trusted_hosts
            )
        
        # 2. Security headers middleware
        self.app.add_middleware(
            SecurityHeadersMiddleware,
            custom_headers=self.security_headers
        )
        
        # 3. CORS middleware
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=self.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            allow_headers=["*"],
            expose_headers=["X-Request-ID"]
        )
        
        # 4. Request logging middleware
        self.app.add_middleware(
            RequestLoggingMiddleware,
            logger=self.agent_core.logger,
            log_request_body=False,  # Don't log request bodies for security
            log_response_body=False  # Don't log response bodies for performance
        )
        
        # 5. Authentication middleware (last, so it has access to all request info)
        self.app.add_middleware(
            AuthenticationMiddleware,
            auth_manager=self.auth_manager,
            excluded_paths=["/health", "/status", "/docs", "/redoc", "/openapi.json", "/"]
        )
        
        # 6. Request ID middleware (simple middleware to ensure request ID is set)
        @self.app.middleware("http")
        async def request_id_middleware(request: Request, call_next):
            # Set request ID if not already set by logging middleware
            if not hasattr(request.state, 'request_id'):
                request.state.request_id = str(uuid.uuid4())
            
            response = await call_next(request)
            
            # Ensure request ID is in response headers
            if hasattr(request.state, 'request_id'):
                response.headers["X-Request-ID"] = request.state.request_id
            
            return response
    
    def _setup_routes(self) -> None:
        """Setup API routes."""
        
        # Health check endpoint for load balancers
        @self.app.get("/health")
        async def health_check():
            """Simple health check endpoint for load balancers."""
            try:
                health_data = self.agent_core.health_monitor.get_health_check_endpoint_data()
                
                if health_data["healthy"]:
                    return health_data
                else:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail=health_data
                    )
            except Exception as e:
                self.agent_core.logger.error(f"Health check failed: {e}")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Service unhealthy"
                )
        
        # Detailed health check endpoint
        @self.app.get("/health/detailed")
        async def detailed_health_check():
            """Detailed health check endpoint for monitoring systems."""
            try:
                return self.agent_core.health_monitor.get_detailed_health_check()
            except Exception as e:
                self.agent_core.logger.error(f"Detailed health check failed: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to get detailed health status"
                )
        
        # Metrics endpoint
        @self.app.get("/metrics")
        async def get_metrics():
            """Get system metrics and performance data."""
            try:
                system_metrics = self.agent_core.health_monitor.get_system_metrics()
                return {
                    "system_metrics": system_metrics.__dict__ if hasattr(system_metrics, '__dict__') else system_metrics,
                    "performance": self.agent_core.health_monitor.get_performance_summary(),
                    "health_summary": self.agent_core.health_monitor.get_health_summary()
                }
            except Exception as e:
                self.agent_core.logger.error(f"Metrics retrieval failed: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to get metrics"
                )
        
        # Status endpoint
        @self.app.get("/status")
        async def get_status():
            """Get comprehensive system status."""
            try:
                uptime = (datetime.utcnow() - self._start_time).total_seconds()
                orchestrator_status = await self.strands.get_orchestrator_status()
                
                return {
                    "gateway": {
                        "uptime_seconds": uptime,
                        "total_requests": self._request_count,
                        "start_time": self._start_time.isoformat()
                    },
                    "orchestrator": orchestrator_status
                }
            except Exception as e:
                self.agent_core.logger.error(f"Status check failed: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to get status"
                )
        
        # Model Properties agent endpoint (backward compatible)
        @self.app.post("/chatbot/prompt", response_model=BackwardCompatibleResponse)
        async def model_properties_prompt(
            payload: ModelPropertiesPayload,
            request: Request,
            access_token: str = Depends(self._check_access)
        ):
            """
            Model Properties agent endpoint (backward compatible).
            
            This endpoint maintains backward compatibility with the original
            ACC Model Properties Assistant API.
            """
            return await self._handle_agent_request(
                agent_type="model_properties",
                payload=payload,
                request=request,
                access_token=access_token,
                context={
                    "project_id": payload.project_id,
                    "version_id": payload.version_id,
                    "urn": self._generate_urn_from_version(payload.version_id)
                }
            )
        
        # AEC Data Model agent endpoint (backward compatible)
        @self.app.post("/aec/chatbot/prompt", response_model=BackwardCompatibleResponse)
        async def aec_data_model_prompt(
            payload: AECDataModelPayload,
            request: Request,
            access_token: str = Depends(self._check_access)
        ):
            """
            AEC Data Model agent endpoint (backward compatible).
            
            This endpoint maintains backward compatibility with the original
            AEC Data Model Assistant API.
            """
            return await self._handle_agent_request(
                agent_type="aec_data_model",
                payload=payload,
                request=request,
                access_token=access_token,
                context={
                    "element_group_id": payload.element_group_id
                }
            )
        
        # Model Derivatives agent endpoint (backward compatible)
        @self.app.post("/derivatives/chatbot/prompt", response_model=BackwardCompatibleResponse)
        async def model_derivatives_prompt(
            payload: ModelDerivativesPayload,
            request: Request,
            access_token: str = Depends(self._check_access)
        ):
            """
            Model Derivatives agent endpoint (backward compatible).
            
            This endpoint maintains backward compatibility with the original
            APS Model Derivatives Assistant API.
            """
            return await self._handle_agent_request(
                agent_type="model_derivatives",
                payload=payload,
                request=request,
                access_token=access_token,
                context={
                    "urn": payload.urn
                }
            )
        
        # Generic agent endpoint (new unified API)
        @self.app.post("/agents/{agent_type}/prompt")
        async def generic_agent_prompt(
            agent_type: str,
            payload: PromptPayload,
            request: Request,
            access_token: str = Depends(self._check_access)
        ):
            """
            Generic agent endpoint for the unified API.
            
            This endpoint provides a consistent interface for all agent types
            in the new unified architecture.
            """
            return await self._handle_agent_request(
                agent_type=agent_type,
                payload=payload,
                request=request,
                access_token=access_token
            )
    
    def _setup_static_files(self) -> None:
        """Setup static file serving if directory is provided."""
        if self.static_dir and os.path.exists(self.static_dir):
            self.app.mount("/", StaticFiles(directory=self.static_dir, html=True), name="static")
    
    def _check_access(self, request: Request) -> str:
        """
        Extract and validate access token from request.
        
        This method maintains backward compatibility with the original authentication pattern
        while leveraging the new authentication middleware when available.
        
        Args:
            request: The FastAPI request object
            
        Returns:
            str: The validated access token
            
        Raises:
            HTTPException: If authentication fails
        """
        # If authentication middleware has already validated the token, use that
        if hasattr(request.state, 'auth_context') and request.state.auth_context:
            return request.state.auth_context.access_token
        
        # Fallback to manual token extraction (backward compatibility)
        authorization = request.headers.get("authorization")
        if not authorization:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authorization header required"
            )
        
        if not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authorization header format"
            )
        
        return authorization[7:]  # Remove "Bearer " prefix
    
    def _get_auth_context(self, request: Request) -> Optional[AuthContext]:
        """
        Get authentication context from request state.
        
        Args:
            request: The FastAPI request object
            
        Returns:
            Optional[AuthContext]: The authentication context if available
        """
        return getattr(request.state, 'auth_context', None)
    
    def _generate_urn_from_version(self, version_id: str) -> str:
        """
        Generate URN from version ID (backward compatibility).
        
        Args:
            version_id: The version ID
            
        Returns:
            str: The generated URN
        """
        return base64.b64encode(version_id.encode()).decode().replace("/", "_").replace("=", "")
    
    async def _handle_agent_request(
        self,
        agent_type: str,
        payload: PromptPayload,
        request: Request,
        access_token: str,
        context: Optional[Dict[str, Any]] = None
    ) -> BackwardCompatibleResponse:
        """
        Handle agent request with unified processing.
        
        Args:
            agent_type: The type of agent to route to
            payload: The request payload
            request: The FastAPI request object
            access_token: The validated access token
            context: Optional additional context
            
        Returns:
            BackwardCompatibleResponse: The formatted response
            
        Raises:
            HTTPException: If request processing fails
        """
        self._request_count += 1
        request_id = getattr(request.state, 'request_id', str(uuid.uuid4()))
        start_time = time.time()
        
        try:
            # Get authentication context from middleware or create new one
            auth_context = self._get_auth_context(request)
            if not auth_context:
                auth_context = AuthContext(
                    access_token=access_token,
                    project_id=context.get("project_id") if context else None,
                    version_id=context.get("version_id") if context else None,
                    element_group_id=context.get("element_group_id") if context else None,
                    urn=context.get("urn") if context else None
                )
            else:
                # Update context with request-specific information
                if context:
                    if context.get("project_id"):
                        auth_context.project_id = context["project_id"]
                    if context.get("version_id"):
                        auth_context.version_id = context["version_id"]
                    if context.get("element_group_id"):
                        auth_context.element_group_id = context["element_group_id"]
                    if context.get("urn"):
                        auth_context.urn = context["urn"]
            
            # Create agent request
            agent_request = AgentRequest(
                agent_type=agent_type,
                prompt=payload.prompt,
                context=context or {},
                authentication=auth_context,
                request_id=request_id,
                metadata={
                    "client_ip": request.client.host if request.client else None,
                    "user_agent": request.headers.get("user-agent"),
                    "endpoint": request.url.path
                }
            )
            
            # Route request to orchestrator
            response = await self.strands.route_request(agent_request)
            
            # Record response time for monitoring
            duration_ms = (time.time() - start_time) * 1000
            self.agent_core.health_monitor.record_response_time(duration_ms, "agent", agent_type)
            
            # Transform response to backward compatible format
            if response.success:
                return BackwardCompatibleResponse(responses=response.responses)
            else:
                # Extract error details from metadata
                error_details = response.metadata.get("error", {})
                error_message = error_details.get("message", "Request processing failed")
                
                self.agent_core.logger.error(
                    f"Agent request failed: {error_message}",
                    request_id=request_id,
                    agent_type=agent_type,
                    error_details=error_details
                )
                
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=error_message
                )
        
        except HTTPException:
            # Re-raise HTTP exceptions as-is
            raise
        
        except Exception as e:
            # Record failed request response time
            duration_ms = (time.time() - start_time) * 1000
            self.agent_core.health_monitor.record_response_time(duration_ms, "agent", agent_type)
            
            self.agent_core.logger.error(
                f"Unexpected error processing request: {str(e)}",
                request_id=request_id,
                agent_type=agent_type,
                error=str(e)
            )
            
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error"
            )
    
    async def startup(self) -> None:
        """Startup tasks for the API Gateway."""
        self.agent_core.logger.info("Starting API Gateway")
        
        # Ensure orchestrator is initialized
        if not self.strands._initialized:
            await self.strands.initialize()
        
        self.agent_core.logger.info("API Gateway started successfully")
    
    async def shutdown(self) -> None:
        """Shutdown tasks for the API Gateway."""
        self.agent_core.logger.info("Shutting down API Gateway")
        
        # Shutdown orchestrator if needed
        if self.strands._initialized:
            await self.strands.shutdown()
        
        self.agent_core.logger.info("API Gateway shutdown completed")
    
    def get_app(self) -> FastAPI:
        """Get the FastAPI application instance."""
        return self.app
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get API Gateway metrics."""
        uptime = (datetime.utcnow() - self._start_time).total_seconds()
        
        return {
            "uptime_seconds": uptime,
            "total_requests": self._request_count,
            "start_time": self._start_time.isoformat(),
            "registered_agents": self.strands.get_registered_agents()
        }