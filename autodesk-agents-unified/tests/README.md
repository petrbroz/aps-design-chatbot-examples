# Integration and End-to-End Tests

This directory contains comprehensive integration and end-to-end tests for the unified agent system. These tests validate the complete functionality of the migrated agents, their interactions with external services, and the API gateway.

## Test Structure

### Test Categories

1. **Agent Integration Tests** (`test_agent_integration.py`)
   - Agent initialization with real services
   - Caching behavior and performance
   - Error scenarios and recovery
   - Cross-agent functionality
   - Concurrent request handling

2. **External Services Integration** (`test_external_services_integration.py`)
   - APS (Autodesk Platform Services) API integration
   - AECDM (AEC Data Model) API integration
   - OpenSearch vector store integration
   - AWS Bedrock integration
   - Service resilience and error handling

3. **End-to-End API Tests** (`test_end_to_end_api.py`)
   - Full request-response cycle tests
   - Backward compatibility with existing client patterns
   - Authentication and authorization flows
   - Concurrent request handling and performance

4. **API Gateway Middleware Tests** (`test_api_gateway_middleware.py`)
   - Request/response transformation middleware
   - Authentication middleware
   - CORS and security headers
   - Request logging and monitoring

## Running Tests

### Quick Start

```bash
# Run all tests
python run_integration_tests.py

# Run specific test type
python run_integration_tests.py --type integration
python run_integration_tests.py --type e2e
python run_integration_tests.py --type external

# Run specific test files
python run_integration_tests.py --files tests/test_agent_integration.py

# Run in verbose mode
python run_integration_tests.py --verbose

# Run quick tests only (skip slow/external)
python run_integration_tests.py --quick
```

### Using pytest directly

```bash
# Run all integration tests
pytest -m integration

# Run end-to-end tests
pytest -m e2e

# Run with coverage
pytest --cov=agent_core --cov-report=html

# Run specific test file
pytest tests/test_agent_integration.py -v

# Run tests matching pattern
pytest -k "test_concurrent" -v
```

## Test Markers

Tests are organized using pytest markers:

- `@pytest.mark.unit` - Unit tests
- `@pytest.mark.integration` - Integration tests with mocked external services
- `@pytest.mark.e2e` - End-to-end tests with full API stack
- `@pytest.mark.external` - Tests requiring real external services
- `@pytest.mark.slow` - Slow running tests (>5 seconds)
- `@pytest.mark.performance` - Performance and load tests

## Test Configuration

### Environment Variables

Set these environment variables for testing:

```bash
export TESTING=true
export AWS_DEFAULT_REGION=us-east-1
export OPENSEARCH_ENDPOINT=https://your-opensearch-endpoint.amazonaws.com
```

### Mock Services

Most tests use mocked external services to avoid:
- Real API calls and costs
- Network dependencies
- Rate limiting
- Authentication complexity

Mocks are configured in `conftest.py` and provide realistic responses.

### Real Service Testing

For tests marked with `@pytest.mark.external`, you need:
- Valid AWS credentials
- Access to OpenSearch cluster
- Valid Autodesk API tokens

## Test Fixtures

### Common Fixtures

- `test_config` - Test configuration with temporary cache directory
- `mock_aws_services` - Mocked AWS Bedrock and other services
- `mock_opensearch` - Mocked OpenSearch client
- `mock_external_apis` - Mocked APS and AECDM APIs
- `sample_auth_contexts` - Sample authentication contexts
- `sample_requests` - Sample agent requests
- `sample_responses` - Sample agent responses

### Agent Core Fixtures

- `agent_core_with_mocks` - Fully initialized AgentCore with mocked services
- `temp_cache_dir` - Temporary cache directory for tests

## Test Data

### Authentication Contexts

