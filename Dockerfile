# Stage 1: Base image with Python
FROM python:3.9-slim

# Install Docker CLI and compose plugin (for stopping/starting stacks)
RUN apt-get update \
	&& apt-get install -y --no-install-recommends \
		ca-certificates \
		curl \
		gnupg2 \
		gosu \
	&& rm -rf /var/lib/apt/lists/* \
	# Install Docker using the official convenience script (get.docker.com)
	&& curl -fsSL https://get.docker.com -o /tmp/install-docker.sh \
	&& sh /tmp/install-docker.sh \
	&& rm -f /tmp/install-docker.sh
	# The get.docker.com script installs Docker and docker compose; no manual plugin download required

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ .

# Expose port
EXPOSE 5000

# Run the application
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "main:app"]
