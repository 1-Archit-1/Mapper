FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ACCEPT_EULA=Y

# Install system dependencies and MS SQL ODBC Driver 18
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gnupg2 \
    unixodbc-dev \
    g++ \
    libexpat1 \
    # Add Microsoft repository for ODBC driver
    && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && curl -fsSL https://packages.microsoft.com/config/debian/12/prod.list > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    # Install MS ODBC 18
    && ACCEPT_EULA=Y apt-get install -y msodbcsql18 \
    # Clean up
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install uv package manager
RUN pip install --no-cache-dir uv

# Copy dependency configuration first to leverage Docker layer caching
COPY pyproject.toml uv.lock ./

# Install dependencies only
RUN uv sync --frozen --no-install-project

# Now copy the rest of the project
COPY . .

# Sync again to finalize the environment
RUN uv sync --frozen

# Expose the Streamlit port
EXPOSE 8501

# Default command to run the web app
CMD ["uv", "run", "streamlit", "run", "location_mapper_webapp.py", "--server.port=8501", "--server.address=0.0.0.0"]
