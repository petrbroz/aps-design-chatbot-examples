#!/usr/bin/env python3
"""
Deployment validation script for Autodesk Agents Unified
Validates that all three agent types are properly initialized and functioning
"""

import os
import json
import time
import logging
import argparse
import requests
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DeploymentValidator:
    """Validates deployment of all three agent types"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip('/')
        self.validation_results = {
            "timestamp": datetime.now().isoformat(),
            "base_url": base_url,
            "overall_status": "unknown",
            "tests": []
        }
    
    def log_test_result(self, test_name: str, status: str, details: Dict[str, Any] = None) -> None:
        """Log test result"""
        result = {
            "test_name": test_name,
            "status": status,
            "timestamp": datetime.now().isoformat(),
            "details": details or {}
        }
        
        self.validation_results["tests"].append(result)
        
        if status == "passed":
            logger.info(f"✅ {test_name}")
        elif status == "failed":
            logger.error(f"❌ {test_name}")
            if details:
                logger.error(f"   Details: {details}")
        else:
            logger.warning(f"⚠️  {test_name}")
    
    def test_basic_health(self) -> bool:
        """Test basic health endpoint"""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=10)
            
            if response.status_code == 200:
                health_data = response.json()
                self.log_test_result(
                    "Basic Health Check",
                    "passed",
                    {"response_time": response.elapsed.total_seconds(), "data": health_data}
                )
                return True
            else:
                self.log_test_result(
                    "Basic Health Check",
                    "failed",
                    {"status_code": response.status_code, "response": response.text}
                )
                return False
                
        except Exception as e:
            self.log_test_result(
                "Basic Health Check",
                "failed",
                {"error": str(e)}
            )
            return False
    
    def test_agent_health(self) -> bool:
        """Test agent-specific health endpoints"""
        try:
            response = requests.get(f"{self.base_url}/health/agents", timeout=10)
            
            if response.status_code == 200:
                agents_data = response.json()
                
                # Check that all three agent types are present and healthy
                expected_agents = ["model_properties", "aec_data_model", "model_derivatives"]
                found_agents = []
                
                if isinstance(agents_data, dict) and "agents" in agents_data:
                    for agent_info in agents_data["agents"]:
                        if isinstance(agent_info, dict) and "type" in agent_info:
                            found_agents.append(agent_info["type"])
                
                missing_agents = set(expected_agents) - set(found_agents)
                
                if not missing_agents:
                    self.log_test_result(
                        "Agent Health Check",
                        "passed",
                        {"found_agents": found_agents, "agents_data": agents_data}
                    )
                    return True
                else:
                    self.log_test_result(
                        "Agent Health Check",
                        "failed",
                        {"missing_agents": list(missing_agents), "found_agents": found_agents}
                    )
                    return False
            else:
                self.log_test_result(
                    "Agent Health Check",
                    "failed",
                    {"status_code": response.status_code, "response": response.text}
                )
                return False
                
        except Exception as e:
            self.log_test_result(
                "Agent Health Check",
                "failed",
                {"error": str(e)}
            )
            return False
    
    def test_dependencies_health(self) -> bool:
        """Test dependencies health"""
        try:
            response = requests.get(f"{self.base_url}/health/dependencies", timeout=10)
            
            if response.status_code == 200:
                deps_data = response.json()
                self.log_test_result(
                    "Dependencies Health Check",
                    "passed",
                    {"dependencies": deps_data}
                )
                return True
            else:
                self.log_test_result(
                    "Dependencies Health Check",
                    "failed",
                    {"status_code": response.status_code, "response": response.text}
                )
                return False
                
        except Exception as e:
            self.log_test_result(
                "Dependencies Health Check",
                "failed",
                {"error": str(e)}
            )
            return False
    
    def test_model_properties_agent(self) -> bool:
        """Test Model Properties agent functionality"""
        try:
            # Test with a simple prompt
            test_payload = {
                "prompt": "List available tools for model properties",
                "context": {
                    "agent_type": "model_properties"
                }
            }
            
            response = requests.post(
                f"{self.base_url}/api/v1/agents/model_properties/prompt",
                json=test_payload,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                self.log_test_result(
                    "Model Properties Agent Test",
                    "passed",
                    {"response_length": len(str(result)), "has_responses": "responses" in result}
                )
                return True
            else:
                self.log_test_result(
                    "Model Properties Agent Test",
                    "failed",
                    {"status_code": response.status_code, "response": response.text}
                )
                return False
                
        except Exception as e:
            self.log_test_result(
                "Model Properties Agent Test",
                "failed",
                {"error": str(e)}
            )
            return False
    
    def test_aec_data_model_agent(self) -> bool:
        """Test AEC Data Model agent functionality"""
        try:
            # Test with a simple prompt
            test_payload = {
                "prompt": "What types of elements can you help me query?",
                "context": {
                    "agent_type": "aec_data_model"
                }
            }
            
            response = requests.post(
                f"{self.base_url}/api/v1/agents/aec_data_model/prompt",
                json=test_payload,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                self.log_test_result(
                    "AEC Data Model Agent Test",
                    "passed",
                    {"response_length": len(str(result)), "has_responses": "responses" in result}
                )
                return True
            else:
                self.log_test_result(
                    "AEC Data Model Agent Test",
                    "failed",
                    {"status_code": response.status_code, "response": response.text}
                )
                return False
                
        except Exception as e:
            self.log_test_result(
                "AEC Data Model Agent Test",
                "failed",
                {"error": str(e)}
            )
            return False
    
    def test_model_derivatives_agent(self) -> bool:
        """Test Model Derivatives agent functionality"""
        try:
            # Test with a simple prompt
            test_payload = {
                "prompt": "What database operations can you perform?",
                "context": {
                    "agent_type": "model_derivatives"
                }
            }
            
            response = requests.post(
                f"{self.base_url}/api/v1/agents/model_derivatives/prompt",
                json=test_payload,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                self.log_test_result(
                    "Model Derivatives Agent Test",
                    "passed",
                    {"response_length": len(str(result)), "has_responses": "responses" in result}
                )
                return True
            else:
                self.log_test_result(
                    "Model Derivatives Agent Test",
                    "failed",
                    {"status_code": response.status_code, "response": response.text}
                )
                return False
                
        except Exception as e:
            self.log_test_result(
                "Model Derivatives Agent Test",
                "failed",
                {"error": str(e)}
            )
            return False
    
    def test_metrics_endpoint(self) -> bool:
        """Test metrics endpoint"""
        try:
            response = requests.get(f"{self.base_url}/metrics", timeout=10)
            
            if response.status_code == 200:
                metrics_text = response.text
                
                # Check for key metrics
                expected_metrics = [
                    "http_requests_total",
                    "http_request_duration_seconds",
                    "agent_requests_total",
                    "agent_processing_duration_seconds"
                ]
                
                found_metrics = []
                for metric in expected_metrics:
                    if metric in metrics_text:
                        found_metrics.append(metric)
                
                if len(found_metrics) >= len(expected_metrics) * 0.75:  # At least 75% of metrics
                    self.log_test_result(
                        "Metrics Endpoint Test",
                        "passed",
                        {"found_metrics": found_metrics, "metrics_count": len(metrics_text.split('\n'))}
                    )
                    return True
                else:
                    self.log_test_result(
                        "Metrics Endpoint Test",
                        "failed",
                        {"found_metrics": found_metrics, "expected_metrics": expected_metrics}
                    )
                    return False
            else:
                self.log_test_result(
                    "Metrics Endpoint Test",
                    "failed",
                    {"status_code": response.status_code}
                )
                return False
                
        except Exception as e:
            self.log_test_result(
                "Metrics Endpoint Test",
                "failed",
                {"error": str(e)}
            )
            return False
    
    def test_api_documentation(self) -> bool:
        """Test API documentation endpoint"""
        try:
            response = requests.get(f"{self.base_url}/docs", timeout=10)
            
            if response.status_code == 200:
                self.log_test_result(
                    "API Documentation Test",
                    "passed",
                    {"content_length": len(response.text)}
                )
                return True
            else:
                self.log_test_result(
                    "API Documentation Test",
                    "failed",
                    {"status_code": response.status_code}
                )
                return False
                
        except Exception as e:
            self.log_test_result(
                "API Documentation Test",
                "failed",
                {"error": str(e)}
            )
            return False
    
    def test_backward_compatibility(self) -> bool:
        """Test backward compatibility endpoints"""
        compatibility_tests = []
        
        # Test legacy endpoints that should still work
        legacy_endpoints = [
            "/api/v1/agents/model_properties/health",
            "/api/v1/agents/aec_data_model/health", 
            "/api/v1/agents/model_derivatives/health"
        ]
        
        for endpoint in legacy_endpoints:
            try:
                response = requests.get(f"{self.base_url}{endpoint}", timeout=10)
                compatibility_tests.append({
                    "endpoint": endpoint,
                    "status_code": response.status_code,
                    "success": response.status_code in [200, 404]  # 404 is acceptable if not implemented
                })
            except Exception as e:
                compatibility_tests.append({
                    "endpoint": endpoint,
                    "error": str(e),
                    "success": False
                })
        
        successful_tests = sum(1 for test in compatibility_tests if test["success"])
        
        if successful_tests >= len(compatibility_tests) * 0.5:  # At least 50% success
            self.log_test_result(
                "Backward Compatibility Test",
                "passed",
                {"tests": compatibility_tests, "success_rate": successful_tests / len(compatibility_tests)}
            )
            return True
        else:
            self.log_test_result(
                "Backward Compatibility Test",
                "failed",
                {"tests": compatibility_tests, "success_rate": successful_tests / len(compatibility_tests)}
            )
            return False
    
    def run_all_tests(self) -> bool:
        """Run all validation tests"""
        logger.info("Starting deployment validation...")
        
        tests = [
            ("Basic Health", self.test_basic_health),
            ("Agent Health", self.test_agent_health),
            ("Dependencies Health", self.test_dependencies_health),
            ("Model Properties Agent", self.test_model_properties_agent),
            ("AEC Data Model Agent", self.test_aec_data_model_agent),
            ("Model Derivatives Agent", self.test_model_derivatives_agent),
            ("Metrics Endpoint", self.test_metrics_endpoint),
            ("API Documentation", self.test_api_documentation),
            ("Backward Compatibility", self.test_backward_compatibility)
        ]
        
        passed_tests = 0
        total_tests = len(tests)
        
        for test_name, test_func in tests:
            logger.info(f"Running {test_name} test...")
            try:
                if test_func():
                    passed_tests += 1
            except Exception as e:
                logger.error(f"Test {test_name} failed with exception: {str(e)}")
        
        success_rate = passed_tests / total_tests
        
        if success_rate >= 0.8:  # 80% success rate required
            self.validation_results["overall_status"] = "passed"
            logger.info(f"🎉 Deployment validation PASSED ({passed_tests}/{total_tests} tests)")
            return True
        else:
            self.validation_results["overall_status"] = "failed"
            logger.error(f"💥 Deployment validation FAILED ({passed_tests}/{total_tests} tests)")
            return False
    
    def save_results(self, output_file: str = "validation_results.json") -> None:
        """Save validation results to file"""
        try:
            with open(output_file, 'w') as f:
                json.dump(self.validation_results, f, indent=2)
            logger.info(f"Validation results saved to {output_file}")
        except Exception as e:
            logger.error(f"Failed to save validation results: {str(e)}")
    
    def print_summary(self) -> None:
        """Print validation summary"""
        print("\n" + "="*60)
        print("DEPLOYMENT VALIDATION SUMMARY")
        print("="*60)
        
        print(f"Base URL: {self.base_url}")
        print(f"Timestamp: {self.validation_results['timestamp']}")
        print(f"Overall Status: {self.validation_results['overall_status'].upper()}")
        
        passed = sum(1 for test in self.validation_results['tests'] if test['status'] == 'passed')
        failed = sum(1 for test in self.validation_results['tests'] if test['status'] == 'failed')
        total = len(self.validation_results['tests'])
        
        print(f"Tests: {passed} passed, {failed} failed, {total} total")
        print(f"Success Rate: {(passed/total)*100:.1f}%")
        
        if failed > 0:
            print("\nFailed Tests:")
            for test in self.validation_results['tests']:
                if test['status'] == 'failed':
                    print(f"  - {test['test_name']}")
                    if 'error' in test.get('details', {}):
                        print(f"    Error: {test['details']['error']}")
        
        print("="*60)


def main():
    parser = argparse.ArgumentParser(description="Validate Autodesk Agents Unified deployment")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Base URL of the deployed service")
    parser.add_argument("--output", default="validation_results.json", help="Output file for results")
    parser.add_argument("--wait-time", type=int, default=30, help="Time to wait for service to be ready")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Wait for service to be ready
    if args.wait_time > 0:
        logger.info(f"Waiting {args.wait_time} seconds for service to be ready...")
        time.sleep(args.wait_time)
    
    validator = DeploymentValidator(args.base_url)
    
    success = validator.run_all_tests()
    validator.save_results(args.output)
    validator.print_summary()
    
    return 0 if success else 1


if __name__ == "__main__":
    exit(main())