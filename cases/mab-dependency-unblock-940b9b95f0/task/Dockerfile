FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends bash && rm -rf /var/lib/apt/lists/*
RUN python3 -m ensurepip --upgrade && python3 -m pip install --no-cache-dir pytest==8.3.5
RUN mkdir -p /app/task_file /app/output_data
COPY task_file /app/task_file
ENV PYTHONPATH=/app
CMD ["/bin/bash","-lc","sleep infinity"]
