#!/bin/bash
# Start ngrok tunnel for Claudiar

echo "Starting ngrok tunnel on port 8000..."
echo ""
echo "Your webhook URL will be: https://YOUR-SUBDOMAIN.ngrok-free.app/webhooks/linear"
echo ""

ngrok http 8000
