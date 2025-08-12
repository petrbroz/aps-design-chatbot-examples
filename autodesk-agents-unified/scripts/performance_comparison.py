#!/usr/bin/env python3
"""
Performance Comparison Script

Compares performance of the unified agent system against original implementations
to validate that performance benchmarks are met or exceeded.
"""

import os
import json
import time
import logging
import argparse
import statistics
from typing import Dict, List, Any, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import psutil

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PerformanceComparator:
    """Compare performance between unified and original implementations"""
    
    def __init__(self, unified_url: str, original_urls: Dict[str, str] = None):
        self.unified_url = unified_url.rstrip('/')
        self.original_urls = original_urls or {}
        
        # Default original implementation URLs (if running locally)
        self.default_original_urls = {
            "model_properties": "http://localhost:8001",
            "aec_data_model": "http://localhost:8002", 
            "model_derivatives": "http://localhost:8003"
        }
        
        self.results = {
            "timestamp": datetime.now().isoformat(),
            "unified_url": unified_url,
            "original_urls": self.original_urls,
            "performance_comparisons": {},
            "summary": {}
        }
    
    def benchmark_endpoint(self, url: str, endpoint: str, payload: Dict[str, Any], 
                          num_requests: int = 10) -> Dict[str, Any]:
        """Benchmark a specific endpoint"""
        response_times = []
        success_count = 0
        error_count = 0
        status_codes = []
        
        # Monitor system resources
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        start_time = time.time()
        
        for i in range(num_requests):
            request_start = time.time()
            
            try:
                response = requests.post(
                    f"{url}{endpoint}",
                    json=payload,
                    timeout=30
                )
                
                request_time = time.time() - request_start
                response_times.append(request_time)
                status_codes.append(response.status_code)
                
                if response.status_code == 200:
                    success_count += 1
                else:
                    error_count += 1
                    
            except Exception as e:
                error_count += 1
                response_times.append(30.0)  # Timeout value
                status_codes.append(0)  # Error code
                logger.warning(f"Request {i} failed: {e}")
        
        total_time = time.time() - start_time
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Calculate statistics
        if response_times:
            avg_response_time = statistics.mean(response_times)
            min_response_time = min(response_times)
            max_response_time = max(response_times)
            median_response_time = statistics.median(response_times)
            
            # Calculate percentiles
            sorted_times = sorted(response_times)
            p95_response_time = sorted_times[int(0.95 * len(sorted_times))]
            p99_response_time = sorted_times[int(0.99 * len(sorted_times))]
        else:
            avg_response_time = min_response_time = max_response_time = 0
            median_response_time = p95_response_time = p99_response_time = 0
        
        return {
            "num_requests": num_requests,
            "success_count": success_count,
            "error_count": error_count,
            "success_rate": success_count / num_requests,
            "avg_response_time": avg_response_time,
            "min_response_time": min_response_time,
            "max_response_time": max_response_time,
            "median_response_time": median_response_time,
            "p95_response_time": p95_response_time,
            "p99_response_time": p99_response_time,
            "total_time": total_time,
            "throughput": success_count / total_time,
            "memory_usage_mb": final_memory - initial_memory,
            "status_codes": status_codes,
            "response_times": response_times
        }
    
    def compare_agent_performance(self, agent_type: str, test_scenarios: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Compare performance for a specific agent type"""
        logger.info(f"🔍 Comparing performance for {agent_type} agent...")
        
        # Unified system endpoints
        unified_endpoints = {
            "model_properties": "/api/v1/model-properties/prompt",
            "aec_data_model": "/api/v1/aec-data-model/prompt",
            "model_derivatives": "/api/v1/model-derivatives/prompt"
        }
        
        # Original system endpoints (assuming same structure)
        original_endpoints = {
            "model_properties": "/prompt",
            "aec_data_model": "/prompt", 
            "model_derivatives": "/prompt"
        }
        
        unified_endpoint = unified_endpoints.get(agent_type)
        original_endpoint = original_endpoints.get(agent_type)
        
        if not unified_endpoint:
            logger.error(f"Unknown agent type: {agent_type}")
            return {}
        
        comparison_results = {
            "agent_type": agent_type,
            "scenarios": {},
            "summary": {}
        }
        
        # Test each scenario
        for i, scenario in enumerate(test_scenarios):
            scenario_name = scenario.get("name", f"scenario_{i}")
            payload = scenario["payload"]
            
            logger.info(f"  Testing scenario: {scenario_name}")
            
            # Benchmark unified system
            unified_results = self.benchmark_endpoint(
                self.unified_url, unified_endpoint, payload
            )
            
            # Benchmark original system (if available)
            original_results = None
            original_url = self.original_urls.get(agent_type) or self.default_original_urls.get(agent_type)
            
            if original_url:
                try:
                    # Check if original system is available
                    health_response = requests.get(f"{original_url}/health", timeout=5)
                    if health_response.status_code == 200:
                        original_results = self.benchmark_endpoint(
                            original_url, original_endpoint, payload
                        )
                    else:
                        logger.warning(f"Original {agent_type} system not available at {original_url}")
                except Exception as e:
                    logger.warning(f"Cannot connect to original {agent_type} system: {e}")
            
            # Store results
            comparison_results["scenarios"][scenario_name] = {
                "unified": unified_results,
                "original": original_results,
                "comparison": self._compare_metrics(unified_results, original_results) if original_results else None
            }
        
        # Calculate summary
        comparison_results["summary"] = self._calculate_agent_summary(comparison_results["scenarios"])
        
        return comparison_results
    
    def _compare_metrics(self, unified: Dict[str, Any], original: Dict[str, Any]) -> Dict[str, Any]:
        """Compare metrics between unified and original implementations"""
        comparison = {}
        
        metrics_to_compare = [
            "avg_response_time", "min_response_time", "max_response_time",
            "p95_response_time", "p99_response_time", "success_rate", "throughput"
        ]
        
        for metric in metrics_to_compare:
            unified_value = unified.get(metric, 0)
            original_value = original.get(metric, 0)
            
            if original_value > 0:
                improvement_ratio = (original_value - unified_value) / original_value
                improvement_percent = improvement_ratio * 100
            else:
                improvement_ratio = 0
                improvement_percent = 0
            
            comparison[metric] = {
                "unified": unified_value,
                "original": original_value,
                "improvement_ratio": improvement_ratio,
                "improvement_percent": improvement_percent,
                "better": self._is_better(metric, unified_value, original_value)
            }
        
        return comparison
    
    def _is_better(self, metric: str, unified_value: float, original_value: float) -> bool:
        """Determine if unified value is better than original"""
        # For response times, lower is better
        if "response_time" in metric:
            return unified_value <= original_value * 1.1  # Allow 10% tolerance
        
        # For success rate and throughput, higher is better
        if metric in ["success_rate", "throughput"]:
            return unified_value >= original_value * 0.9  # Allow 10% tolerance
        
        return unified_value >= original_value
    
    def _calculate_agent_summary(self, scenarios: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate summary statistics for an agent"""
        unified_metrics = []
        original_metrics = []
        comparisons = []
        
        for scenario_name, scenario_data in scenarios.items():
            unified_metrics.append(scenario_data["unified"])
            
            if scenario_data["original"]:
                original_metrics.append(scenario_data["original"])
                
            if scenario_data["comparison"]:
                comparisons.append(scenario_data["comparison"])
        
        summary = {
            "total_scenarios": len(scenarios),
            "scenarios_with_comparison": len(comparisons)
        }
        
        if unified_metrics:
            # Calculate average unified metrics
            summary["unified_avg"] = {
                "avg_response_time": statistics.mean([m["avg_response_time"] for m in unified_metrics]),
                "success_rate": statistics.mean([m["success_rate"] for m in unified_metrics]),
                "throughput": statistics.mean([m["throughput"] for m in unified_metrics])
            }
        
        if original_metrics:
            # Calculate average original metrics
            summary["original_avg"] = {
                "avg_response_time": statistics.mean([m["avg_response_time"] for m in original_metrics]),
                "success_rate": statistics.mean([m["success_rate"] for m in original_metrics]),
                "throughput": statistics.mean([m["throughput"] for m in original_metrics])
            }
        
        if comparisons:
            # Calculate overall improvement
            avg_improvements = {}
            better_count = {}
            
            for comparison in comparisons:
                for metric, data in comparison.items():
                    if metric not in avg_improvements:
                        avg_improvements[metric] = []
                        better_count[metric] = 0
                    
                    avg_improvements[metric].append(data["improvement_percent"])
                    if data["better"]:
                        better_count[metric] += 1
            
            summary["overall_improvement"] = {}
            for metric, improvements in avg_improvements.items():
                summary["overall_improvement"][metric] = {
                    "avg_improvement_percent": statistics.mean(improvements),
                    "better_scenarios": better_count[metric],
                    "total_scenarios": len(improvements),
                    "better_rate": better_count[metric] / len(improvements)
                }
        
        return summary
    
    def run_comprehensive_comparison(self) -> bool:
        """Run comprehensive performance comparison"""
        logger.info("🚀 Starting comprehensive performance comparison...")
        
        # Define test scenarios for each agent type
        test_scenarios = {
            "model_properties": [
                {
                    "name": "list_properties",
                    "payload": {
                        "prompt": "List all available properties for walls",
                        "project_id": "b.test_project",
                        "version_id": "test_version"
                    }
                },
                {
                    "name": "create_index",
                    "payload": {
                        "prompt": "Create an index for this design",
                        "project_id": "b.test_project", 
                        "version_id": "test_version"
                    }
                },
                {
                    "name": "query_properties",
                    "payload": {
                        "prompt": "Find all elements with height greater than 3 meters",
                        "project_id": "b.test_project",
                        "version_id": "test_version"
                    }
                }
            ],
            "aec_data_model": [
                {
                    "name": "find_elements",
                    "payload": {
                        "prompt": "Find all door elements in the design",
                        "element_group_id": "test_element_group"
                    }
                },
                {
                    "name": "element_properties",
                    "payload": {
                        "prompt": "Show properties for wall elements",
                        "element_group_id": "test_element_group"
                    }
                },
                {
                    "name": "complex_query",
                    "payload": {
                        "prompt": "Find all structural elements with area greater than 10 square meters",
                        "element_group_id": "test_element_group"
                    }
                }
            ],
            "model_derivatives": [
                {
                    "name": "setup_database",
                    "payload": {
                        "prompt": "Setup the database for this model",
                        "urn": "dXJuOmFkc2sud2lwcHJvZDpmcy5maWxlOnZmLlUyTVk1UEFwUi1PV2l2TS1Zam9BQXc_dmVyc2lvbj0x"
                    }
                },
                {
                    "name": "sql_query",
                    "payload": {
                        "prompt": "Execute SQL query to find elements with specific properties",
                        "urn": "dXJuOmFkc2sud2lwcHJvZDpmcy5maWxlOnZmLlUyTVk1UEFwUi1PV2l2TS1Zam9BQXc_dmVyc2lvbj0x"
                    }
                },
                {
                    "name": "complex_analysis",
                    "payload": {
                        "prompt": "Perform complex analysis on building elements",
                        "urn": "dXJuOmFkc2sud2lwcHJvZDpmcy5maWxlOnZmLlUyTVk1UEFwUi1PV2l2TS1Zam9BQXc_dmVyc2lvbj0x"
                    }
                }
            ]
        }
        
        # Run comparisons for each agent type
        all_passed = True
        
        for agent_type, scenarios in test_scenarios.items():
            try:
                comparison_result = self.compare_agent_performance(agent_type, scenarios)
                self.results["performance_comparisons"][agent_type] = comparison_result
                
                # Evaluate if performance is acceptable
                summary = comparison_result.get("summary", {})
                
                if "overall_improvement" in summary:
                    # Check if performance is better or within acceptable range
                    response_time_improvement = summary["overall_improvement"].get("avg_response_time", {})
                    success_rate_improvement = summary["overall_improvement"].get("success_rate", {})
                    
                    response_time_acceptable = response_time_improvement.get("better_rate", 0) >= 0.7  # 70% of scenarios
                    success_rate_acceptable = success_rate_improvement.get("better_rate", 0) >= 0.8   # 80% of scenarios
                    
                    if response_time_acceptable and success_rate_acceptable:
                        logger.info(f"✅ {agent_type} performance comparison PASSED")
                    else:
                        logger.warning(f"⚠️  {agent_type} performance comparison needs attention")
                        all_passed = False
                else:
                    # No original system to compare against - check unified performance
                    unified_avg = summary.get("unified_avg", {})
                    avg_response_time = unified_avg.get("avg_response_time", 0)
                    success_rate = unified_avg.get("success_rate", 0)
                    
                    if avg_response_time <= 5.0 and success_rate >= 0.9:  # 5s max, 90% success
                        logger.info(f"✅ {agent_type} performance baseline PASSED")
                    else:
                        logger.warning(f"⚠️  {agent_type} performance baseline needs attention")
                        all_passed = False
                        
            except Exception as e:
                logger.error(f"❌ Performance comparison failed for {agent_type}: {e}")
                all_passed = False
        
        # Calculate overall summary
        self.results["summary"] = self._calculate_overall_summary()
        
        return all_passed
    
    def _calculate_overall_summary(self) -> Dict[str, Any]:
        """Calculate overall performance summary"""
        summary = {
            "total_agents": len(self.results["performance_comparisons"]),
            "agents_with_comparison": 0,
            "overall_performance": "unknown"
        }
        
        agent_summaries = []
        
        for agent_type, comparison_data in self.results["performance_comparisons"].items():
            agent_summary = comparison_data.get("summary", {})
            agent_summaries.append(agent_summary)
            
            if "overall_improvement" in agent_summary:
                summary["agents_with_comparison"] += 1
        
        if agent_summaries:
            # Calculate overall metrics
            all_response_times = []
            all_success_rates = []
            all_throughputs = []
            
            for agent_summary in agent_summaries:
                unified_avg = agent_summary.get("unified_avg", {})
                if unified_avg:
                    all_response_times.append(unified_avg.get("avg_response_time", 0))
                    all_success_rates.append(unified_avg.get("success_rate", 0))
                    all_throughputs.append(unified_avg.get("throughput", 0))
            
            if all_response_times:
                summary["overall_unified_performance"] = {
                    "avg_response_time": statistics.mean(all_response_times),
                    "avg_success_rate": statistics.mean(all_success_rates),
                    "avg_throughput": statistics.mean(all_throughputs)
                }
                
                # Determine overall performance rating
                avg_response_time = summary["overall_unified_performance"]["avg_response_time"]
                avg_success_rate = summary["overall_unified_performance"]["avg_success_rate"]
                
                if avg_response_time <= 3.0 and avg_success_rate >= 0.95:
                    summary["overall_performance"] = "excellent"
                elif avg_response_time <= 5.0 and avg_success_rate >= 0.9:
                    summary["overall_performance"] = "good"
                elif avg_response_time <= 10.0 and avg_success_rate >= 0.8:
                    summary["overall_performance"] = "acceptable"
                else:
                    summary["overall_performance"] = "needs_improvement"
        
        return summary
    
    def save_results(self, output_file: str = "performance_comparison_results.json") -> None:
        """Save performance comparison results"""
        try:
            with open(output_file, 'w') as f:
                json.dump(self.results, f, indent=2, default=str)
            
            logger.info(f"Performance comparison results saved to {output_file}")
            
        except Exception as e:
            logger.error(f"Failed to save results: {e}")
    
    def print_summary(self) -> None:
        """Print performance comparison summary"""
        print("\n" + "="*80)
        print("⚡ PERFORMANCE COMPARISON SUMMARY")
        print("="*80)
        
        print(f"Timestamp: {self.results['timestamp']}")
        print(f"Unified System: {self.unified_url}")
        
        summary = self.results.get("summary", {})
        print(f"Overall Performance: {summary.get('overall_performance', 'unknown').upper()}")
        
        if "overall_unified_performance" in summary:
            perf = summary["overall_unified_performance"]
            print(f"Average Response Time: {perf['avg_response_time']*1000:.1f}ms")
            print(f"Average Success Rate: {perf['avg_success_rate']*100:.1f}%")
            print(f"Average Throughput: {perf['avg_throughput']:.1f} req/s")
        
        print(f"\n📊 Agent Comparisons:")
        
        for agent_type, comparison_data in self.results["performance_comparisons"].items():
            print(f"\n  {agent_type.upper()}:")
            
            summary_data = comparison_data.get("summary", {})
            
            if "unified_avg" in summary_data:
                unified = summary_data["unified_avg"]
                print(f"    Unified - Response Time: {unified['avg_response_time']*1000:.1f}ms, Success Rate: {unified['success_rate']*100:.1f}%")
            
            if "original_avg" in summary_data:
                original = summary_data["original_avg"]
                print(f"    Original - Response Time: {original['avg_response_time']*1000:.1f}ms, Success Rate: {original['success_rate']*100:.1f}%")
            
            if "overall_improvement" in summary_data:
                improvements = summary_data["overall_improvement"]
                response_time_imp = improvements.get("avg_response_time", {})
                success_rate_imp = improvements.get("success_rate", {})
                
                print(f"    Improvement - Response Time: {response_time_imp.get('avg_improvement_percent', 0):.1f}%, Success Rate: {success_rate_imp.get('avg_improvement_percent', 0):.1f}%")
        
        print("="*80)


def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="Performance Comparison Tool")
    parser.add_argument("--unified-url", default="http://localhost:8000", help="Unified system URL")
    parser.add_argument("--original-mp-url", help="Original Model Properties system URL")
    parser.add_argument("--original-aec-url", help="Original AEC Data Model system URL") 
    parser.add_argument("--original-md-url", help="Original Model Derivatives system URL")
    parser.add_argument("--output", default="performance_comparison_results.json", help="Output file")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Build original URLs dictionary
    original_urls = {}
    if args.original_mp_url:
        original_urls["model_properties"] = args.original_mp_url
    if args.original_aec_url:
        original_urls["aec_data_model"] = args.original_aec_url
    if args.original_md_url:
        original_urls["model_derivatives"] = args.original_md_url
    
    # Initialize comparator
    comparator = PerformanceComparator(args.unified_url, original_urls)
    
    # Run comparison
    success = comparator.run_comprehensive_comparison()
    
    # Save results and print summary
    comparator.save_results(args.output)
    comparator.print_summary()
    
    return 0 if success else 1


if __name__ == "__main__":
    exit(main())