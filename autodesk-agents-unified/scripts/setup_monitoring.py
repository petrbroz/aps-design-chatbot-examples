#!/usr/bin/env python3
"""
Monitoring and alerting setup script for Autodesk Agents Unified
Sets up comprehensive monitoring, logging, and alerting infrastructure
"""

import os
import json
import yaml
import logging
import argparse
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MonitoringSetup:
    """Sets up monitoring and alerting infrastructure"""
    
    def __init__(self, environment: str, config_dir: str = "monitoring"):
        self.environment = environment
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(exist_ok=True)
    
    def create_prometheus_config(self) -> None:
        """Create Prometheus configuration"""
        logger.info("Creating Prometheus configuration...")
        
        prometheus_config = {
            "global": {
                "scrape_interval": "15s",
                "evaluation_interval": "15s"
            },
            "rule_files": [
                "alert_rules.yml"
            ],
            "alertmanager_configs": [
                {
                    "static_configs": [
                        {"targets": ["alertmanager:9093"]}
                    ]
                }
            ],
            "scrape_configs": [
                {
                    "job_name": "agents-unified",
                    "static_configs": [
                        {"targets": ["agents-unified:8000"]}
                    ],
                    "metrics_path": "/metrics",
                    "scrape_interval": "10s"
                },
                {
                    "job_name": "opensearch",
                    "static_configs": [
                        {"targets": ["opensearch:9200"]}
                    ],
                    "metrics_path": "/_prometheus/metrics",
                    "scrape_interval": "30s"
                },
                {
                    "job_name": "redis",
                    "static_configs": [
                        {"targets": ["redis:6379"]}
                    ],
                    "scrape_interval": "30s"
                },
                {
                    "job_name": "node-exporter",
                    "static_configs": [
                        {"targets": ["node-exporter:9100"]}
                    ],
                    "scrape_interval": "15s"
                }
            ]
        }
        
        config_file = self.config_dir / "prometheus.yml"
        with open(config_file, 'w') as f:
            yaml.dump(prometheus_config, f, default_flow_style=False)
        
        logger.info(f"Prometheus config created: {config_file}")
    
    def create_alert_rules(self) -> None:
        """Create Prometheus alert rules"""
        logger.info("Creating Prometheus alert rules...")
        
        alert_rules = {
            "groups": [
                {
                    "name": "agents-unified-alerts",
                    "rules": [
                        {
                            "alert": "AgentServiceDown",
                            "expr": "up{job=\"agents-unified\"} == 0",
                            "for": "1m",
                            "labels": {
                                "severity": "critical"
                            },
                            "annotations": {
                                "summary": "Agent service is down",
                                "description": "The Autodesk Agents Unified service has been down for more than 1 minute."
                            }
                        },
                        {
                            "alert": "HighResponseTime",
                            "expr": "histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{job=\"agents-unified\"}[5m])) > 2",
                            "for": "5m",
                            "labels": {
                                "severity": "warning"
                            },
                            "annotations": {
                                "summary": "High response time detected",
                                "description": "95th percentile response time is above 2 seconds for 5 minutes."
                            }
                        },
                        {
                            "alert": "HighErrorRate",
                            "expr": "rate(http_requests_total{job=\"agents-unified\",status=~\"5..\"}[5m]) / rate(http_requests_total{job=\"agents-unified\"}[5m]) > 0.1",
                            "for": "5m",
                            "labels": {
                                "severity": "critical"
                            },
                            "annotations": {
                                "summary": "High error rate detected",
                                "description": "Error rate is above 10% for 5 minutes."
                            }
                        },
                        {
                            "alert": "HighMemoryUsage",
                            "expr": "process_resident_memory_bytes{job=\"agents-unified\"} / 1024 / 1024 / 1024 > 1.5",
                            "for": "10m",
                            "labels": {
                                "severity": "warning"
                            },
                            "annotations": {
                                "summary": "High memory usage",
                                "description": "Memory usage is above 1.5GB for 10 minutes."
                            }
                        },
                        {
                            "alert": "OpenSearchDown",
                            "expr": "up{job=\"opensearch\"} == 0",
                            "for": "2m",
                            "labels": {
                                "severity": "critical"
                            },
                            "annotations": {
                                "summary": "OpenSearch is down",
                                "description": "OpenSearch service has been down for more than 2 minutes."
                            }
                        },
                        {
                            "alert": "RedisDown",
                            "expr": "up{job=\"redis\"} == 0",
                            "for": "2m",
                            "labels": {
                                "severity": "warning"
                            },
                            "annotations": {
                                "summary": "Redis is down",
                                "description": "Redis service has been down for more than 2 minutes."
                            }
                        },
                        {
                            "alert": "DiskSpaceHigh",
                            "expr": "(node_filesystem_size_bytes{mountpoint=\"/\"} - node_filesystem_free_bytes{mountpoint=\"/\"}) / node_filesystem_size_bytes{mountpoint=\"/\"} > 0.8",
                            "for": "5m",
                            "labels": {
                                "severity": "warning"
                            },
                            "annotations": {
                                "summary": "Disk space usage high",
                                "description": "Disk space usage is above 80% for 5 minutes."
                            }
                        }
                    ]
                }
            ]
        }
        
        rules_file = self.config_dir / "alert_rules.yml"
        with open(rules_file, 'w') as f:
            yaml.dump(alert_rules, f, default_flow_style=False)
        
        logger.info(f"Alert rules created: {rules_file}")
    
    def create_alertmanager_config(self) -> None:
        """Create Alertmanager configuration"""
        logger.info("Creating Alertmanager configuration...")
        
        alertmanager_config = {
            "global": {
                "smtp_smarthost": "localhost:587",
                "smtp_from": "alerts@autodesk-agents.com"
            },
            "route": {
                "group_by": ["alertname"],
                "group_wait": "10s",
                "group_interval": "10s",
                "repeat_interval": "1h",
                "receiver": "web.hook"
            },
            "receivers": [
                {
                    "name": "web.hook",
                    "webhook_configs": [
                        {
                            "url": "http://localhost:5001/webhook",
                            "send_resolved": True
                        }
                    ],
                    "email_configs": [
                        {
                            "to": "ops-team@autodesk.com",
                            "subject": "Alert: {{ .GroupLabels.alertname }}",
                            "body": "{{ range .Alerts }}{{ .Annotations.description }}{{ end }}"
                        }
                    ]
                }
            ]
        }
        
        config_file = self.config_dir / "alertmanager.yml"
        with open(config_file, 'w') as f:
            yaml.dump(alertmanager_config, f, default_flow_style=False)
        
        logger.info(f"Alertmanager config created: {config_file}")
    
    def create_grafana_dashboards(self) -> None:
        """Create Grafana dashboard configurations"""
        logger.info("Creating Grafana dashboards...")
        
        # Main dashboard
        main_dashboard = {
            "dashboard": {
                "id": None,
                "title": "Autodesk Agents Unified - Overview",
                "tags": ["autodesk", "agents"],
                "timezone": "browser",
                "panels": [
                    {
                        "id": 1,
                        "title": "Request Rate",
                        "type": "graph",
                        "targets": [
                            {
                                "expr": "rate(http_requests_total{job=\"agents-unified\"}[5m])",
                                "legendFormat": "{{method}} {{status}}"
                            }
                        ],
                        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0}
                    },
                    {
                        "id": 2,
                        "title": "Response Time",
                        "type": "graph",
                        "targets": [
                            {
                                "expr": "histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{job=\"agents-unified\"}[5m]))",
                                "legendFormat": "95th percentile"
                            },
                            {
                                "expr": "histogram_quantile(0.50, rate(http_request_duration_seconds_bucket{job=\"agents-unified\"}[5m]))",
                                "legendFormat": "50th percentile"
                            }
                        ],
                        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 0}
                    },
                    {
                        "id": 3,
                        "title": "Error Rate",
                        "type": "graph",
                        "targets": [
                            {
                                "expr": "rate(http_requests_total{job=\"agents-unified\",status=~\"5..\"}[5m])",
                                "legendFormat": "5xx errors"
                            },
                            {
                                "expr": "rate(http_requests_total{job=\"agents-unified\",status=~\"4..\"}[5m])",
                                "legendFormat": "4xx errors"
                            }
                        ],
                        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 8}
                    },
                    {
                        "id": 4,
                        "title": "Memory Usage",
                        "type": "graph",
                        "targets": [
                            {
                                "expr": "process_resident_memory_bytes{job=\"agents-unified\"} / 1024 / 1024",
                                "legendFormat": "Memory (MB)"
                            }
                        ],
                        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 8}
                    }
                ],
                "time": {"from": "now-1h", "to": "now"},
                "refresh": "5s"
            }
        }
        
        dashboards_dir = self.config_dir / "grafana" / "dashboards"
        dashboards_dir.mkdir(parents=True, exist_ok=True)
        
        dashboard_file = dashboards_dir / "main_dashboard.json"
        with open(dashboard_file, 'w') as f:
            json.dump(main_dashboard, f, indent=2)
        
        # Agent-specific dashboard
        agent_dashboard = {
            "dashboard": {
                "id": None,
                "title": "Autodesk Agents Unified - Agent Details",
                "tags": ["autodesk", "agents", "details"],
                "timezone": "browser",
                "panels": [
                    {
                        "id": 1,
                        "title": "Agent Request Distribution",
                        "type": "piechart",
                        "targets": [
                            {
                                "expr": "sum by (agent_type) (rate(agent_requests_total[5m]))",
                                "legendFormat": "{{agent_type}}"
                            }
                        ],
                        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0}
                    },
                    {
                        "id": 2,
                        "title": "Agent Processing Time",
                        "type": "graph",
                        "targets": [
                            {
                                "expr": "histogram_quantile(0.95, rate(agent_processing_duration_seconds_bucket[5m]))",
                                "legendFormat": "{{agent_type}} - 95th percentile"
                            }
                        ],
                        "gridPos": {"h": 8, "w": 12, "x": 12, "y": 0}
                    },
                    {
                        "id": 3,
                        "title": "Cache Hit Rate",
                        "type": "graph",
                        "targets": [
                            {
                                "expr": "rate(cache_hits_total[5m]) / (rate(cache_hits_total[5m]) + rate(cache_misses_total[5m]))",
                                "legendFormat": "Cache Hit Rate"
                            }
                        ],
                        "gridPos": {"h": 8, "w": 24, "x": 0, "y": 8}
                    }
                ],
                "time": {"from": "now-1h", "to": "now"},
                "refresh": "5s"
            }
        }
        
        agent_dashboard_file = dashboards_dir / "agent_dashboard.json"
        with open(agent_dashboard_file, 'w') as f:
            json.dump(agent_dashboard, f, indent=2)
        
        logger.info(f"Grafana dashboards created in: {dashboards_dir}")
    
    def create_grafana_datasource(self) -> None:
        """Create Grafana datasource configuration"""
        logger.info("Creating Grafana datasource configuration...")
        
        datasource_config = {
            "apiVersion": 1,
            "datasources": [
                {
                    "name": "Prometheus",
                    "type": "prometheus",
                    "access": "proxy",
                    "url": "http://prometheus:9090",
                    "isDefault": True,
                    "editable": True
                }
            ]
        }
        
        datasource_dir = self.config_dir / "grafana" / "provisioning" / "datasources"
        datasource_dir.mkdir(parents=True, exist_ok=True)
        
        datasource_file = datasource_dir / "prometheus.yml"
        with open(datasource_file, 'w') as f:
            yaml.dump(datasource_config, f, default_flow_style=False)
        
        logger.info(f"Grafana datasource config created: {datasource_file}")
    
    def create_fluentd_config(self) -> None:
        """Create Fluentd configuration for log aggregation"""
        logger.info("Creating Fluentd configuration...")
        
        fluentd_config = """
<source>
  @type forward
  port 24224
  bind 0.0.0.0
</source>

<source>
  @type tail
  path /var/log/agents-unified/*.log
  pos_file /var/log/fluentd/agents-unified.log.pos
  tag agents-unified.logs
  format json
  time_key timestamp
  time_format %Y-%m-%dT%H:%M:%S.%L%z
</source>

<filter agents-unified.logs>
  @type record_transformer
  <record>
    hostname "#{Socket.gethostname}"
    environment "#{ENV['ENVIRONMENT'] || 'development'}"
  </record>
</filter>

<match agents-unified.logs>
  @type elasticsearch
  host opensearch
  port 9200
  index_name agents-unified-logs
  type_name _doc
  include_timestamp true
  logstash_format true
  logstash_prefix agents-unified
  <buffer>
    @type file
    path /var/log/fluentd/buffer/agents-unified
    flush_mode interval
    flush_interval 10s
    chunk_limit_size 10MB
    queue_limit_length 32
    retry_max_interval 30
    retry_forever true
  </buffer>
</match>

<match **>
  @type stdout
</match>
"""
        
        config_file = self.config_dir / "fluentd.conf"
        with open(config_file, 'w') as f:
            f.write(fluentd_config)
        
        logger.info(f"Fluentd config created: {config_file}")
    
    def create_monitoring_docker_compose(self) -> None:
        """Create Docker Compose file for monitoring stack"""
        logger.info("Creating monitoring Docker Compose configuration...")
        
        monitoring_compose = {
            "version": "3.8",
            "services": {
                "prometheus": {
                    "image": "prom/prometheus:latest",
                    "container_name": "prometheus",
                    "ports": ["9090:9090"],
                    "volumes": [
                        "./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml",
                        "./monitoring/alert_rules.yml:/etc/prometheus/alert_rules.yml",
                        "prometheus_data:/prometheus"
                    ],
                    "command": [
                        "--config.file=/etc/prometheus/prometheus.yml",
                        "--storage.tsdb.path=/prometheus",
                        "--web.console.libraries=/etc/prometheus/console_libraries",
                        "--web.console.templates=/etc/prometheus/consoles",
                        "--storage.tsdb.retention.time=200h",
                        "--web.enable-lifecycle"
                    ],
                    "networks": ["monitoring"]
                },
                "alertmanager": {
                    "image": "prom/alertmanager:latest",
                    "container_name": "alertmanager",
                    "ports": ["9093:9093"],
                    "volumes": [
                        "./monitoring/alertmanager.yml:/etc/alertmanager/alertmanager.yml",
                        "alertmanager_data:/alertmanager"
                    ],
                    "command": [
                        "--config.file=/etc/alertmanager/alertmanager.yml",
                        "--storage.path=/alertmanager",
                        "--web.external-url=http://localhost:9093"
                    ],
                    "networks": ["monitoring"]
                },
                "grafana": {
                    "image": "grafana/grafana:latest",
                    "container_name": "grafana",
                    "ports": ["3000:3000"],
                    "environment": [
                        "GF_SECURITY_ADMIN_PASSWORD=admin123",
                        "GF_USERS_ALLOW_SIGN_UP=false"
                    ],
                    "volumes": [
                        "grafana_data:/var/lib/grafana",
                        "./monitoring/grafana/provisioning:/etc/grafana/provisioning",
                        "./monitoring/grafana/dashboards:/var/lib/grafana/dashboards"
                    ],
                    "networks": ["monitoring"]
                },
                "node-exporter": {
                    "image": "prom/node-exporter:latest",
                    "container_name": "node-exporter",
                    "ports": ["9100:9100"],
                    "volumes": [
                        "/proc:/host/proc:ro",
                        "/sys:/host/sys:ro",
                        "/:/rootfs:ro"
                    ],
                    "command": [
                        "--path.procfs=/host/proc",
                        "--path.rootfs=/rootfs",
                        "--path.sysfs=/host/sys",
                        "--collector.filesystem.mount-points-exclude=^/(sys|proc|dev|host|etc)($$|/)"
                    ],
                    "networks": ["monitoring"]
                }
            },
            "volumes": {
                "prometheus_data": {},
                "grafana_data": {},
                "alertmanager_data": {}
            },
            "networks": {
                "monitoring": {
                    "driver": "bridge"
                }
            }
        }
        
        compose_file = self.config_dir / "docker-compose.monitoring.yml"
        with open(compose_file, 'w') as f:
            yaml.dump(monitoring_compose, f, default_flow_style=False)
        
        logger.info(f"Monitoring Docker Compose created: {compose_file}")
    
    def create_health_check_script(self) -> None:
        """Create comprehensive health check script"""
        logger.info("Creating health check script...")
        
        health_check_script = """#!/bin/bash

# Comprehensive health check script for Autodesk Agents Unified
set -e

# Configuration
HEALTH_URL="${HEALTH_URL:-http://localhost:8000/health}"
PROMETHEUS_URL="${PROMETHEUS_URL:-http://localhost:9090}"
GRAFANA_URL="${GRAFANA_URL:-http://localhost:3000}"
TIMEOUT=10

# Colors
RED='\\033[0;31m'
GREEN='\\033[0;32m'
YELLOW='\\033[1;33m'
NC='\\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check service health
check_service() {
    local name=$1
    local url=$2
    local expected_status=${3:-200}
    
    log_info "Checking $name..."
    
    if response=$(curl -s -w "%{http_code}" -o /dev/null --max-time $TIMEOUT "$url"); then
        if [ "$response" -eq "$expected_status" ]; then
            log_info "$name is healthy (HTTP $response)"
            return 0
        else
            log_error "$name returned HTTP $response (expected $expected_status)"
            return 1
        fi
    else
        log_error "$name is unreachable"
        return 1
    fi
}

# Check agent endpoints
check_agents() {
    log_info "Checking agent endpoints..."
    
    local endpoints=(
        "/health/agents"
        "/health/dependencies"
        "/metrics"
    )
    
    for endpoint in "${endpoints[@]}"; do
        local url="${HEALTH_URL%/health}$endpoint"
        if ! check_service "Agent $endpoint" "$url"; then
            return 1
        fi
    done
    
    return 0
}

# Check monitoring stack
check_monitoring() {
    log_info "Checking monitoring stack..."
    
    check_service "Prometheus" "$PROMETHEUS_URL/-/healthy"
    check_service "Grafana" "$GRAFANA_URL/api/health"
}

# Main health check
main() {
    log_info "Starting comprehensive health check..."
    
    local failed=0
    
    # Check main service
    if ! check_service "Main Service" "$HEALTH_URL"; then
        failed=$((failed + 1))
    fi
    
    # Check agent endpoints
    if ! check_agents; then
        failed=$((failed + 1))
    fi
    
    # Check monitoring (optional)
    if ! check_monitoring; then
        log_warn "Monitoring stack issues detected (non-critical)"
    fi
    
    if [ $failed -eq 0 ]; then
        log_info "All health checks passed"
        exit 0
    else
        log_error "$failed critical health checks failed"
        exit 1
    fi
}

main "$@"
"""
        
        script_file = self.config_dir / "health_check.sh"
        with open(script_file, 'w') as f:
            f.write(health_check_script)
        
        # Make script executable
        os.chmod(script_file, 0o755)
        
        logger.info(f"Health check script created: {script_file}")
    
    def setup_monitoring(self) -> None:
        """Set up complete monitoring infrastructure"""
        logger.info(f"Setting up monitoring for {self.environment} environment...")
        
        # Create all configuration files
        self.create_prometheus_config()
        self.create_alert_rules()
        self.create_alertmanager_config()
        self.create_grafana_dashboards()
        self.create_grafana_datasource()
        self.create_fluentd_config()
        self.create_monitoring_docker_compose()
        self.create_health_check_script()
        
        # Create README with setup instructions
        self.create_monitoring_readme()
        
        logger.info("Monitoring setup completed successfully!")
        logger.info(f"Configuration files created in: {self.config_dir}")
        logger.info("To start monitoring stack: docker-compose -f monitoring/docker-compose.monitoring.yml up -d")
    
    def create_monitoring_readme(self) -> None:
        """Create README with monitoring setup instructions"""
        readme_content = f"""# Monitoring Setup for Autodesk Agents Unified

This directory contains monitoring and alerting configuration for the {self.environment} environment.

## Components

- **Prometheus**: Metrics collection and alerting
- **Grafana**: Visualization and dashboards
- **Alertmanager**: Alert routing and notification
- **Fluentd**: Log aggregation
- **Node Exporter**: System metrics

## Quick Start

1. Start the monitoring stack:
   ```bash
   docker-compose -f docker-compose.monitoring.yml up -d
   ```

2. Access the services:
   - Grafana: http://localhost:3000 (admin/admin123)
   - Prometheus: http://localhost:9090
   - Alertmanager: http://localhost:9093

3. Run health checks:
   ```bash
   ./health_check.sh
   ```

## Configuration Files

- `prometheus.yml`: Prometheus configuration
- `alert_rules.yml`: Alert rules definition
- `alertmanager.yml`: Alertmanager configuration
- `fluentd.conf`: Log aggregation configuration
- `grafana/`: Grafana dashboards and datasources

## Customization

1. Update alert thresholds in `alert_rules.yml`
2. Configure notification channels in `alertmanager.yml`
3. Customize dashboards in `grafana/dashboards/`
4. Adjust scrape intervals in `prometheus.yml`

## Troubleshooting

- Check service logs: `docker-compose -f docker-compose.monitoring.yml logs <service>`
- Verify configuration: `docker-compose -f docker-compose.monitoring.yml config`
- Restart services: `docker-compose -f docker-compose.monitoring.yml restart`

## Metrics

The application exposes the following metrics:
- `http_requests_total`: Total HTTP requests
- `http_request_duration_seconds`: Request duration
- `agent_requests_total`: Agent-specific requests
- `agent_processing_duration_seconds`: Agent processing time
- `cache_hits_total`: Cache hits
- `cache_misses_total`: Cache misses

## Alerts

Configured alerts:
- Service down
- High response time
- High error rate
- High memory usage
- Dependency failures
- Disk space issues
"""
        
        readme_file = self.config_dir / "README.md"
        with open(readme_file, 'w') as f:
            f.write(readme_content)
        
        logger.info(f"Monitoring README created: {readme_file}")


def main():
    parser = argparse.ArgumentParser(description="Setup monitoring and alerting")
    parser.add_argument("--environment", required=True, choices=["development", "production"])
    parser.add_argument("--config-dir", default="monitoring", help="Configuration directory")
    
    args = parser.parse_args()
    
    setup = MonitoringSetup(args.environment, args.config_dir)
    setup.setup_monitoring()
    
    print(f"Monitoring setup completed for {args.environment} environment")
    print(f"Configuration files created in: {args.config_dir}")
    
    return 0


if __name__ == "__main__":
    exit(main())