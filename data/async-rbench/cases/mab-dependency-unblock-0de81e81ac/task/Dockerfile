FROM python:3.11-slim
WORKDIR /app
RUN python3 -m pip install --no-cache-dir pytest==8.3.5
RUN mkdir -p /app/task_file /app/output_data
COPY task_file /app/task_file
ENV PYTHONPATH=/app
CMD ["bash","-lc","sleep infinity"]
