# Use official Python image
FROM python:3.14.0-slim

# Set working directory inside container
WORKDIR /app

# Copy requirements and install dependencies
COPY app/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./

# Expose FastAPI port
#EXPOSE 8000

# Start FastAPI app (replace 'main:app' if using a different entrypoint)
#CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
