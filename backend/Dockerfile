FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (required for psycopg and compiling some extensions)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# CRITICAL OPTIMIZATION: Install PyTorch CPU-only version.
# Standard PyTorch is >2GB because it includes NVIDIA CUDA drivers.
# The CPU version is ~170MB, allowing it to easily fit on free cloud tiers.
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# CRITICAL OPTIMIZATION: Pre-download the HuggingFace model during the Docker build.
# This ensures that your server starts instantly and doesn't crash from memory spikes
# or timeout limits when trying to download the model on the first request.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Copy the rest of the application code
COPY . .

# Expose the standard web port
EXPOSE 8000

# Run the FastAPI server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
