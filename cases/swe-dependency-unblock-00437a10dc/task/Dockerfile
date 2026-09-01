FROM ghcr.io/epoch-research/swe-bench.eval.x86_64.sympy__sympy-21930:latest
RUN python -m pip install --no-cache-dir pytest==8.3.5 pytest-rerunfailures==14.0
RUN mkdir -p /app/task_file /app/output_data
COPY task_file /app/task_file
WORKDIR /testbed
CMD ["bash", "-lc", "sleep infinity"]
