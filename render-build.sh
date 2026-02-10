#!/usr/bin/env bash
# exit on error
set -o errexit

# Upgrade pip
python -m pip install --upgrade pip

# Force CPU version of torch to save space on Render
# This prevents downloading massive CUDA binaries (~2-4GB)
echo "Installing CPU-only torch..."
pip install torch --index-url https://download.pytorch.org/whl/cpu

# Install the rest of the dependencies
echo "Installing requirements..."
pip install -r requirements.txt

# Run any additional build steps if needed
