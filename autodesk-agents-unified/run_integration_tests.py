#!/usr/bin/env python3
"""
Integration and End-to-End Test Runner

This script runs the comprehensive integration and end-to-end tests for the
unified agent system. It provides options to run different test suites and
generates detailed reports.
"""

import os
import sys
import argparse
import subprocess
import time
from pathlib import Path
from typing import List, Dict, Any


def run_command(cmd: List[str], cwd: str = None) -> Dict[str, Any]:
    """Run a command and return the result."""
    print(f"Running: {' '.join(cmd)}")
    start_time = time.time()
    
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        execution_time = time.time() - start_time
        
        return {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "execution_time": execution_time
        }
    
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": "Command timed out after 5 minutes",
            "execution_time": time.time() - start_time
        }
    
    except Exception as e:
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": str(e),
            "execution_time": time.time() - start_time
        }


def run_test_suite(test_type: str, test_files: List[str] = None, verbose: bool = False) -> Dict[str, Any]:
    """Run a specific test suite."""
    print(f"\n{'='*60}")
    print(f"Running {test_type.upper()} Tests")
    print(f"{'='*60}")
    
    # Base pytest command
    cmd = ["python", "-m", "pytest"]
    
    # Add verbosity
    if verbose:
        cmd.extend(["-v", "-s"])
    
    # Add test files or markers
    if test_files:
        cmd.extend(test_files)
    else:
        # Use markers to select test types
        if test_type == "integration":
            cmd.extend(["-m", "integration"])
        elif test_type == "e2e":
            cmd.extend(["-m", "e2e"])
        elif test_type == "external":
            cmd.extend(["-m", "external"])
        elif test_type == "all":
            cmd.extend(["tests/"])
    
    # Add coverage reporting
    cmd.extend([
        "--cov=agent_core",
        "--cov-report=term-missing",
        "--cov-report=html:htmlcov",
        "--cov-report=xml:coverage.xml"
    ])
    
    # Add JUnit XML output for CI
    cmd.extend(["--junit-xml=test-results.xml"])
    
    # Run the tests
    result = run_command(cmd, cwd=".")
    
    # Print results
    if result["success"]:
        print(f"\n✅ {test_type.upper()} tests PASSED")
        print(f"Execution time: {result['execution_time']:.2f} seconds")
    else:
        print(f"\n❌ {test_type.upper()} tests FAILED")
        print(f"Return code: {result['returncode']}")
        print(f"Execution time: {result['execution_time']:.2f} seconds")
        
        if result["stderr"]:
            print(f"\nErrors:\n{result['stderr']}")
    
    # Always show test output for debugging
    if result["stdout"]:
        print(f"\nTest Output:\n{result['stdout']}")
    
    return result


def check_dependencies() -> bool:
    """Check if required dependencies are installed."""
    print("Checking dependencies...")
    
    required_packages = [
        "pytest",
        "pytest-asyncio", 
        "pytest-cov",
        "httpx",
        "fastapi"
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package.replace("-", "_"))
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        print(f"❌ Missing required packages: {', '.join(missing_packages)}")
        print("Install them with: pip install " + " ".join(missing_packages))
        return False
    
    print("✅ All dependencies are installed")
    return True


def setup_test_environment():
    """Setup test environment variables and directories."""
    print("Setting up test environment...")
    
    # Set environment variables for testing
    os.environ["TESTING"] = "true"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
    os.environ["OPENSEARCH_ENDPOINT"] = "https://test-opensearch.amazonaws.com"
    
    # Create test directories
    test_dirs = [
        "test_results",
        "htmlcov",
        "/tmp/test_agent_cache"
    ]
    
    for dir_path in test_dirs:
        Path(dir_path).mkdir(parents=True, exist_ok=True)
    
    print("✅ Test environment setup complete")


