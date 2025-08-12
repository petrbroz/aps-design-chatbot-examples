# Comprehensive Error Handling

The AgentCore framework provides a comprehensive error handling system that includes centralized error management, retry mechanisms, circuit breakers, and error reporting capabilities.

## Features

### 1. Centralized Error Management

The `ErrorHandler` class provides centralized error handling across all agents and tools:

```python
from agent_core.error_handler import ErrorHandler
from agent_core.logging import StructuredLogger

logger = StructuredLogger("my_service")
error_handler = ErrorHandler(logger)
```

### 2. Retry Mechanisms

Configure retry policies with different strategies:

```python
from agent_core.error_handler import RetryPolicy, RetryStrategy

# Exponential backoff
policy = RetryPolicy(
    max_retries=3,
    strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
    base_delay=1.0,
    backoff_factor=2.0,
    max_delay=60.0,
    retry_exceptions=[ConnectionError, TimeoutError]
)

error_handler.set_retry_policy("my_operation", policy)

# Execute with retry
result = await error_handler.execute_with_retry(
    "my_operation",
    my_function,
    arg1, arg2
)
```

#### Retry Strategies

- **Exponential Backoff**: Delay increases exponentially (1s, 2s, 4s, 8s...)
- **Linear Backoff**: Delay increases linearly (1s, 2s, 3s, 4s...)
- **Fixed Delay**: Constant delay between retries
- **Immediate**: No delay between retries

### 3. Circuit Breakers

Prevent cascading failures with circuit breakers:

```python
error_handler.set_circuit_breaker(
    "external_service",
    failure_threshold=5,      # Open after 5 failures
    recovery_timeout=60,      # Try to close after 60 seconds
    half_open_max_calls=3     # Allow 3 calls in half-open state
)
```

#### Circuit Breaker States

- **Closed**: Normal operation, all calls allowed
- **Open**: Circuit is open, calls are blocked
- **Half-Open**: Limited calls allowed to test recovery

### 4. Error Alerting

Set up alerts for error thresholds:

```python
from agent_core.error_handler import AlertSeverity

# Configure alert thresholds
error_handler.set_alert_threshold(
    "ConnectionError",
    threshold=10,
    time_window_minutes=5,
    severity=AlertSeverity.HIGH
)

# Register alert callback
def alert_handler(alert):
    print(f"Alert: {alert.message}")
    # Send to monitoring system, email, etc.

error_handler.register_alert_callback(alert_handler)
```

### 5. Error Metrics and Reporting

Get comprehensive error statistics:

```python
stats = error_handler.get_error_statistics()
print(f"Total errors: {stats['total_errors']}")
print(f"Error rate: {stats['error_rate_per_minute']}/min")
print(f"Successful recoveries: {stats['successful_recoveries']}")

# Get recent error history
recent_errors = error_handler.get_recent_errors(limit=10)
```

## Usage Examples

### Basic Error Handling

```python
async def handle_agent_request(request):
    try:
        # Process request
        result = await process_request(request)
        return result
    except Exception as e:
        # Handle with error handler
        error_response = await error_handler.handle_agent_error(e, request)
        return error_response
```

### Tool Error Handling

```python
async def execute_tool(tool_name, params):
    try:
        result = await tool.execute(params)
        return result
    except Exception as e:
        error_response = await error_handler.handle_tool_error(
            e, tool_name, {"params": params}
        )
        raise ToolExecutionError(error_response.message)
```

### Custom Error Handlers

Register custom handlers for specific exception types:

```python
def handle_api_error(error, context):
    if "rate limit" in str(error).lower():
        return ErrorResponse(
            error_code="RATE_LIMIT_EXCEEDED",
            message="API rate limit exceeded, please try again later",
            details={"retry_after": 60}
        )
    return None

error_handler.register_error_handler(APIError, handle_api_error)
```

### Validation Error Handling

```python
try:
    validate_input(user_input)
except ValidationError as e:
    error_response = await error_handler.handle_validation_error(
        e, field_name="user_input", value=user_input
    )
    return error_response
```

### Authentication Error Handling

```python
try:
    authenticate_user(token)
except AuthenticationError as e:
    error_response = await error_handler.handle_authentication_error(
        e, auth_context={"token_type": "bearer"}
    )
    return error_response
```

## Error Codes

The system uses standardized error codes:

- `VALIDATION_ERROR`: Input validation failures
- `AUTHENTICATION_ERROR`: Authentication failures
- `AUTHORIZATION_ERROR`: Authorization failures
- `AGENT_NOT_FOUND`: Agent not registered
- `TOOL_ERROR`: Tool execution failures
- `EXTERNAL_SERVICE_ERROR`: External service failures
- `CONFIGURATION_ERROR`: Configuration issues
- `INTERNAL_ERROR`: Internal system errors
- `TIMEOUT_ERROR`: Operation timeouts
- `RATE_LIMIT_ERROR`: Rate limit exceeded

## Best Practices

### 1. Configure Appropriate Retry Policies

- Use exponential backoff for external services
- Set reasonable max delays to avoid long waits
- Only retry recoverable errors (network, timeouts)
- Don't retry validation or authentication errors

### 2. Set Up Circuit Breakers for External Dependencies

- Configure failure thresholds based on service SLAs
- Set recovery timeouts appropriate for the service
- Monitor circuit breaker states

### 3. Implement Comprehensive Alerting

- Set different severity levels for different error types
- Configure appropriate time windows and thresholds
- Integrate with monitoring and notification systems

### 4. Monitor Error Metrics

- Track error rates and patterns
- Monitor retry success rates
- Watch for circuit breaker activations
- Set up dashboards for error visibility

### 5. Handle Errors Gracefully

- Provide meaningful error messages to users
- Log errors with sufficient context
- Implement fallback mechanisms where possible
- Don't expose internal error details to end users

## Integration with Agents

The error handler integrates seamlessly with the agent framework:

```python
class MyAgent(BaseAgent):
    def __init__(self, config):
        super().__init__(config)
        self.error_handler = ErrorHandler(self.logger)
        
        # Configure retry policy for this agent
        policy = RetryPolicy(max_retries=3, retry_exceptions=[ConnectionError])
        self.error_handler.set_retry_policy("agent_operation", policy)
    
    async def process_request(self, request):
        try:
            return await self.error_handler.execute_with_retry(
                "agent_operation",
                self._do_process_request,
                request
            )
        except Exception as e:
            return await self.error_handler.handle_agent_error(e, request)
```

## Testing Error Handling

The framework includes comprehensive tests for error handling scenarios:

```bash
# Run error handler tests
python -m pytest tests/test_error_handler.py -v

# Run with coverage
python -m pytest tests/test_error_handler.py --cov=agent_core.error_handler
```

## Demo and Examples

See the comprehensive demo script for examples of all features:

```bash
python examples/error_handling_demo.py
```

This demonstrates:
- Different retry strategies
- Circuit breaker behavior
- Error alerting
- Metrics collection
- Integration patterns