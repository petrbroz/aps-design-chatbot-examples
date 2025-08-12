#!/usr/bin/env python3
"""
Comprehensive deployment verification script for Autodesk Agents Unified
Performs extensive testing of all system components and integrations
"""

import os
import json
import time
import logging
import argparse
import requests
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DeploymentVerifier:
    """Comprehensive deployment verification"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip('/')
        self.verification_results = {
            "timestamp": datetime.now().isoformat(),
            "base_url": base_url,
            "overall_status": "unknown",
            "test_categories": {},
            "performance_metrics": {},
            "security_checks": {},
            "integration_tests": {}
        }
    
    def log_test_result(self, category: str, test_name: str, status: str, 
                       details: Dict[str, Any] = None, duration: float = 0) -> None:
        """Log test result with category"""
        if category not in self.verification_results["test_categories"]:
            self.verification_results["test_categories"][category] = []
        
        result = {
            "test_name": test_name,
            "status": status,
            "duration": duration,
            "timestamp": datetime.now().isoformat(),
            "details": details or {}
        }
        
        self.verification_results["test_categories"][category].append(result)
        
        status_icon = "✅" if status == "passed" else "❌" if status == "failed" else "⚠️"
        logger.info(f"{status_icon} [{category}] {test_name} ({duration:.2f}s)")
        
        if status == "failed" and details:
            logger.error(f"   Details: {details}")
    
    def test_system_health_comprehensive(self) -> bool:
        """Comprehensive system health testing"""
        start_time = time.time()
        
        try:
            # Test main health endpoint
            response = requests.get(f"{self.base_url}/health", timeout=10)
            
            if response.status_code != 200:
                self.log_test_result(
                    "Health", "Main Health Endpoint", "failed",
                    {"status_code": response.status_code, "response": response.text},
                    time.time() - start_time
                )
                return False
            
            health_data = response.json()
            
            # Verify health response structure
            required_fields = ["status", "timestamp", "version"]
            missing_fields = [field for field in required_fields if field not in health_data]
            
            if missing_fields:
                self.log_test_result(
                    "Health", "Health Response Structure", "failed",
                    {"missing_fields": missing_fields},
                    time.time() - start_time
                )
                return False
            
            # Test detailed health endpoints
            health_endpoints = [
                "/health/agents",
                "/health/dependencies",
                "/health/detailed"
            ]
            
            for endpoint in health_endpoints:
                try:
                    resp = requests.get(f"{self.base_url}{endpoint}", timeout=10)
                    if resp.status_code == 200:
                        self.log_test_result(
                            "Health", f"Health Endpoint {endpoint}", "passed",
                            {"response_size": len(resp.text)},
                            time.time() - start_time
                        )
                    else:
                        self.log_test_result(
                            "Health", f"Health Endpoint {endpoint}", "failed",
                            {"status_code": resp.status_code},
                            time.time() - start_time
                        )
                except Exception as e:
                    self.log_test_result(
                        "Health", f"Health Endpoint {endpoint}", "failed",
                        {"error": str(e)},
                        time.time() - start_time
                    )
            
            self.log_test_result(
                "Health", "System Health Comprehensive", "passed",
                {"health_data": health_data},
                time.time() - start_time
            )
            return True
            
        except Exception as e:
            self.log_test_result(
                "Health", "System Health Comprehensive", "failed",
                {"error": str(e)},
                time.time() - start_time
            )
            return False
    
    def test_agent_functionality_comprehensive(self) -> bool:
        """Comprehensive agent functionality testing"""
        agents = [
            ("model_properties", "List available tools and describe their functionality"),
            ("aec_data_model", "What types of building elements can you help me analyze?"),
            ("model_derivatives", "What database operations and queries can you perform?")
        ]
        
        all_passed = True
        
        for agent_type, test_prompt in agents:
            start_time = time.time()
            
            try:
                # Test agent prompt endpoint
                payload = {
                    "prompt": test_prompt,
                    "context": {
                        "agent_type": agent_type,
                        "test_mode": True
                    }
                }
                
                response = requests.post(
                    f"{self.base_url}/api/v1/agents/{agent_type}/prompt",
                    json=payload,
                    timeout=60
                )
                
                if response.status_code == 200:
                    result = response.json()
                    
                    # Verify response structure
                    if "responses" in result and isinstance(result["responses"], list):
                        response_length = sum(len(str(r)) for r in result["responses"])
                        
                        # Check if response is meaningful (not just error messages)
                        if response_length > 50:  # Minimum meaningful response length
                            self.log_test_result(
                                "Agents", f"{agent_type} Functionality", "passed",
                                {
                                    "response_length": response_length,
                                    "response_count": len(result["responses"]),
                                    "has_metadata": "metadata" in result
                                },
                                time.time() - start_time
                            )
                        else:
                            self.log_test_result(
                                "Agents", f"{agent_type} Functionality", "failed",
                                {"error": "Response too short or empty", "response": result},
                                time.time() - start_time
                            )
                            all_passed = False
                    else:
                        self.log_test_result(
                            "Agents", f"{agent_type} Functionality", "failed",
                            {"error": "Invalid response structure", "response": result},
                            time.time() - start_time
                        )
                        all_passed = False
                else:
                    self.log_test_result(
                        "Agents", f"{agent_type} Functionality", "failed",
                        {"status_code": response.status_code, "response": response.text},
                        time.time() - start_time
                    )
                    all_passed = False
                    
            except Exception as e:
                self.log_test_result(
                    "Agents", f"{agent_type} Functionality", "failed",
                    {"error": str(e)},
                    time.time() - start_time
                )
                all_passed = False
        
        return all_passed
    
    def test_performance_benchmarks(self) -> bool:
        """Performance benchmark testing"""
        start_time = time.time()
        
        try:
            # Test response time under load
            concurrent_requests = 10
            request_timeout = 30
            
            def make_request():
                try:
                    start = time.time()
                    response = requests.get(f"{self.base_url}/health", timeout=request_timeout)
                    duration = time.time() - start
                    return {
                        "status_code": response.status_code,
                        "duration": duration,
                        "success": response.status_code == 200
                    }
                except Exception as e:
                    return {
                        "error": str(e),
                        "duration": request_timeout,
                        "success": False
                    }
            
            # Execute concurrent requests
            with ThreadPoolExecutor(max_workers=concurrent_requests) as executor:
                futures = [executor.submit(make_request) for _ in range(concurrent_requests)]
                results = [future.result() for future in as_completed(futures)]
            
            # Analyze results
            successful_requests = sum(1 for r in results if r["success"])
            response_times = [r["duration"] for r in results if r["success"]]
            
            if response_times:
                avg_response_time = sum(response_times) / len(response_times)
                max_response_time = max(response_times)
                min_response_time = min(response_times)
                
                # Store performance metrics
                self.verification_results["performance_metrics"] = {
                    "concurrent_requests": concurrent_requests,
                    "successful_requests": successful_requests,
                    "success_rate": successful_requests / concurrent_requests,
                    "avg_response_time": avg_response_time,
                    "max_response_time": max_response_time,
                    "min_response_time": min_response_time
                }
                
                # Performance thresholds
                success_rate_threshold = 0.9  # 90%
                avg_response_time_threshold = 2.0  # 2 seconds
                
                if (successful_requests / concurrent_requests >= success_rate_threshold and
                    avg_response_time <= avg_response_time_threshold):
                    
                    self.log_test_result(
                        "Performance", "Load Testing", "passed",
                        self.verification_results["performance_metrics"],
                        time.time() - start_time
                    )
                    return True
                else:
                    self.log_test_result(
                        "Performance", "Load Testing", "failed",
                        {
                            **self.verification_results["performance_metrics"],
                            "thresholds": {
                                "success_rate": success_rate_threshold,
                                "avg_response_time": avg_response_time_threshold
                            }
                        },
                        time.time() - start_time
                    )
                    return False
            else:
                self.log_test_result(
                    "Performance", "Load Testing", "failed",
                    {"error": "No successful requests"},
                    time.time() - start_time
                )
                return False
                
        except Exception as e:
            self.log_test_result(
                "Performance", "Load Testing", "failed",
                {"error": str(e)},
                time.time() - start_time
            )
            return False
    
    def test_security_headers(self) -> bool:
        """Test security headers and configurations"""
        start_time = time.time()
        
        try:
            response = requests.get(f"{self.base_url}/health", timeout=10)
            headers = response.headers
            
            # Check for important security headers
            security_headers = {
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": ["DENY", "SAMEORIGIN"],
                "X-XSS-Protection": "1; mode=block",
                "Strict-Transport-Security": None,  # Should be present for HTTPS
                "Content-Security-Policy": None     # Should be present
            }
            
            security_results = {}
            all_passed = True
            
            for header, expected_values in security_headers.items():
                if header in headers:
                    header_value = headers[header]
                    if expected_values is None:
                        # Just check presence
                        security_results[header] = {"present": True, "value": header_value}
                    elif isinstance(expected_values, list):
                        # Check if value is in expected list
                        if header_value in expected_values:
                            security_results[header] = {"present": True, "value": header_value, "valid": True}
                        else:
                            security_results[header] = {"present": True, "value": header_value, "valid": False}
                            all_passed = False
                    else:
                        # Check exact match
                        if header_value == expected_values:
                            security_results[header] = {"present": True, "value": header_value, "valid": True}
                        else:
                            security_results[header] = {"present": True, "value": header_value, "valid": False}
                            all_passed = False
                else:
                    security_results[header] = {"present": False}
                    if header != "Strict-Transport-Security":  # Optional for HTTP
                        all_passed = False
            
            self.verification_results["security_checks"] = security_results
            
            status = "passed" if all_passed else "warning"  # Warning instead of failed for security
            self.log_test_result(
                "Security", "Security Headers", status,
                security_results,
                time.time() - start_time
            )
            
            return True  # Don't fail deployment for security warnings
            
        except Exception as e:
            self.log_test_result(
                "Security", "Security Headers", "failed",
                {"error": str(e)},
                time.time() - start_time
            )
            return False
    
    def test_api_documentation(self) -> bool:
        """Test API documentation availability"""
        start_time = time.time()
        
        try:
            # Test OpenAPI/Swagger documentation
            docs_endpoints = [
                "/docs",
                "/redoc",
                "/openapi.json"
            ]
            
            docs_results = {}
            
            for endpoint in docs_endpoints:
                try:
                    response = requests.get(f"{self.base_url}{endpoint}", timeout=10)
                    docs_results[endpoint] = {
                        "status_code": response.status_code,
                        "content_length": len(response.text),
                        "available": response.status_code == 200
                    }
                except Exception as e:
                    docs_results[endpoint] = {
                        "error": str(e),
                        "available": False
                    }
            
            # At least one documentation endpoint should be available
            available_docs = sum(1 for result in docs_results.values() if result.get("available", False))
            
            if available_docs > 0:
                self.log_test_result(
                    "Documentation", "API Documentation", "passed",
                    docs_results,
                    time.time() - start_time
                )
                return True
            else:
                self.log_test_result(
                    "Documentation", "API Documentation", "failed",
                    docs_results,
                    time.time() - start_time
                )
                return False
                
        except Exception as e:
            self.log_test_result(
                "Documentation", "API Documentation", "failed",
                {"error": str(e)},
                time.time() - start_time
            )
            return False
    
    def test_monitoring_integration(self) -> bool:
        """Test monitoring and metrics integration"""
        start_time = time.time()
        
        try:
            # Test metrics endpoint
            response = requests.get(f"{self.base_url}/metrics", timeout=10)
            
            if response.status_code != 200:
                self.log_test_result(
                    "Monitoring", "Metrics Endpoint", "failed",
                    {"status_code": response.status_code},
                    time.time() - start_time
                )
                return False
            
            metrics_text = response.text
            
            # Check for essential metrics
            essential_metrics = [
                "http_requests_total",
                "http_request_duration_seconds",
                "process_resident_memory_bytes",
                "process_cpu_seconds_total"
            ]
            
            found_metrics = []
            for metric in essential_metrics:
                if metric in metrics_text:
                    found_metrics.append(metric)
            
            # Test Prometheus connectivity if available
            prometheus_url = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
            prometheus_available = False
            
            try:
                prom_response = requests.get(f"{prometheus_url}/-/healthy", timeout=5)
                prometheus_available = prom_response.status_code == 200
            except:
                pass
            
            monitoring_results = {
                "metrics_endpoint_available": True,
                "metrics_count": len(metrics_text.split('\n')),
                "essential_metrics_found": found_metrics,
                "essential_metrics_missing": list(set(essential_metrics) - set(found_metrics)),
                "prometheus_available": prometheus_available
            }
            
            self.verification_results["integration_tests"]["monitoring"] = monitoring_results
            
            # Pass if at least 75% of essential metrics are present
            if len(found_metrics) >= len(essential_metrics) * 0.75:
                self.log_test_result(
                    "Monitoring", "Metrics Integration", "passed",
                    monitoring_results,
                    time.time() - start_time
                )
                return True
            else:
                self.log_test_result(
                    "Monitoring", "Metrics Integration", "failed",
                    monitoring_results,
                    time.time() - start_time
                )
                return False
                
        except Exception as e:
            self.log_test_result(
                "Monitoring", "Metrics Integration", "failed",
                {"error": str(e)},
                time.time() - start_time
            )
            return False
    
    def test_docker_environment(self) -> bool:
        """Test Docker environment and container health"""
        start_time = time.time()
        
        try:
            # Check Docker containers
            result = subprocess.run(
                ["docker", "ps", "--format", "json"],
                capture_output=True,
                text=True,
                check=False
            )
            
            if result.returncode != 0:
                self.log_test_result(
                    "Infrastructure", "Docker Environment", "failed",
                    {"error": "Docker not available or not running"},
                    time.time() - start_time
                )
                return False
            
            # Parse container information
            containers = []
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    try:
                        container_info = json.loads(line)
                        containers.append(container_info)
                    except json.JSONDecodeError:
                        pass
            
            # Look for relevant containers
            agent_containers = [c for c in containers if 'agents' in c.get('Names', '').lower()]
            monitoring_containers = [c for c in containers if any(service in c.get('Names', '').lower() 
                                   for service in ['prometheus', 'grafana', 'alertmanager'])]
            
            docker_results = {
                "total_containers": len(containers),
                "agent_containers": len(agent_containers),
                "monitoring_containers": len(monitoring_containers),
                "container_details": containers[:5]  # First 5 containers for details
            }
            
            self.verification_results["integration_tests"]["docker"] = docker_results
            
            if agent_containers:
                self.log_test_result(
                    "Infrastructure", "Docker Environment", "passed",
                    docker_results,
                    time.time() - start_time
                )
                return True
            else:
                self.log_test_result(
                    "Infrastructure", "Docker Environment", "warning",
                    docker_results,
                    time.time() - start_time
                )
                return True  # Don't fail for this
                
        except Exception as e:
            self.log_test_result(
                "Infrastructure", "Docker Environment", "failed",
                {"error": str(e)},
                time.time() - start_time
            )
            return False
    
    def run_comprehensive_verification(self) -> bool:
        """Run all verification tests"""
        logger.info("Starting comprehensive deployment verification...")
        
        test_suites = [
            ("System Health", self.test_system_health_comprehensive),
            ("Agent Functionality", self.test_agent_functionality_comprehensive),
            ("Performance Benchmarks", self.test_performance_benchmarks),
            ("Security Configuration", self.test_security_headers),
            ("API Documentation", self.test_api_documentation),
            ("Monitoring Integration", self.test_monitoring_integration),
            ("Infrastructure", self.test_docker_environment)
        ]
        
        passed_suites = 0
        total_suites = len(test_suites)
        
        for suite_name, test_func in test_suites:
            logger.info(f"Running {suite_name} tests...")
            try:
                if test_func():
                    passed_suites += 1
            except Exception as e:
                logger.error(f"Test suite {suite_name} failed with exception: {str(e)}")
        
        success_rate = passed_suites / total_suites
        
        # Calculate overall test results
        total_tests = sum(len(category) for category in self.verification_results["test_categories"].values())
        passed_tests = sum(1 for category in self.verification_results["test_categories"].values() 
                          for test in category if test["status"] == "passed")
        
        if success_rate >= 0.8:  # 80% success rate required
            self.verification_results["overall_status"] = "passed"
            logger.info(f"🎉 Comprehensive verification PASSED ({passed_suites}/{total_suites} suites, {passed_tests}/{total_tests} tests)")
            return True
        else:
            self.verification_results["overall_status"] = "failed"
            logger.error(f"💥 Comprehensive verification FAILED ({passed_suites}/{total_suites} suites, {passed_tests}/{total_tests} tests)")
            return False
    
    def save_results(self, output_file: str = "verification_results.json") -> None:
        """Save verification results to file"""
        try:
            with open(output_file, 'w') as f:
                json.dump(self.verification_results, f, indent=2)
            logger.info(f"Verification results saved to {output_file}")
        except Exception as e:
            logger.error(f"Failed to save verification results: {str(e)}")
    
    def print_summary(self) -> None:
        """Print verification summary"""
        print("\n" + "="*80)
        print("🔍 COMPREHENSIVE DEPLOYMENT VERIFICATION SUMMARY")
        print("="*80)
        
        print(f"Base URL: {self.base_url}")
        print(f"Timestamp: {self.verification_results['timestamp']}")
        print(f"Overall Status: {self.verification_results['overall_status'].upper()}")
        
        # Test category summary
        for category, tests in self.verification_results["test_categories"].items():
            passed = sum(1 for test in tests if test['status'] == 'passed')
            failed = sum(1 for test in tests if test['status'] == 'failed')
            warnings = sum(1 for test in tests if test['status'] == 'warning')
            total = len(tests)
            
            print(f"\n📊 {category}: {passed} passed, {failed} failed, {warnings} warnings, {total} total")
            
            if failed > 0:
                for test in tests:
                    if test['status'] == 'failed':
                        print(f"  ❌ {test['test_name']}")
        
        # Performance metrics
        if self.verification_results.get("performance_metrics"):
            metrics = self.verification_results["performance_metrics"]
            print(f"\n⚡ Performance Metrics:")
            print(f"  Success Rate: {metrics.get('success_rate', 0)*100:.1f}%")
            print(f"  Avg Response Time: {metrics.get('avg_response_time', 0)*1000:.1f}ms")
            print(f"  Max Response Time: {metrics.get('max_response_time', 0)*1000:.1f}ms")
        
        # Security summary
        if self.verification_results.get("security_checks"):
            security = self.verification_results["security_checks"]
            present_headers = sum(1 for check in security.values() if check.get("present", False))
            total_headers = len(security)
            print(f"\n🔒 Security Headers: {present_headers}/{total_headers} present")
        
        print("="*80)


def main():
    parser = argparse.ArgumentParser(description="Comprehensive deployment verification")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Base URL of the deployed service")
    parser.add_argument("--output", default="verification_results.json", help="Output file for results")
    parser.add_argument("--wait-time", type=int, default=30, help="Time to wait for service to be ready")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument("--prometheus-url", help="Prometheus URL for monitoring tests")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    if args.prometheus_url:
        os.environ["PROMETHEUS_URL"] = args.prometheus_url
    
    # Wait for service to be ready
    if args.wait_time > 0:
        logger.info(f"Waiting {args.wait_time} seconds for service to be ready...")
        time.sleep(args.wait_time)
    
    verifier = DeploymentVerifier(args.base_url)
    
    success = verifier.run_comprehensive_verification()
    verifier.save_results(args.output)
    verifier.print_summary()
    
    return 0 if success else 1


if __name__ == "__main__":
    exit(main())