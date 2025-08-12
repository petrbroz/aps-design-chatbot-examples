# Autodesk Agents Unified

A unified AgentCore and Strands-based architecture for Autodesk Data agents.

## Architecture

This project consolidates three existing Autodesk Data agents:
- ACC Model Properties Assistant
- AEC Data Model Assistant  
- APS Model Derivatives Assistant

## Structure

- `agent_core/` - Core AgentCore framework
- `agents/` - Individual agent implementations
- `tools/` - Agent tools and utilities
- `config/` - Configuration files
- `tests/` - Unit and integration tests

## Getting Started

```bash
pip install -r requirements.txt
python -m agent_core.main
```