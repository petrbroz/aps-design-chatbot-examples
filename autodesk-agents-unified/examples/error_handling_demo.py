#!/usr/bin/env python3
"""
Demonstration of comprehensive error handling capabilities.

This script shows how to use the enhanced ErrorHandler class with:
- Retry mechanisms with different strategies
- Circuit breakers
- Error alerting and reporting
- Metrics collection
"""

import asyncio
import random
from datetime import datetime

from agent_core.error_handler import (
    ErrorHandler, RetryPolicy, RetryStrategy, AlertSeverity
)
from agent_core.logging import StructuredLogger


class DemoService:
    """Demo service that simulates various failure scenarios."""
    
    def __init__(self, failure_rate: float = 0.3):
        self.failure_rate = failure_rate
        self.call_count = 0
    
    async def unreliable_operation(self, operation_id: str) -> str:
        """Simulate an unreliable operation that sometimes fails."""
        self.call_count += 1
        
        if random.random() < self.failure_rate:
            # Simulate different types of failures
            failure_type = random.choice([
                ConnectionError("Network connection failed"),
                TimeoutError("Operation timed out"),
                ValueError("Invalid input data"),
                RuntimeError("Service temporarily unavailable")
            ])
            raise failure_type
        
        return f"Success for operation {operation_id} (attempt {self.call_count})"


async def demo_retry_mechanisms():
    """Demonstrate different retry strategies."""
    print("\n=== Retry Mechanisms Demo ===")
    
    logger = StructuredLogger(log_level="INFO", service_name="demo")
    error_handler = ErrorHandler(logger)
    service = DemoService(failure_rate=0.7)  # High failure rate
    
    # Configure different retry policies
    policies = {
        "exponential": RetryPolicy(
            max_retries=3,
            strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
            base_delay=0.1,
            backoff_factor=2.0,
            retry_exceptions=[ConnectionError, TimeoutError, RuntimeError]
        ),
        "linear": RetryPolicy(
            max_retries=3,
            strategy=RetryStrategy.LINEAR_BACKOFF,
            base_delay=0.1,
            retry_exceptions=[ConnectionError, TimeoutError, RuntimeError]
        ),
        "fixed": RetryPolicy(
            max_retries=3,
            strategy=RetryStrategy.FIXED_DELAY,
            base_delay=0.1,
            retry_exceptions=[ConnectionError, TimeoutError, RuntimeError]
        )
    }
    
    for strategy_name, policy in policies.items():
        print(f"\nTesting {strategy_name} backoff strategy:")
        error_handler.set_retry_policy(f"demo_{strategy_name}", policy)
        
        try:
            result = await error_handler.execute_with_retry(
                f"demo_{strategy_name}",
                service.unreliable_operation,
                f"test_{strategy_name}"
            )
            print(f"✓ {result}")
        except Exception as e:
            print(f"✗ Failed after retries: {e}")


async def demo_circuit_breaker():
    """Demonstrate circuit breaker functionality."""
    print("\n=== Circuit Breaker Demo ===")
    
    logger = StructuredLogger(log_level="INFO", service_name="demo")
    error_handler = ErrorHandler(logger)
    service = DemoService(failure_rate=0.9)  # Very high failure rate
    
    # Configure circuit breaker
    error_handler.set_circuit_breaker(
        "demo_circuit",
        failure_threshold=3,
        recovery_timeout=2,  # 2 seconds
        half_open_max_calls=2
    )
    
    # Configure retry policy
    policy = RetryPolicy(
        max_retries=1,
        base_delay=0.1,
        retry_exceptions=[ConnectionError, TimeoutError, RuntimeError]
    )
    error_handler.set_retry_policy("demo_circuit", policy)
    
    print("Making calls to trigger circuit breaker...")
    
    for i in range(8):
        try:
            result = await error_handler.execute_with_retry(
                "demo_circuit",
                service.unreliable_operation,
                f"circuit_test_{i}"
            )
            print(f"Call {i+1}: ✓ {result}")
        except Exception as e:
            print(f"Call {i+1}: ✗ {type(e).__name__}: {e}")
        
        # Small delay between calls
        await asyncio.sleep(0.1)
    
    print("\nWaiting for circuit breaker recovery...")
    await asyncio.sleep(2.5)
    
    print("Trying calls after recovery timeout:")
    for i in range(3):
        try:
            result = await error_handler.execute_with_retry(
                "demo_circuit",
                service.unreliable_operation,
                f"recovery_test_{i}"
            )
            print(f"Recovery call {i+1}: ✓ {result}")
        except Exception as e:
            print(f"Recovery call {i+1}: ✗ {type(e).__name__}: {e}")


