#!/bin/bash
# RAG2 Self-RAG System Launcher for Linux/Mac
# This script activates virtual environment and runs the system

echo "========================================================"
echo "       RAG2 - Self-RAG System Launcher"
echo "========================================================"
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "[ERROR] Virtual environment not found!"
    echo "Please create it first:"
    echo "  python3 -m venv venv"
    echo "  source venv/bin/activate"
    echo "  pip install -r requirements.txt"
    exit 1
fi

# Activate virtual environment
echo "[1/2] Activating virtual environment..."
source venv/bin/activate

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo ""
    echo "[WARNING] .env file not found!"
    echo "Creating from .env.example..."
    cp .env.example .env
    echo ""
    echo "[IMPORTANT] Please edit .env file and set your configuration:"
    echo "  - For Cloud Mode: Set MODE=CLOUD and add OPENAI_API_KEY"
    echo "  - For Local Mode: Set MODE=LOCAL and ensure Ollama is running"
    echo ""
    read -p "Press Enter to continue (after editing .env)..."
fi

# Run system
echo ""
echo "[2/2] Starting RAG2 Self-RAG System..."
echo ""
python main.py

# Deactivate environment on exit
deactivate