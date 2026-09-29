FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends vim && rm -rf /var/lib/apt/lists/* && pip install --no-cache-dir pytest==8.4.1
WORKDIR /app
COPY task_file /app/task_file
CMD ["bash", "-lc", "sleep infinity"]
