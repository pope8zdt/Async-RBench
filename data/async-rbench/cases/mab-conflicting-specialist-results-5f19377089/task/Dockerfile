FROM python:3.11-slim
RUN pip install --no-cache-dir pytest==8.4.1 zstandard==0.23.0
WORKDIR /app
COPY task_file /app/task_file
COPY bootstrap_fixtures.py /tmp/bootstrap_fixtures.py
RUN python3 /tmp/bootstrap_fixtures.py && rm /tmp/bootstrap_fixtures.py
