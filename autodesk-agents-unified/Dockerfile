# Multi-stage Dockerfile for Autodesk Agents Unified
# Stage 1: Base image with Python and system dependencies
FROM python:3.11-slim as base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create app user
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Set working directory
WORKDIR /app

# Stage 2: Dependencies installation
FROM base as dependencies

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Stage 3: Development image
FROM dependencies as development

# Install development dependencies
RUN pip install --no-cache-dir pytest-cov black flake8 mypy

# Copy source code
COPY . .

# Change ownership to app user
RUN chown -R appuser:appuser /app

# Switch to app user
USER appuser

# Expose port
EXPOSE 8000

# Default command for development
CMD ["python", "-m", "uvicorn", "agent_core.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# Stage 4: Production image
FROM dependencies as production

# Copy only necessary files
COPY agent_core/ ./agent_core/
COPY config/ ./config/
COPY requirements.txt .

# Create cache directory
RUN mkdir -p /app/cache && chown -R appuser:appuser /app

# Switch to app user
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Production command
CMD ["python", "-m", "uvicorn", "agent_core.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]

# Stage 5: Testing image
FROM development as testing

# Copy test files
COPY tests/ ./tests/

# Run tests
RUN python -m pytest tests/ -v --cov=agent_core --cov-report=html --cov-report=term

# Default command for testing
CMD ["python", "-m", "pytest", "tests/", "-v"]