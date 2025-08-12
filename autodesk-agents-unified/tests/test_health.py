"""
Unit tests for health monitoring.
"""

import pytest
import asyncio
from unittest.mock import patch, MagicMock
from agent_core.health import HealthMonitor, HealthStatus, HealthCheck, SystemMetrics, ResponseTimeMetrics


class TestHealthMonitor:
    """Test health monitoring functionality."""
    
    def test_health_monitor_initialization(self):
        """Test health monitor initialization."""
        monitor = HealthMonitor(check_interval=60)
        
        assert monitor.check_interval == 60
        assert monitor._is_running is False
        assert len(monitor._health_checks) == 0
    
    @pytest.mark.asyncio
    async def test_start_stop_monitoring(self):
        """Test starting and stopping health monitoring."""
        monitor = HealthMonitor(check_interval=1)
        
        # Start monitoring
        await monitor.start_monitoring()
        assert monitor._is_running is True
        assert monitor._monitoring_task is not None
        
        # Stop monitoring
        await monitor.stop_monitoring()
        assert monitor._is_running is False
    
    @pytest.mark.asyncio
    async def test_system_health_check(self):
        """Test system health check."""
        monitor = HealthMonitor()
        
        health_check = await monitor.check_system_health()
        
        assert health_check.name == "system"
        assert isinstance(health_check.status, HealthStatus)
        assert health_check.duration_ms > 0
        assert health_check.metadata is not None
        assert "cpu_percent" in health_check.metadata
        assert "memory_percent" in health_check.metadata
    
    @pytest.mark.asyncio
    @patch('psutil.cpu_percent')
    @patch('psutil.virtual_memory')
    async def test_system_health_degraded(self, mock_memory, mock_cpu):
        """Test system health check with degraded status."""
        # Mock high resource usage
        mock_cpu.return_value = 85.0
        mock_memory.return_value = MagicMock(percent=90.0)
        
        monitor = HealthMonitor()
        health_check = await monitor.check_system_health()
        
        assert health_check.status == HealthStatus.DEGRADED
        assert "High resource usage" in health_check.message
    
    @pytest.mark.asyncio
    @patch('psutil.cpu_percent')
    @patch('psutil.virtual_memory')
    async def test_system_health_unhealthy(self, mock_memory, mock_cpu):
        """Test system health check with unhealthy status."""
        # Mock critical resource usage
        mock_cpu.return_value = 98.0
        mock_memory.return_value = MagicMock(percent=97.0)
        
        monitor = HealthMonitor()
        health_check = await monitor.check_system_health()
        
        assert health_check.status == HealthStatus.UNHEALTHY
        assert "Critical resource usage" in health_check.message
    
    @pytest.mark.asyncio
    async def test_agent_health_check(self):
        """Test agent health check."""
        monitor = HealthMonitor()
        
        health_check = await monitor.check_agent_health("model_properties")
        
        assert health_check.name == "agent_model_properties"
        assert health_check.status == HealthStatus.HEALTHY
        assert "model_properties" in health_check.message
    
    @pytest.mark.asyncio
    async def test_dependencies_health_check(self):
        """Test dependencies health check."""
        monitor = HealthMonitor()
        
        dependencies = await monitor.check_dependencies()
        
        assert "bedrock" in dependencies
        assert "opensearch" in dependencies
        assert isinstance(dependencies["bedrock"], HealthCheck)
        assert isinstance(dependencies["opensearch"], HealthCheck)
    
    def test_get_system_metrics(self):
        """Test getting system metrics."""
        monitor = HealthMonitor()
        
        metrics = monitor.get_system_metrics()
        
        assert isinstance(metrics, SystemMetrics)
        assert metrics.cpu_percent >= 0
        assert metrics.memory_percent >= 0
        assert metrics.memory_used_mb >= 0
        assert metrics.memory_total_mb > 0
        assert metrics.uptime_seconds >= 0
    
    def test_get_overall_health_no_checks(self):
        """Test overall health when no checks have been performed."""
        monitor = HealthMonitor()
        
        status = monitor.get_overall_health()
        
        assert status == HealthStatus.UNHEALTHY
    
    @pytest.mark.asyncio
    async def test_get_overall_health_with_checks(self):
        """Test overall health with various check results."""
        monitor = HealthMonitor()
        
        # Add healthy check
        await monitor.check_system_health()
        assert monitor.get_overall_health() in [HealthStatus.HEALTHY, HealthStatus.DEGRADED]
        
        # Add unhealthy check
        monitor._health_checks["test_unhealthy"] = HealthCheck(
            name="test_unhealthy",
            status=HealthStatus.UNHEALTHY,
            message="Test unhealthy",
            duration_ms=10.0,
            timestamp=monitor.get_system_metrics().timestamp
        )
        
        assert monitor.get_overall_health() == HealthStatus.UNHEALTHY
    
    @pytest.mark.asyncio
    async def test_health_summary(self):
        """Test getting comprehensive health summary."""
        monitor = HealthMonitor()
        
        # Perform some health checks
        await monitor.check_system_health()
        await monitor.check_agent_health("test_agent")
        
        summary = monitor.get_health_summary()
        
        assert "overall_status" in summary
        assert "checks" in summary
        assert "system_metrics" in summary
        assert "uptime_seconds" in summary
        assert len(summary["checks"]) >= 2
    
    @pytest.mark.asyncio
    async def test_monitoring_loop_error_handling(self):
        """Test that monitoring loop handles errors gracefully."""
        monitor = HealthMonitor(check_interval=0.1)
        
        # Mock an error in health checks
        with patch.object(monitor, '_perform_health_checks', side_effect=Exception("Test error")):
            await monitor.start_monitoring()
            
            # Let it run briefly
            await asyncio.sleep(0.2)
            
            # Should still be running despite errors
            assert monitor._is_running is True
            
            await monitor.stop_monitoring()
    
    def test_record_response_time(self):
        """Test recording response times."""
        monitor = HealthMonitor()
        
        # Record general response times
        monitor.record_response_time(100.0)
        monitor.record_response_time(200.0)
        monitor.record_response_time(150.0)
        
        assert len(monitor._response_times) == 3
        
        # Record agent-specific response times
        monitor.record_response_time(300.0, "agent", "model_properties")
        monitor.record_response_time(250.0, "agent", "model_properties")
        
        assert len(monitor._agent_response_times["model_properties"]) == 2
        
        # Record tool-specific response times
        monitor.record_response_time(50.0, "tool", "create_index")
        
        assert len(monitor._tool_response_times["create_index"]) == 1
    
    def test_get_response_time_metrics(self):
        """Test getting response time metrics."""
        monitor = HealthMonitor()
        
        # Add some response times
        response_times = [100.0, 200.0, 150.0, 300.0, 250.0]
        for rt in response_times:
            monitor.record_response_time(rt)
        
        metrics = monitor.get_response_time_metrics()
        
        assert isinstance(metrics, ResponseTimeMetrics)
        assert metrics.avg_response_time_ms == 200.0
        assert metrics.min_response_time_ms == 100.0
        assert metrics.max_response_time_ms == 300.0
        assert metrics.total_requests == 5
        assert metrics.p95_response_time_ms > 0
        assert metrics.p99_response_time_ms > 0
    
    def test_get_response_time_metrics_empty(self):
        """Test getting response time metrics when no data exists."""
        monitor = HealthMonitor()
        
        metrics = monitor.get_response_time_metrics()
        
        assert metrics is None
    
    def test_get_agent_response_time_metrics(self):
        """Test getting agent-specific response time metrics."""
        monitor = HealthMonitor()
        
        # Add agent-specific response times
        monitor.record_response_time(100.0, "agent", "test_agent")
        monitor.record_response_time(200.0, "agent", "test_agent")
        
        metrics = monitor.get_response_time_metrics("agent", "test_agent")
        
        assert isinstance(metrics, ResponseTimeMetrics)
        assert metrics.avg_response_time_ms == 150.0
        assert metrics.total_requests == 2
    
    def test_get_tool_response_time_metrics(self):
        """Test getting tool-specific response time metrics."""
        monitor = HealthMonitor()
        
        # Add tool-specific response times
        monitor.record_response_time(50.0, "tool", "test_tool")
        monitor.record_response_time(75.0, "tool", "test_tool")
        
        metrics = monitor.get_response_time_metrics("tool", "test_tool")
        
        assert isinstance(metrics, ResponseTimeMetrics)
        assert metrics.avg_response_time_ms == 62.5
        assert metrics.total_requests == 2
    
    def test_get_performance_summary(self):
        """Test getting performance summary."""
        monitor = HealthMonitor()
        
        # Add various response times
        monitor.record_response_time(100.0)
        monitor.record_response_time(200.0, "agent", "test_agent")
        monitor.record_response_time(50.0, "tool", "test_tool")
        
        summary = monitor.get_performance_summary()
        
        assert "overall" in summary
        assert "agents" in summary
        assert "tools" in summary
        assert "test_agent" in summary["agents"]
        assert "test_tool" in summary["tools"]
    
    def test_get_health_check_endpoint_data(self):
        """Test getting health check data for load balancers."""
        monitor = HealthMonitor()
        
        data = monitor.get_health_check_endpoint_data()
        
        assert "status" in data
        assert "healthy" in data
        assert "timestamp" in data
        assert "uptime" in data
        assert "version" in data
        assert isinstance(data["healthy"], bool)
    
    @pytest.mark.asyncio
    async def test_get_detailed_health_check(self):
        """Test getting detailed health check data."""
        monitor = HealthMonitor()
        
        # Perform some health checks
        await monitor.check_system_health()
        monitor.record_response_time(100.0)
        
        detailed = monitor.get_detailed_health_check()
        
        assert "overall_status" in detailed
        assert "checks" in detailed
        assert "system_metrics" in detailed
        assert "performance" in detailed
        assert "uptime_seconds" in detailed
    
    @pytest.mark.asyncio
    async def test_enhanced_health_summary_with_response_times(self):
        """Test that health summary includes response time metrics."""
        monitor = HealthMonitor()
        
        # Add response times and perform health check
        monitor.record_response_time(100.0)
        monitor.record_response_time(200.0)
        await monitor.check_system_health()
        
        summary = monitor.get_health_summary()
        
        assert "system_metrics" in summary
        assert "response_times" in summary["system_metrics"]
        
        response_times = summary["system_metrics"]["response_times"]
        if response_times:  # May be None if no response times recorded
            assert "avg_response_time_ms" in response_times
            assert "total_requests" in response_times