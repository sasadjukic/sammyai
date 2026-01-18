#!/usr/bin/env python3
"""
Quick test to verify Google Gemini client setup.
This script tests that the Google client can be initialized with an API key.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from llm.client import LLMClient, LLMConfig
from api_key_manager import APIKeyManager

def test_google_client():
    """Test Google Gemini client initialization."""
    print("Testing Google Gemini client setup...")
    
    # Check if API key is configured
    api_key = APIKeyManager.load_api_key("google")
    if not api_key:
        print("❌ No Google API key configured")
        print("   Please configure your API key using the text editor's API Key dialog")
        return False
    
    print(f"✓ Google API key found (length: {len(api_key)})")
    
    # Try to create a Gemini client
    try:
        config = LLMConfig(model_key="Gemini-2.5-Flash")
        client = config.create_client()
        print(f"✓ Gemini client created successfully")
        print(f"  - Model: {client.model_name}")
        print(f"  - Provider: {client.provider}")
        print(f"  - Type: {client.model_type.value}")
        return True
    except Exception as e:
        print(f"❌ Failed to create Gemini client: {e}")
        return False

def test_local_client():
    """Test local Ollama client still works."""
    print("\nTesting local Ollama client...")
    
    try:
        config = LLMConfig(model_key="Gemma3:4b")
        client = config.create_client()
        print(f"✓ Local client created successfully")
        print(f"  - Model: {client.model_name}")
        print(f"  - Provider: {client.provider}")
        print(f"  - Type: {client.model_type.value}")
        return True
    except Exception as e:
        print(f"❌ Failed to create local client: {e}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("LLM Client Verification Test")
    print("=" * 60)
    
    google_ok = test_google_client()
    local_ok = test_local_client()
    
    # Optional: Test DeepSeek if you want to verify its setup
    print("\nTesting DeepSeek V3.2 setup...")
    try:
        ds_config = LLMConfig(model_key="Deepseek V3.2")
        ds_client = ds_config.create_client()
        print(f"✓ DeepSeek client created successfully")
        ds_ok = True
    except Exception as e:
        print(f"❌ DeepSeek client creation failed: {e}")
        ds_ok = False

    print("\n" + "=" * 60)
    print("Summary:")
    print(f"  Google Gemini: {'✓ PASS' if google_ok else '❌ FAIL'}")
    print(f"  Local Ollama:  {'✓ PASS' if local_ok else '❌ FAIL'}")
    print(f"  DeepSeek V3.2: {'✓ PASS' if ds_ok else '❌ FAIL'}")
    print("=" * 60)
    
    sys.exit(0 if (google_ok and local_ok and ds_ok) else 1)
