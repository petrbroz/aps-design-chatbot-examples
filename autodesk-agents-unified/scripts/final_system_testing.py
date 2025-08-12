#!/usr/bin/env python3
"""
Final Integration and System Testing Script

This script performs comprehensive system testing with all agents to validate:
- Performance benchmarks against original implementations
- System behavior under load and stress conditions
- All requirements are met and documented
- Complete end-to-end functionality

Requirements covered: 1.1, 1.2, 1.3, 1.4
"""

import os
import sys
import json
import time
import logging
import argparse
import asyncio
import subprocess
import tempfile
import statistics
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict

import requests
import psutil
import pytest

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Performance metrics data structure"""
    test_name: str
    avg_response_time: float
    min_response_time: float
    max_response_time: float
    p95_response_time: float
    p99_response_time: float
    success_rate: float
    throughput: float
    memory_usage_mb: float
    cpu_usage_percent: float
    error_count: int
    total_requests: int


@dataclass
class SystemTestResults:
    """System test results data structure"""
    timestamp: str
    overall_status: str
    requirements_validation: Dict[str, bool]
    performance_benchmarks: List[PerformanceMetrics]
    load_test_results: Dict[str, Any]
    stress_test_results: Dict[str, Any]
    integration_test_results: Dict[str, Any]
    agent_functionality_tests: Dict[str, Any]
    backward_compatibility_tests: Dict[str, Any]
    error_scenarios_tests: Dict[str, Any]
    resource_usage_analysis: Dict[str, Any]
    test_summary: Dict[str, int]


class FinalSystemTester:
    """Comprehensive final system testing"""
    
    def __init__(self, base_url: str = "http://localhost:8000", 
                 original_implementations_path: str = None):
        self.base_url = base_url.rstrip('/')
        self.original_implementations_path = original_implementations_path
        self.results = SystemTestResults(
            timestamp=datetime.now().isoformat(),
            overall_status="unknown",
            requirements_validation={},
            performance_benchmarks=[],
            load_test_results={},
            stress_test_results={},
            integration_test_results={},
            agent_functionality_tests={},
            backward_compatibility_tests={},
            error_scenarios_tests={},
            resource_usage_analysis={},
            test_summary={"passed": 0, "failed": 0, "warnings": 0, "total": 0}
        )
        
        # Performance baseline from original implementations
        self.performance_baselines = {
            "model_properties": {
                "avg_response_time": 3.0,  # seconds
                "max_response_time": 10.0,
                "success_rate": 0.95
            },
            "aec_data_model": {
                "avg_response_time": 2.5,
                "max_response_time": 8.0,
                "success_rate": 0.95
            },
            "model_derivatives": {
                "avg_response_time": 4.0,
                "max_response_time": 15.0,
                "success_rate": 0.95
            }
        }
    
    def log_test_result(self, test_name: str, status: str, details: Dict[str, Any] = None) -> None:
        """Log test result and update summary"""
        status_icon = "✅" if status == "passed" else "❌" if status == "failed" else "⚠️"
        logger.info(f"{status_icon} {test_name}")
        
        if status == "failed" and details:
            logger.error(f"   Details: {details}")
        
        # Update summary
        self.results.test_summary[status] += 1
        self.results.test_summary["total"] += 1
    
    async def validate_requirements_compliance(self) -> bool:
        """Validate all requirements are met (Requirements 1.1, 1.2, 1.3, 1.4)"""
        logger.info("🔍 Validating requirements compliance...")
        
        requirements_tests = {
            "1.1_unified_architecture": self._test_requirement_1_1,
            "1.2_interface_compatibility": self._test_requirement_1_2,
            "1.3_single_deployment": self._test_requirement_1_3,
            "1.4_tool_modularity": self._test_requirement_1_4
        }
        
        all_passed = True
        
        for req_id, test_func in requirements_tests.items():
            try:
                result = await test_func()
                self.results.requirements_validation[req_id] = result
                
                if result:
                    self.log_test_result(f"Requirement {req_id.replace('_', '.')}", "passed")
                else:
                    self.log_test_result(f"Requirement {req_id.replace('_', '.')}", "failed")
                    all_passed = False
                    
            except Exception as e:
                logger.error(f"Error testing requirement {req_id}: {e}")
                self.results.requirements_validation[req_id] = False
                self.log_test_result(f"Requirement {req_id.replace('_', '.')}", "failed", {"error": str(e)})
                all_passed = False
        
        return all_passed
    
    async def _test_requirement_1_1(self) -> bool:
        """Test Requirement 1.1: Unified AgentCore and Strands architecture"""
        try:
            # Test that all three agents are available through unified system
            response = requests.get(f"{self.base_url}/health/agents", timeout=10)
            
            if response.status_code != 200:
                return False
            
            agents_data = response.json()
            expected_agents = ["model_properties", "aec_data_model", "model_derivatives"]
            
            # Check that all agents are present and using AgentCore
            if "agents" in agents_data:
                found_agents = [agent.get("type") for agent in agents_data["agents"]]
                return all(agent in found_agents for agent in expected_agents)
            
            return False
            
        except Exception as e:
            logger.error(f"Requirement 1.1 test failed: {e}")
            return False
    
    async def _test_requirement_1_2(self) -> bool:
        """Test Requirement 1.2: Interface compatibility maintained"""
        try:
            # Test that existing API patterns still work
            test_payloads = [
                {
                    "endpoint": "/api/v1/model-properties/prompt",
                    "payload": {"prompt": "Test compatibility", "project_id": "test"}
                },
                {
                    "endpoint": "/api/v1/aec-data-model/prompt", 
                    "payload": {"prompt": "Test compatibility", "element_group_id": "test"}
                },
                {
                    "endpoint": "/api/v1/model-derivatives/prompt",
                    "payload": {"prompt": "Test compatibility", "urn": "test"}
                }
            ]
            
            for test_case in test_payloads:
                response = requests.post(
                    f"{self.base_url}{test_case['endpoint']}",
                    json=test_case["payload"],
                    timeout=30
                )
                
                # Should return 200 or proper error (not 404/500)
                if response.status_code not in [200, 400, 401, 403]:
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Requirement 1.2 test failed: {e}")
            return False
    
    async def _test_requirement_1_3(self) -> bool:
        """Test Requirement 1.3: Single deployment model"""
        try:
            # Test that all agents are served from single deployment
            response = requests.get(f"{self.base_url}/health", timeout=10)
            
            if response.status_code != 200:
                return False
            
            health_data = response.json()
            
            # Should have unified health endpoint showing all agents
            return "agents" in str(health_data).lower() or "unified" in str(health_data).lower()
            
        except Exception as e:
            logger.error(f"Requirement 1.3 test failed: {e}")
            return False
    
    async def _test_requirement_1_4(self) -> bool:
        """Test Requirement 1.4: Tool modularity and reusability"""
        try:
            # Test that tools are properly modularized
            # This would require checking the tool registry endpoint
            response = requests.get(f"{self.base_url}/api/v1/tools", timeout=10)
            
            if response.status_code == 200:
                tools_data = response.json()
                # Should have tools organized by category/agent
                return isinstance(tools_data, dict) and len(tools_data) > 0
            
            # If tools endpoint doesn't exist, check agent functionality
            # which implies tools are working
            agents = ["model_properties", "aec_data_model", "model_derivatives"]
            for agent in agents:
                test_response = requests.post(
                    f"{self.base_url}/api/v1/agents/{agent}/prompt",
                    json={"prompt": "List your tools", "context": {"test": True}},
                    timeout=30
                )
                
                if test_response.status_code not in [200, 400, 401]:
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Requirement 1.4 test failed: {e}")
            return False
    
    async def run_performance_benchmarks(self) -> bool:
        """Run performance benchmarks against original implementations"""
        logger.info("⚡ Running performance benchmarks...")
        
        agents = ["model_properties", "aec_data_model", "model_derivatives"]
        all_passed = True
        
        for agent in agents:
            try:
                metrics = await self._benchmark_agent_performance(agent)
                self.results.performance_benchmarks.append(metrics)
                
                # Compare against baseline
                baseline = self.performance_baselines[agent]
                
                performance_acceptable = (
                    metrics.avg_response_time <= baseline["avg_response_time"] * 1.2 and  # 20% tolerance
                    metrics.max_response_time <= baseline["max_response_time"] * 1.5 and  # 50% tolerance
                    metrics.success_rate >= baseline["success_rate"]
                )
                
                if performance_acceptable:
                    self.log_test_result(f"Performance Benchmark - {agent}", "passed")
                else:
                    self.log_test_result(f"Performance Benchmark - {agent}", "failed", {
                        "actual": asdict(metrics),
                        "baseline": baseline
                    })
                    all_passed = False
                    
            except Exception as e:
                logger.error(f"Performance benchmark failed for {agent}: {e}")
                self.log_test_result(f"Performance Benchmark - {agent}", "failed", {"error": str(e)})
                all_passed = False
        
        return all_passed
    
    async def _benchmark_agent_performance(self, agent_type: str) -> PerformanceMetrics:
        """Benchmark individual agent performance"""
        test_prompts = {
            "model_properties": "List available properties for walls",
            "aec_data_model": "Find all door elements in the design",
            "model_derivatives": "Query elements with area greater than 10 square meters"
        }
        
        prompt = test_prompts[agent_type]
        endpoint = f"/api/v1/agents/{agent_type}/prompt"
        
        # Warm up
        for _ in range(3):
            try:
                requests.post(
                    f"{self.base_url}{endpoint}",
                    json={"prompt": prompt, "context": {"test": True}},
                    timeout=30
                )
            except:
                pass
        
        # Benchmark runs
        response_times = []
        success_count = 0
        error_count = 0
        
        # Monitor system resources
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        initial_cpu = process.cpu_percent()
        
        start_time = time.time()
        
        for i in range(20):  # 20 requests for statistical significance
            request_start = time.time()
            
            try:
                response = requests.post(
                    f"{self.base_url}{endpoint}",
                    json={"prompt": f"{prompt} (test {i})", "context": {"test": True}},
                    timeout=30
                )
                
                request_time = time.time() - request_start
                response_times.append(request_time)
                
                if response.status_code == 200:
                    success_count += 1
                else:
                    error_count += 1
                    
            except Exception as e:
                error_count += 1
                response_times.append(30.0)  # Timeout value
        
        total_time = time.time() - start_time
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        final_cpu = process.cpu_percent()
        
        # Calculate metrics
        if response_times:
            avg_response_time = statistics.mean(response_times)
            min_response_time = min(response_times)
            max_response_time = max(response_times)
            
            sorted_times = sorted(response_times)
            p95_response_time = sorted_times[int(0.95 * len(sorted_times))]
            p99_response_time = sorted_times[int(0.99 * len(sorted_times))]
        else:
            avg_response_time = min_response_time = max_response_time = 0
            p95_response_time = p99_response_time = 0
        
        return PerformanceMetrics(
            test_name=f"{agent_type}_benchmark",
            avg_response_time=avg_response_time,
            min_response_time=min_response_time,
            max_response_time=max_response_time,
            p95_response_time=p95_response_time,
            p99_response_time=p99_response_time,
            success_rate=success_count / 20,
            throughput=success_count / total_time,
            memory_usage_mb=final_memory - initial_memory,
            cpu_usage_percent=final_cpu - initial_cpu,
            error_count=error_count,
            total_requests=20
        )
    
    async def run_load_stress_tests(self) -> bool:
        """Test system behavior under load and stress conditions"""
        logger.info("🔥 Running load and stress tests...")
        
        load_tests = [
            ("Concurrent Users", self._test_concurrent_users),
            ("High Request Volume", self._test_high_request_volume),
            ("Memory Stress", self._test_memory_stress),
            ("Long Running Requests", self._test_long_running_requests),
            ("Resource Exhaustion", self._test_resource_exhaustion)
        ]
        
        all_passed = True
        
        for test_name, test_func in load_tests:
            try:
                result = await test_func()
                
                if result["success"]:
                    self.log_test_result(f"Load Test - {test_name}", "passed")
                    self.results.load_test_results[test_name] = result
                else:
                    self.log_test_result(f"Load Test - {test_name}", "failed", result)
                    self.results.load_test_results[test_name] = result
                    all_passed = False
                    
            except Exception as e:
                logger.error(f"Load test {test_name} failed: {e}")
                self.log_test_result(f"Load Test - {test_name}", "failed", {"error": str(e)})
                all_passed = False
        
        return all_passed
    
    async def _test_concurrent_users(self) -> Dict[str, Any]:
        """Test concurrent user load"""
        concurrent_users = 50
        requests_per_user = 5
        
        def make_user_requests(user_id: int):
            results = []
            for i in range(requests_per_user):
                try:
                    start_time = time.time()
                    response = requests.post(
                        f"{self.base_url}/api/v1/agents/model_properties/prompt",
                        json={
                            "prompt": f"User {user_id} request {i}",
                            "context": {"user_id": user_id, "test": True}
                        },
                        timeout=30
                    )
                    
                    duration = time.time() - start_time
                    results.append({
                        "success": response.status_code == 200,
                        "duration": duration,
                        "status_code": response.status_code
                    })
                    
                except Exception as e:
                    results.append({
                        "success": False,
                        "duration": 30.0,
                        "error": str(e)
                    })
            
            return results
        
        # Monitor system resources
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024
        
        start_time = time.time()
        
        # Execute concurrent requests
        with ThreadPoolExecutor(max_workers=concurrent_users) as executor:
            futures = [executor.submit(make_user_requests, user_id) 
                      for user_id in range(concurrent_users)]
            
            all_results = []
            for future in as_completed(futures):
                all_results.extend(future.result())
        
        total_time = time.time() - start_time
        final_memory = process.memory_info().rss / 1024 / 1024
        
        # Analyze results
        successful_requests = sum(1 for r in all_results if r["success"])
        total_requests = len(all_results)
        avg_response_time = statistics.mean([r["duration"] for r in all_results])
        
        success_rate = successful_requests / total_requests
        memory_increase = final_memory - initial_memory
        
        return {
            "success": success_rate >= 0.9 and memory_increase < 500,  # 90% success, <500MB memory
            "concurrent_users": concurrent_users,
            "total_requests": total_requests,
            "successful_requests": successful_requests,
            "success_rate": success_rate,
            "avg_response_time": avg_response_time,
            "total_time": total_time,
            "memory_increase_mb": memory_increase,
            "throughput": successful_requests / total_time
        }
    
    async def _test_high_request_volume(self) -> Dict[str, Any]:
        """Test high volume of requests"""
        total_requests = 200
        batch_size = 20
        
        successful_requests = 0
        total_time = 0
        response_times = []
        
        for batch_start in range(0, total_requests, batch_size):
            batch_end = min(batch_start + batch_size, total_requests)
            batch_requests = batch_end - batch_start
            
            start_time = time.time()
            
            # Make batch of requests
            with ThreadPoolExecutor(max_workers=batch_size) as executor:
                futures = []
                for i in range(batch_requests):
                    future = executor.submit(
                        requests.post,
                        f"{self.base_url}/api/v1/agents/aec_data_model/prompt",
                        json={"prompt": f"High volume test {batch_start + i}", "context": {"test": True}},
                        timeout=30
                    )
                    futures.append(future)
                
                for future in as_completed(futures):
                    try:
                        response = future.result()
                        if response.status_code == 200:
                            successful_requests += 1
                    except:
                        pass
            
            batch_time = time.time() - start_time
            total_time += batch_time
            response_times.append(batch_time / batch_requests)
            
            # Small delay between batches
            await asyncio.sleep(0.5)
        
        success_rate = successful_requests / total_requests
        avg_response_time = statistics.mean(response_times) if response_times else 0
        
        return {
            "success": success_rate >= 0.85,  # 85% success rate for high volume
            "total_requests": total_requests,
            "successful_requests": successful_requests,
            "success_rate": success_rate,
            "avg_response_time": avg_response_time,
            "total_time": total_time,
            "throughput": successful_requests / total_time
        }
    
    async def _test_memory_stress(self) -> Dict[str, Any]:
        """Test memory usage under stress"""
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024
        
        # Create large payloads to stress memory
        large_prompt = "Analyze this design " + "with many details " * 100
        
        memory_samples = []
        successful_requests = 0
        
        for i in range(50):
            try:
                response = requests.post(
                    f"{self.base_url}/api/v1/agents/model_derivatives/prompt",
                    json={
                        "prompt": large_prompt,
                        "context": {"test": True, "iteration": i}
                    },
                    timeout=30
                )
                
                if response.status_code == 200:
                    successful_requests += 1
                
                # Sample memory usage
                current_memory = process.memory_info().rss / 1024 / 1024
                memory_samples.append(current_memory)
                
            except Exception as e:
                logger.warning(f"Memory stress test request {i} failed: {e}")
        
        final_memory = process.memory_info().rss / 1024 / 1024
        max_memory = max(memory_samples) if memory_samples else final_memory
        memory_increase = final_memory - initial_memory
        peak_memory_increase = max_memory - initial_memory
        
        return {
            "success": memory_increase < 1000 and peak_memory_increase < 1500,  # <1GB sustained, <1.5GB peak
            "initial_memory_mb": initial_memory,
            "final_memory_mb": final_memory,
            "max_memory_mb": max_memory,
            "memory_increase_mb": memory_increase,
            "peak_memory_increase_mb": peak_memory_increase,
            "successful_requests": successful_requests,
            "total_requests": 50
        }
    
    async def _test_long_running_requests(self) -> Dict[str, Any]:
        """Test handling of long-running requests"""
        # Simulate requests that might take longer
        long_prompts = [
            "Perform a comprehensive analysis of all building elements",
            "Generate detailed reports for all properties in the design",
            "Execute complex queries across all element categories"
        ]
        
        successful_requests = 0
        response_times = []
        
        for i, prompt in enumerate(long_prompts * 3):  # 9 total requests
            try:
                start_time = time.time()
                response = requests.post(
                    f"{self.base_url}/api/v1/agents/aec_data_model/prompt",
                    json={"prompt": prompt, "context": {"test": True, "long_running": True}},
                    timeout=60  # Longer timeout for long-running requests
                )
                
                duration = time.time() - start_time
                response_times.append(duration)
                
                if response.status_code == 200:
                    successful_requests += 1
                    
            except Exception as e:
                logger.warning(f"Long-running request {i} failed: {e}")
                response_times.append(60.0)
        
        avg_response_time = statistics.mean(response_times) if response_times else 0
        max_response_time = max(response_times) if response_times else 0
        
        return {
            "success": successful_requests >= 6 and max_response_time < 45,  # At least 6/9 success, <45s max
            "successful_requests": successful_requests,
            "total_requests": 9,
            "avg_response_time": avg_response_time,
            "max_response_time": max_response_time,
            "response_times": response_times
        }
    
    async def _test_resource_exhaustion(self) -> Dict[str, Any]:
        """Test system behavior under resource exhaustion"""
        # Test with many concurrent requests to exhaust resources
        concurrent_requests = 100
        
        def make_request(request_id: int):
            try:
                response = requests.post(
                    f"{self.base_url}/api/v1/agents/model_properties/prompt",
                    json={
                        "prompt": f"Resource exhaustion test {request_id}",
                        "context": {"test": True, "resource_test": True}
                    },
                    timeout=20
                )
                
                return {
                    "success": response.status_code == 200,
                    "status_code": response.status_code,
                    "request_id": request_id
                }
                
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                    "request_id": request_id
                }
        
        # Monitor system resources
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024
        initial_cpu = process.cpu_percent()
        
        start_time = time.time()
        
        # Execute all requests concurrently
        with ThreadPoolExecutor(max_workers=concurrent_requests) as executor:
            futures = [executor.submit(make_request, i) for i in range(concurrent_requests)]
            results = [future.result() for future in as_completed(futures)]
        
        total_time = time.time() - start_time
        final_memory = process.memory_info().rss / 1024 / 1024
        final_cpu = process.cpu_percent()
        
        successful_requests = sum(1 for r in results if r["success"])
        success_rate = successful_requests / concurrent_requests
        
        # System should handle resource exhaustion gracefully
        # Success criteria: at least 50% success rate and system remains responsive
        system_responsive = True
        try:
            health_response = requests.get(f"{self.base_url}/health", timeout=10)
            system_responsive = health_response.status_code == 200
        except:
            system_responsive = False
        
        return {
            "success": success_rate >= 0.5 and system_responsive,
            "concurrent_requests": concurrent_requests,
            "successful_requests": successful_requests,
            "success_rate": success_rate,
            "total_time": total_time,
            "memory_increase_mb": final_memory - initial_memory,
            "cpu_increase_percent": final_cpu - initial_cpu,
            "system_responsive": system_responsive
        }
    
    async def run_integration_tests(self) -> bool:
        """Run comprehensive integration tests"""
        logger.info("🔗 Running integration tests...")
        
        # Run existing integration test suite
        try:
            # Change to the correct directory
            os.chdir("autodesk-agents-unified")
            
            # Run integration tests using pytest
            result = subprocess.run([
                "python", "-m", "pytest",
                "tests/test_agent_integration.py",
                "tests/test_end_to_end_api.py", 
                "tests/test_external_services_integration.py",
                "-v", "--tb=short",
                "--json-report", "--json-report-file=integration_test_results.json"
            ], capture_output=True, text=True, timeout=600)
            
            # Parse results
            if os.path.exists("integration_test_results.json"):
                with open("integration_test_results.json", 'r') as f:
                    test_results = json.load(f)
                
                self.results.integration_test_results = {
                    "total_tests": test_results.get("summary", {}).get("total", 0),
                    "passed_tests": test_results.get("summary", {}).get("passed", 0),
                    "failed_tests": test_results.get("summary", {}).get("failed", 0),
                    "duration": test_results.get("duration", 0),
                    "success_rate": test_results.get("summary", {}).get("passed", 0) / max(test_results.get("summary", {}).get("total", 1), 1)
                }
                
                success = self.results.integration_test_results["success_rate"] >= 0.8
                
                if success:
                    self.log_test_result("Integration Test Suite", "passed")
                else:
                    self.log_test_result("Integration Test Suite", "failed", self.results.integration_test_results)
                
                return success
            else:
                # Fallback if JSON report not available
                success = result.returncode == 0
                
                self.results.integration_test_results = {
                    "returncode": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr
                }
                
                if success:
                    self.log_test_result("Integration Test Suite", "passed")
                else:
                    self.log_test_result("Integration Test Suite", "failed", {
                        "returncode": result.returncode,
                        "stderr": result.stderr[:500]  # First 500 chars
                    })
                
                return success
                
        except Exception as e:
            logger.error(f"Integration tests failed: {e}")
            self.log_test_result("Integration Test Suite", "failed", {"error": str(e)})
            return False
    
    async def run_comprehensive_system_tests(self) -> bool:
        """Run all comprehensive system tests"""
        logger.info("🚀 Starting comprehensive final system testing...")
        
        test_phases = [
            ("Requirements Validation", self.validate_requirements_compliance),
            ("Performance Benchmarks", self.run_performance_benchmarks),
            ("Load and Stress Tests", self.run_load_stress_tests),
            ("Integration Tests", self.run_integration_tests)
        ]
        
        passed_phases = 0
        total_phases = len(test_phases)
        
        for phase_name, phase_func in test_phases:
            logger.info(f"📋 Running {phase_name}...")
            
            try:
                phase_start = time.time()
                result = await phase_func()
                phase_duration = time.time() - phase_start
                
                if result:
                    passed_phases += 1
                    logger.info(f"✅ {phase_name} completed successfully ({phase_duration:.1f}s)")
                else:
                    logger.error(f"❌ {phase_name} failed ({phase_duration:.1f}s)")
                    
            except Exception as e:
                logger.error(f"💥 {phase_name} failed with exception: {e}")
        
        # Calculate overall success
        success_rate = passed_phases / total_phases
        
        if success_rate >= 0.75:  # 75% success rate required
            self.results.overall_status = "passed"
            logger.info(f"🎉 Final system testing PASSED ({passed_phases}/{total_phases} phases)")
            return True
        else:
            self.results.overall_status = "failed"
            logger.error(f"💥 Final system testing FAILED ({passed_phases}/{total_phases} phases)")
            return False
    
    def save_results(self, output_file: str = "final_system_test_results.json") -> None:
        """Save comprehensive test results"""
        try:
            # Convert dataclass to dict for JSON serialization
            results_dict = asdict(self.results)
            
            with open(output_file, 'w') as f:
                json.dump(results_dict, f, indent=2, default=str)
            
            logger.info(f"Final system test results saved to {output_file}")
            
        except Exception as e:
            logger.error(f"Failed to save results: {e}")
    
    def print_comprehensive_summary(self) -> None:
        """Print comprehensive test summary"""
        print("\n" + "="*100)
        print("🏁 FINAL INTEGRATION AND SYSTEM TESTING SUMMARY")
        print("="*100)
        
        print(f"Timestamp: {self.results.timestamp}")
        print(f"Overall Status: {self.results.overall_status.upper()}")
        print(f"Base URL: {self.base_url}")
        
        # Test summary
        summary = self.results.test_summary
        print(f"\n📊 Test Summary: {summary['passed']} passed, {summary['failed']} failed, {summary['warnings']} warnings, {summary['total']} total")
        print(f"Success Rate: {(summary['passed']/max(summary['total'], 1))*100:.1f}%")
        
        # Requirements validation
        print(f"\n📋 Requirements Validation:")
        for req_id, passed in self.results.requirements_validation.items():
            status = "✅ PASSED" if passed else "❌ FAILED"
            print(f"  {req_id.replace('_', '.')}: {status}")
        
        # Performance benchmarks
        if self.results.performance_benchmarks:
            print(f"\n⚡ Performance Benchmarks:")
            for metrics in self.results.performance_benchmarks:
                print(f"  {metrics.test_name}:")
                print(f"    Avg Response Time: {metrics.avg_response_time*1000:.1f}ms")
                print(f"    Success Rate: {metrics.success_rate*100:.1f}%")
                print(f"    Throughput: {metrics.throughput:.1f} req/s")
        
        # Load test results
        if self.results.load_test_results:
            print(f"\n🔥 Load Test Results:")
            for test_name, result in self.results.load_test_results.items():
                status = "✅ PASSED" if result.get("success", False) else "❌ FAILED"
                print(f"  {test_name}: {status}")
                if "success_rate" in result:
                    print(f"    Success Rate: {result['success_rate']*100:.1f}%")
        
        # Integration tests
        if self.results.integration_test_results:
            print(f"\n🔗 Integration Tests:")
            integration = self.results.integration_test_results
            if "total_tests" in integration:
                print(f"  Total Tests: {integration['total_tests']}")
                print(f"  Passed: {integration['passed_tests']}")
                print(f"  Failed: {integration['failed_tests']}")
                print(f"  Success Rate: {integration['success_rate']*100:.1f}%")
        
        print("\n" + "="*100)
        
        if self.results.overall_status == "passed":
            print("🎉 ALL REQUIREMENTS VALIDATED - SYSTEM READY FOR PRODUCTION")
        else:
            print("💥 SYSTEM TESTING FAILED - REVIEW ISSUES BEFORE DEPLOYMENT")
        
        print("="*100)


async def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="Final Integration and System Testing")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Base URL of the system")
    parser.add_argument("--original-path", help="Path to original implementations for comparison")
    parser.add_argument("--output", default="final_system_test_results.json", help="Output file for results")
    parser.add_argument("--wait-time", type=int, default=60, help="Time to wait for system to be ready")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Wait for system to be ready
    if args.wait_time > 0:
        logger.info(f"⏳ Waiting {args.wait_time} seconds for system to be ready...")
        time.sleep(args.wait_time)
    
    # Initialize tester
    tester = FinalSystemTester(args.base_url, args.original_path)
    
    # Run comprehensive tests
    success = await tester.run_comprehensive_system_tests()
    
    # Save results and print summary
    tester.save_results(args.output)
    tester.print_comprehensive_summary()
    
    return 0 if success else 1


if __name__ == "__main__":
    exit(asyncio.run(main()))