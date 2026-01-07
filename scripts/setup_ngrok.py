#!/usr/bin/env python3
"""Script to set up ngrok tunnel."""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


def main():
    """Set up ngrok tunnel."""
    print("ngrok Tunnel Setup")
    print("=" * 40)
    print()

    try:
        from claudiar.config import get_settings

        settings = get_settings()
    except Exception as e:
        print(f"Error loading settings: {e}")
        print("Make sure you have a .env file configured")
        sys.exit(1)

    if not settings.ngrok_authtoken:
        print("Error: NGROK_AUTHTOKEN not set in .env")
        print()
        print("To get an ngrok auth token:")
        print("1. Sign up at https://dashboard.ngrok.com/signup")
        print("2. Get your auth token from https://dashboard.ngrok.com/get-started/your-authtoken")
        print("3. Add NGROK_AUTHTOKEN=your_token to your .env file")
        sys.exit(1)

    try:
        from pyngrok import conf, ngrok

        # Configure ngrok
        conf.get_default().auth_token = settings.ngrok_authtoken

        # Create tunnel
        port = settings.webhook_port
        tunnel = ngrok.connect(port, "http")

        print(f"✅ ngrok tunnel established!")
        print()
        print(f"📡 Public URL: {tunnel.public_url}")
        print(f"📡 Webhook URL: {tunnel.public_url}/webhooks/linear")
        print()
        print(f"Local server: http://localhost:{port}")
        print()
        print("Press Ctrl+C to stop the tunnel")

        # Keep running
        try:
            ngrok_process = ngrok.get_ngrok_process()
            ngrok_process.proc.wait()
        except KeyboardInterrupt:
            print("\nStopping tunnel...")
            ngrok.disconnect(tunnel.public_url)
            ngrok.kill()

    except ImportError:
        print("Error: pyngrok not installed")
        print("Run: pip install pyngrok")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
