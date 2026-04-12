#!/usr/bin/env python3
"""
Quick script to verify OAuth setup locally
Run this to test that environment variables are configured correctly
"""

import os
import sys
from pathlib import Path

# Add the project to path
sys.path.insert(0, str(Path(__file__).parent))

from liked_music_studio.oauth import is_configured, get_google_oauth_url

print("=== OAuth Configuration Check ===\n")

# Check environment variables
client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
redirect_uri = os.environ.get("OAUTH_REDIRECT_URI", "")

print(f"GOOGLE_CLIENT_ID: {'✓ SET' if client_id else '✗ NOT SET'}")
if client_id:
    print(f"  Value: {client_id[:20]}...")

print(f"GOOGLE_CLIENT_SECRET: {'✓ SET' if client_secret else '✗ NOT SET'}")
if client_secret:
    print(f"  Value: {client_secret[:20]}...")

print(f"OAUTH_REDIRECT_URI: {'✓ SET' if redirect_uri else '✗ NOT SET'}")
if redirect_uri:
    print(f"  Value: {redirect_uri}")

print(f"\nis_configured(): {is_configured()}\n")

if is_configured():
    auth_url = get_google_oauth_url()
    print(f"✓ OAuth URL generated successfully!")
    print(f"  URL: {auth_url[:100]}...")
else:
    print("✗ OAuth is NOT configured!")
    print("\nTo fix: Set these environment variables:")
    print("  GOOGLE_CLIENT_ID=60550032844-nvo233680ksmqm53ubd9u3ae6au5mdhh.apps.googleusercontent.com")
    print("  GOOGLE_CLIENT_SECRET=<your-client-secret-from-google-cloud>")
    print("  OAUTH_REDIRECT_URI=https://music-studio-uwdb.onrender.com/api/auth/callback")
