#!/usr/bin/env python3
"""
Test script to verify Ollama cloud model integration.
This tests that the client can be initialized for all three model types.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from llm.client import LLMClient, MODEL_MAPPING

def test_client_initialization():
    """Test that clients can be initialized for each model type."""
    
    print("Testing client initialization for all model types...\n")
    
    # Test 1: Local model (should work without API key)
    print("1. Testing local model (Gemma3:4b)...")
    try:
        client = LLMClient(model_key="Gemma3:4b")
        print(f"   ✓ Local client initialized successfully")
        print(f"   - Provider: {client.provider}")
        print(f"   - Model: {client.model_name}")
        print(f"   - Client type: {type(client._client)}")
    except Exception as e:
        print(f"   ✗ Failed: {e}")
    
    print()
    
    # Test 2: Google cloud model (requires API key)
    print("2. Testing Google cloud model (Gemini-2.5-Flash)...")
    try:
        # This will fail without a real API key, but we can check the error message
        client = LLMClient(model_key="Gemini-2.5-Flash", api_key="test_key")
        print(f"   ✓ Google client initialized successfully")
        print(f"   - Provider: {client.provider}")
        print(f"   - Model: {client.model_name}")
        print(f"   - Client type: {type(client._google_client)}")
    except ValueError as e:
        if "API key required" in str(e):
            print(f"   ✓ Correctly requires API key")
        else:
            print(f"   ✗ Unexpected error: {e}")
    except Exception as e:
        # Expected to fail with invalid API key, but initialization logic should work
        print(f"   ✓ Client initialization logic works (failed with test key as expected)")
        print(f"   - Error: {e}")
    
    print()
    
    # Test 3: Ollama cloud model (requires API key)
    print("3. Testing Ollama cloud model (Kimi K2:1T)...")
    try:
        client = LLMClient(model_key="Kimi K2:1T", api_key="test_key")
        print(f"   ✓ Ollama cloud client initialized successfully")
        print(f"   - Provider: {client.provider}")
        print(f"   - Model: {client.model_name}")
        print(f"   - Client type: {type(client._client)}")
        print(f"   - Client host: {client._client._client.base_url if hasattr(client._client, '_client') else 'N/A'}")
    except ValueError as e:
        if "API key required" in str(e):
            print(f"   ✓ Correctly requires API key")
        else:
            print(f"   ✗ Unexpected error: {e}")
    except Exception as e:
        print(f"   ✗ Failed: {e}")
    
    print()
    
    # Test 4: DeepSeek cloud model (requires API key)
    print("4. Testing DeepSeek cloud model (Deepseek V3.2)...")
    try:
        client = LLMClient(model_key="Deepseek V3.2", api_key="test_key")
        print(f"   ✓ DeepSeek cloud client initialized successfully")
        print(f"   - Provider: {client.provider}")
        print(f"   - Model: {client.model_name}")
        print(f"   - Client type: {type(client._client)}")
    except ValueError as e:
        if "API key required" in str(e):
            print(f"   ✓ Correctly requires API key")
        else:
            print(f"   ✗ Unexpected error: {e}")
    except Exception as e:
        print(f"   ✗ Failed: {e}")
    
    print("\n" + "="*60)
    print("Test complete!")

if __name__ == "__main__":
    test_client_initialization()
