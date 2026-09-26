# Auto Trader — cloud-ready container.
# Runs the momentum runner (worker) and/or the dashboard (web) depending on CMD.
FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (better layer caching).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the app.
COPY . .

# Both paper portfolios share one account-wide safety/execution controller.
CMD ["python", "run_all.py"]
