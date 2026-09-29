FROM python:3.11-slim
RUN pip install --no-cache-dir pytest==8.4.1
WORKDIR /app
COPY task_file /app/task_file
CMD ["bash", "-lc", "sleep infinity"]
