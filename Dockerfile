# Auto Trader — cloud-ready container.
# Runs the momentum runner (worker) and/or the dashboard (web) depending on CMD.
FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (better layer caching).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the app.
COPY . .

# Default command: run the trading runner.
# Override with `python dashboard.py` for the web service.
CMD ["python", "csmom_runner.py", "--leveraged", "--composite"]
