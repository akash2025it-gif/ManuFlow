# Multi-stage / Production Dockerfile for NIT Trichy Order-to-Audit Management System
FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

# Install system dependencies for PostgreSQL support and build utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy dependency specifications and install Python packages
COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . /app/

# Collect static files for WhiteNoise static serving
RUN python manage.py collectstatic --noinput || true

# Expose web service port
EXPOSE 8000

# Start WSGI server using Gunicorn
CMD ["gunicorn", "nit_system.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
