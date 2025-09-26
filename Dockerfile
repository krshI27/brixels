FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    wget \
    ca-certificates \
    git \
    libgdal-dev \
    gcc \
    g++ \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better layer caching
COPY environment.yml /app/

# Install miniconda with improved architecture detection
RUN ARCH=$(uname -m) && \
    echo "Detected architecture: $ARCH" && \
    if [ "$ARCH" = "x86_64" ]; then \
    MINICONDA_URL="https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh"; \
    elif [ "$ARCH" = "aarch64" ]; then \
    MINICONDA_URL="https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-aarch64.sh"; \
    else \
    echo "Unsupported architecture: $ARCH" && exit 1; \
    fi && \
    echo "Downloading miniconda from: $MINICONDA_URL" && \
    wget "$MINICONDA_URL" -O /tmp/miniconda.sh && \
    bash /tmp/miniconda.sh -b -p /opt/conda && \
    rm /tmp/miniconda.sh

# Create conda environment with better error handling and Apple Silicon optimizations
RUN /opt/conda/bin/conda config --set channel_priority strict && \
    /opt/conda/bin/conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main && \
    /opt/conda/bin/conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r && \
    /opt/conda/bin/conda config --set remote_read_timeout_secs 120 && \
    /opt/conda/bin/conda config --set remote_connect_timeout_secs 30 && \
    for i in 1 2 3; do /opt/conda/bin/conda env create -f environment.yml && break || sleep 10; done && \
    /opt/conda/bin/conda clean -afy

# Add conda to path and initialize conda
ENV PATH=/opt/conda/bin:/opt/conda/envs/brixels/bin:$PATH

# Initialize conda for shell usage
RUN /opt/conda/bin/conda init bash && \
    echo "conda activate brixels" >> ~/.bashrc

# Copy the rest of the application (done later for better caching)
COPY . /app/

# Expose Streamlit port
EXPOSE 8501

# Set entrypoint to run Streamlit
CMD ["conda", "run", "--no-capture-output", "-n", "brixels", "streamlit", "run", "app.py"]
