FROM python:3.12-slim

WORKDIR /app

# Keep Python output unbuffered and avoid pyc writes in containers.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FLASK_ENV=production \
    FLASK_APP=app:app \
    PORT=5000

# Install runtime dependencies required by this module.
RUN pip install --upgrade pip && \
    pip install \
      flask \
      python-dotenv \
    gunicorn \
      reportlab \
      pillow \
      groq \
      psycopg2-binary \
      cryptography \
      werkzeug

# Copy only module3 source.
COPY . .

EXPOSE 5000

# Run the module-level Flask app via Gunicorn.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
