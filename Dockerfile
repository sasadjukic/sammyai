# Use Python 3.12 on a stable Debian release for a balance of size and compatibility
FROM python:3.12-slim-bookworm

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PIP_NO_CACHE_DIR=1
ENV QT_X11_NO_MITSHM=1
ENV QT_DEBUG_PLUGINS=0
# Set paths for persistent storage
ENV HF_HOME=/app/models
ENV SENTENCE_TRANSFORMERS_HOME=/app/models
ENV SAMMYAI_CONFIG_DIR=/app/runtime/config
ENV SAMMYAI_DATA_DIR=/app/runtime/data
ENV SAMMYAI_CACHE_DIR=/app/runtime/cache
ENV SAMMYAI_LOG_DIR=/app/runtime/logs

# Install system dependencies for PySide6/Qt and other libraries
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libfontconfig1 \
    libxrender1 \
    libdbus-1-3 \
    libxcb-cursor0 \
    libxcb-icccm4 \
    libxcb-image0 \
    libxcb-keysyms1 \
    libxcb-randr0 \
    libxcb-render-util0 \
    libxcb-shape0 \
    libxcb-shm0 \
    libxcb-sync1 \
    libxcb-util1 \
    libxcb-xfixes0 \
    libxcb-xinerama0 \
    libxcb-xkb1 \
    libxkbcommon-x11-0 \
    libegl1 \
    libnss3 \
    libasound2 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Create mutable runtime locations used by SammyAI and model libraries
RUN mkdir -p \
    "$HF_HOME" \
    "$SAMMYAI_CONFIG_DIR" \
    "$SAMMYAI_DATA_DIR" \
    "$SAMMYAI_CACHE_DIR" \
    "$SAMMYAI_LOG_DIR"

# Install CPU-only PyTorch first to save space (avoiding CUDA)
RUN pip install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

# Copy requirements and install remaining dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code and assets
COPY . .

# Set the entry point to run SammyAI
CMD ["python", "sammyai.py"]
