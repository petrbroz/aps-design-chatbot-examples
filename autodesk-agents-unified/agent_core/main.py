"""
Main entry point for AgentCore framework demonstration.
"""

import asyncio
import signal
import sys
from .core import AgentCore


async def main():
    """Main entry point for the AgentCore framework."""
    print("Starting AgentCore framework...")
    
    # Create and initialize AgentCore
    agent_core = AgentCore()
    
    # Set up signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        print(f"\nReceived signal {signum}, shutting down gracefully...")
        asyncio.create_task(shutdown(agent_core))
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Initialize the core framework
        await agent_core.initialize()
        print("AgentCore initialized successfully!")
        
        # Display system information
        system_info = await agent_core.get_system_info()
        print(f"System Info:")
        print(f"  - Initialized: {system_info['initialized']}")
        print(f"  - Healthy: {system_info['healthy']}")
        print(f"  - AWS Region: {system_info['config']['aws_region']}")
        print(f"  - Log Level: {system_info['config']['log_level']}")
        print(f"  - Cache Directory: {system_info['config']['cache_directory']}")
        print(f"  - Agents Configured: {system_info['config']['agents_configured']}")
        
        # Display health status
        health_status = await agent_core.get_health_status()
        print(f"Health Status: {health_status['overall_status']}")
        
        # Keep the application running
        print("AgentCore is running. Press Ctrl+C to stop.")
        while not agent_core._shutdown:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        print("\nShutdown requested by user")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        await shutdown(agent_core)


async def shutdown(agent_core: AgentCore):
    """Graceful shutdown of AgentCore."""
    print("Shutting down AgentCore...")
    try:
        await agent_core.shutdown()
        print("AgentCore shutdown completed")
    except Exception as e:
        print(f"Error during shutdown: {e}")
    finally:
        # Stop the event loop
        loop = asyncio.get_event_loop()
        loop.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nApplication terminated by user")
    except Exception as e:
        print(f"Application error: {e}")
        sys.exit(1)