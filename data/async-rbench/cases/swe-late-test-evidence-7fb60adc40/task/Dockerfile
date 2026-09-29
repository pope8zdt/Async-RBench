FROM ghcr.io/epoch-research/swe-bench.eval.x86_64.pytest-dev__pytest-5631:latest
RUN python -m pip install --no-cache-dir pytest==8.3.5
RUN /opt/miniconda3/envs/testbed/bin/python -m pip install --no-cache-dir mock==5.1.0
RUN mkdir -p /app/task_file /app/output_data
COPY task_file /app/task_file
WORKDIR /testbed
CMD ["bash", "-lc", "sleep infinity"]