def generate_test_report(results: Dict[str, Dict[str, Any]]):
    """Generate a comprehensive test report."""
    print(f"\n{'='*60}")
    print("TEST EXECUTION SUMMARY")
    print(f"{'='*60}")
    
    total_time = 0
    passed_suites = 0
    failed_suites = 0
    
    for suite_name, result in results.items():
        status = "PASSED" if result["success"] else "FAILED"
        print(f"{suite_name:20} | {status:6} | {result['execution_time']:6.2f}s")
        
        total_time += result["execution_time"]
        if result["success"]:
            passed_suites += 1
        else:
            failed_suites += 1
    
    print(f"{'='*60}")
    print(f"Total Suites: {len(results)}")
    print(f"Passed: {passed_suites}")
    print(f"Failed: {failed_suites}")
    print(f"Total Time: {total_time:.2f} seconds")
    
    # Generate detailed report file
    report_file = "test_execution_report.txt"
    with open(report_file, "w") as f:
        f.write("Integration and End-to-End Test Execution Report\n")
        f.write("=" * 50 + "\n\n")
        
        for suite_name, result in results.items():
            f.write(f"Test Suite: {suite_name}\n")
            f.write(f"Status: {'PASSED' if result['success'] else 'FAILED'}\n")
            f.write(f"Execution Time: {result['execution_time']:.2f} seconds\n")
            f.write(f"Return Code: {result['returncode']}\n")
            
            if result["stdout"]:
                f.write(f"\nOutput:\n{result['stdout']}\n")
            
            if result["stderr"]:
                f.write(f"\nErrors:\n{result['stderr']}\n")
            
            f.write("\n" + "-" * 40 + "\n\n")
    
    print(f"\nDetailed report saved to: {report_file}")
    
    return failed_suites == 0


def main():
    """Main test runner function."""
    parser = argparse.ArgumentParser(
        description="Run integration and end-to-end tests for the unified agent system"
    )
    
    parser.add_argument(
        "--type",
        choices=["integration", "e2e", "external", "all", "final"],
        default="all",
        help="Type of tests to run"
    )
    
    parser.add_argument(
        "--files",
        nargs="*",
        help="Specific test files to run"
    )
    
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Run tests in verbose mode"
    )
    
    parser.add_argument(
        "--skip-deps",
        action="store_true",
        help="Skip dependency check"
    )
    
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run only quick tests (skip slow/external tests)"
    )
    
    parser.add_argument(
        "--final-system-test",
        action="store_true",
        help="Run comprehensive final system testing"
    )
    
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Base URL for system testing"
    )
    
    args = parser.parse_args()
    
    print("Unified Agent System - Integration & E2E Test Runner")
    print("=" * 60)
    
    # Check dependencies
    if not args.skip_deps and not check_dependencies():
        sys.exit(1)
    
    # Setup test environment
    setup_test_environment()
    
    # Run final system testing if requested
    if args.final_system_test or args.type == "final":
        print("\n🚀 Running Final System Testing...")
        
        # Run the comprehensive final system testing script
        final_test_cmd = [
            "python", "scripts/final_system_testing.py",
            "--base-url", args.base_url,
            "--output", "final_system_test_results.json"
        ]
        
        if args.verbose:
            final_test_cmd.append("--verbose")
        
        result = run_command(final_test_cmd, cwd=".")
        
        if result["success"]:
            print("🎉 Final System Testing PASSED!")
            return 0
        else:
            print("💥 Final System Testing FAILED!")
            print(f"Error: {result['stderr']}")
            return 1
    
    # Determine which tests to run
    test_suites = {}
    
    if args.type == "all":
        if not args.quick:
            test_suites = {
                "Agent Integration": {
                    "files": ["tests/test_agent_integration.py"],
                    "type": "integration"
                },
                "External Services": {
                    "files": ["tests/test_external_services_integration.py"],
                    "type": "external"
                },
                "End-to-End API": {
                    "files": ["tests/test_end_to_end_api.py"],
                    "type": "e2e"
                },
                "API Gateway Middleware": {
                    "files": ["tests/test_api_gateway_middleware.py"],
                    "type": "e2e"
                }
            }
        else:
            # Quick test suite - skip external and slow tests
            test_suites = {
                "Agent Integration (Quick)": {
                    "files": ["tests/test_agent_integration.py", "-m", "not slow and not external"],
                    "type": "integration"
                },
                "End-to-End API (Quick)": {
                    "files": ["tests/test_end_to_end_api.py", "-m", "not slow"],
                    "type": "e2e"
                }
            }
    else:
        # Single test type
        if args.files:
            test_suites[f"{args.type.title()} Tests"] = {
                "files": args.files,
                "type": args.type
            }
        else:
            test_suites[f"{args.type.title()} Tests"] = {
                "files": None,
                "type": args.type
            }
    
    # Run test suites
    results = {}
    
    for suite_name, suite_config in test_suites.items():
        result = run_test_suite(
            suite_config["type"],
            suite_config["files"],
            args.verbose
        )
        results[suite_name] = result
    
    # Generate report
    all_passed = generate_test_report(results)
    
    # Exit with appropriate code
    if all_passed:
        print("\n🎉 All tests passed!")
        sys.exit(0)
    else:
        print("\n💥 Some tests failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()