async def demo_error_alerting():
    """Demonstrate error alerting and reporting."""
    print("\n=== Error Alerting Demo ===")
    
    logger = StructuredLogger(log_level="INFO", service_name="demo")
    error_handler = ErrorHandler(logger)
    
    # Set up alert callback
    def alert_callback(alert):
        print(f"🚨 ALERT: {alert.severity.value.upper()} - {alert.message}")
        print(f"   Error Type: {alert.error_type}")
        print(f"   Count: {alert.count}")
        print(f"   Time Range: {alert.first_occurrence} to {alert.last_occurrence}")
    
    error_handler.register_alert_callback(alert_callback)
    
    # Configure alert thresholds
    error_handler.set_alert_threshold(
        "ConnectionError", 
        threshold=3, 
        time_window_minutes=1,
        severity=AlertSeverity.HIGH
    )
    
    error_handler.set_alert_threshold(
        "ValueError", 
        threshold=2, 
        time_window_minutes=1,
        severity=AlertSeverity.MEDIUM
    )
    
    print("Generating errors to trigger alerts...")
    
    # Generate errors to trigger alerts
    errors = [
        ConnectionError("Connection failed"),
        ConnectionError("Network timeout"),
        ValueError("Invalid data"),
        ConnectionError("Service unavailable"),
        ValueError("Bad input"),
        ConnectionError("Connection reset"),
    ]
    
    for error in errors:
        error_handler._update_error_metrics(error, "demo_service")


async def demo_comprehensive_example():
    """Comprehensive example showing all features together."""
    print("\n=== Comprehensive Error Handling Demo ===")
    
    logger = StructuredLogger(log_level="INFO", service_name="demo")
    error_handler = ErrorHandler(logger)
    service = DemoService(failure_rate=0.4)
    
    # Configure comprehensive error handling
    policy = RetryPolicy(
        max_retries=3,
        strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
        base_delay=0.1,
        backoff_factor=1.5,
        retry_exceptions=[ConnectionError, TimeoutError, RuntimeError]
    )
    error_handler.set_retry_policy("comprehensive_demo", policy)
    
    error_handler.set_circuit_breaker(
        "comprehensive_demo",
        failure_threshold=5,
        recovery_timeout=3
    )
    
    def alert_callback(alert):
        print(f"📊 Alert: {alert.count} {alert.error_type} errors detected")
    
    error_handler.register_alert_callback(alert_callback)
    error_handler.set_alert_threshold("RuntimeError", threshold=2, time_window_minutes=1)
    
    print("Running comprehensive test with multiple operations...")
    
    # Run multiple operations
    for i in range(10):
        try:
            result = await error_handler.execute_with_retry(
                "comprehensive_demo",
                service.unreliable_operation,
                f"comprehensive_{i}"
            )
            print(f"Operation {i+1}: ✓")
        except Exception as e:
            print(f"Operation {i+1}: ✗ {type(e).__name__}")
        
        await asyncio.sleep(0.2)
    
    # Show statistics
    stats = error_handler.get_error_statistics()
    print(f"\n📈 Final Statistics:")
    print(f"   Total Errors: {stats['total_errors']}")
    print(f"   Retry Attempts: {stats['retry_attempts']}")
    print(f"   Successful Recoveries: {stats['successful_recoveries']}")
    print(f"   Failed Recoveries: {stats['failed_recoveries']}")
    print(f"   Error Rate: {stats['error_rate_per_minute']}/min")
    print(f"   Errors by Type: {stats['errors_by_type']}")
    
    # Show recent errors
    recent_errors = error_handler.get_recent_errors(limit=5)
    if recent_errors:
        print(f"\n📋 Recent Errors:")
        for error in recent_errors[-3:]:  # Show last 3
            print(f"   {error['timestamp'].strftime('%H:%M:%S')} - {error['error_type']}: {error['error_message']}")


async def main():
    """Run all demonstrations."""
    print("🔧 Error Handling Capabilities Demonstration")
    print("=" * 50)
    
    await demo_retry_mechanisms()
    await demo_circuit_breaker()
    await demo_error_alerting()
    await demo_comprehensive_example()
    
    print("\n✅ Demo completed!")


if __name__ == "__main__":
    asyncio.run(main())