```python
{
    "model_properties": AuthContext(
        access_token="test_mp_token_12345",
        project_id="b.project123",
        version_id="test_version_456"
    ),
    "aec_data_model": AuthContext(
        access_token="test_aec_token_12345",
        element_group_id="test_element_group_789"
    ),
    "model_derivatives": AuthContext(
        access_token="test_md_token_12345",
        urn="dXJuOmFkc2sud2lwcHJvZDpmcy5maWxlOnZmLlUyTVk1UEFwUi1PV2l2TS1Zam9BQXc_dmVyc2lvbj0x"
    )
}
```

### Sample Requests

Each agent type has sample requests that exercise typical functionality:
- Model Properties: Index creation and property queries
- AEC Data Model: Element searches with GraphQL
- Model Derivatives: Database setup and SQL queries

## Performance Testing

Performance tests validate:
- Response time consistency under load
- Memory usage under concurrent requests
- Throughput with multiple agents
- Resource cleanup after requests

### Performance Benchmarks

- Single request: < 5 seconds
- Concurrent requests (10): < 10 seconds total
- Memory increase under load: < 100MB
- Response time variance: < 2x average

## Error Testing

Error scenarios tested include:
- Invalid authentication tokens
- Network timeouts and failures
- External service unavailability
- Malformed requests
- Resource exhaustion

### Error Recovery

Tests validate that the system:
- Handles errors gracefully
- Returns appropriate error messages
- Maintains system stability
- Recovers from transient failures

## Coverage Requirements

Minimum coverage targets:
- Overall: 85%
- Agent classes: 90%
- API Gateway: 90%
- Error handlers: 95%

## Continuous Integration

Tests are designed to run in CI environments:
- No external dependencies (when using mocks)
- Deterministic results
- Reasonable execution time
- Clear failure reporting

### CI Configuration

```yaml
# Example GitHub Actions configuration
- name: Run Integration Tests
  run: |
    python run_integration_tests.py --quick
    
- name: Run Full Test Suite
  run: |
    python run_integration_tests.py --type all
  env:
    TESTING: true
    AWS_DEFAULT_REGION: us-east-1
```

## Troubleshooting

### Common Issues

1. **Import Errors**
   - Ensure all dependencies are installed: `pip install -r requirements.txt`
   - Check Python path includes project root

2. **Async Test Failures**
   - Verify `pytest-asyncio` is installed
   - Check `asyncio_mode = auto` in pytest.ini

3. **Mock Service Issues**
   - Verify mocks are properly configured in conftest.py
   - Check that external service calls are patched

4. **Performance Test Failures**
   - May fail on slow systems
   - Adjust timeouts in test configuration
   - Run with `--slow` marker to skip performance tests

### Debug Mode

Run tests with debug output:

```bash
pytest -v -s --tb=long tests/test_agent_integration.py::TestModelPropertiesAgentIntegration::test_specific_test
```

### Test Isolation

Each test runs in isolation with:
- Temporary cache directories
- Fresh mock configurations
- Clean agent state

## Contributing

When adding new tests:

1. Follow existing naming conventions
2. Use appropriate markers
3. Include docstrings explaining test purpose
4. Mock external services appropriately
5. Add performance assertions where relevant
6. Test both success and failure scenarios

### Test Template

```python
@pytest.mark.integration
async def test_new_functionality(self, agent_core, sample_auth_contexts):
    """Test description explaining what is being validated."""
    # Arrange
    agent = SomeAgent(agent_core)
    auth_context = sample_auth_contexts["agent_type"]
    
    # Act
    result = await agent.some_method(auth_context)
    
    # Assert
    assert result.success
    assert "expected_content" in result.responses[0]
```

## Reporting

Test execution generates:
- Console output with pass/fail status
- HTML coverage report in `htmlcov/`
- XML coverage report for CI
- JUnit XML test results
- Detailed execution report

Access reports:
- Coverage: Open `htmlcov/index.html`
- Test results: Check `test-results.xml`
- Execution report: Read `test_execution_report.txt`