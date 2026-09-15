# Auto Trader — cloud-ready container.
# Runs the momentum runner (worker) and/or the dashboard (web) depending on CMD.
FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (better layer caching).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the app.
COPY . .

# Default command: run BOTH trading scenarios (HIGH risk + LOW risk).
# Each is a separate bot.py process supervised by run_all.py.
CMD ["python", "run_all.py"]
