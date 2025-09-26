#!/bin/bash
# Setup script for devcontainer

echo "Setting up conda environment..."

# Initialize conda for bash
/opt/conda/bin/conda init bash

# Add conda activation to bashrc
echo "conda activate brixels" >> ~/.bashrc

# Activate conda environment
source /opt/conda/etc/profile.d/conda.sh
conda activate brixels

# Verify environment
echo "Environment setup complete!"
echo "Python version: $(python --version)"
echo "Conda environment: $(conda info --envs | grep '*')"