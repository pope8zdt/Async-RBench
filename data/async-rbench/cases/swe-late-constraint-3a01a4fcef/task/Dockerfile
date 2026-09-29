FROM ghcr.io/epoch-research/swe-bench.eval.x86_64.pallets__flask-5014:latest
RUN python -m pip install --no-cache-dir pytest==8.3.5
RUN mkdir -p /app/task_file /app/output_data
COPY task_file /app/task_file
WORKDIR /testbed
CMD ["bash", "-lc", "sleep infinity"]
