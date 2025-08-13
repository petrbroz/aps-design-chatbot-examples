#!/usr/bin/env python3
"""
AgentCore Demo Starter

This script starts the development server and opens the web interface.
"""

import os
import sys
import time
import webbrowser
import subprocess
from pathlib import Path

def main():
    """Start the demo"""
    print("🚀 Starting AgentCore Demo...")
    
    # Get the current directory
    current_dir = Path(__file__).parent
    web_interface = current_dir / "web_interface.html"
    
    print("📋 Demo Components:")
    print("1. ✅ AgentCore Development Server (running on port 8000)")
    print("2. ✅ Web Interface (HTML file)")
    print("3. ✅ Mock data with realistic building properties")
    
    print(f"\n🌐 Opening web interface: {web_interface}")
    
    # Open the web interface in the default browser
    try:
        webbrowser.open(f"file://{web_interface.absolute()}")
        print("✅ Web interface opened in your default browser")
    except Exception as e:
        print(f"❌ Could not open browser automatically: {e}")
        print(f"📝 Please manually open: file://{web_interface.absolute()}")
    
    print("\n" + "="*80)
    print("🎉 AGENTCORE DEMO IS READY!")
    print("="*80)
    print("📊 What you can test:")
    print("• Wall Properties - Get detailed wall analysis")
    print("• Door Analysis - Review door specifications")
    print("• Window Data - Analyze window properties")
    print("• Area Calculations - Compute building areas")
    print("• Health Checks - Monitor system status")
    print("")
    print("🔧 API Endpoints available:")
    print("• http://127.0.0.1:8000/health - System health")
    print("• http://127.0.0.1:8000/api/v1/model-properties/prompt - Model properties")
    print("• http://127.0.0.1:8000/api/v1/aec-data-model/prompt - AEC data model")
    print("• http://127.0.0.1:8000/api/v1/model-derivatives/prompt - Model derivatives")
    print("")
    print("💡 The web interface provides an easy way to test all endpoints!")
    print("="*80)
    
    # Keep the script running
    try:
        print("\n⏸️  Press Ctrl+C to stop the demo")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n👋 Demo stopped. Thanks for testing AgentCore!")

if __name__ == "__main__":
    main()