ARG BASE_IMAGE=ghcr.io/laude-institute/t-bench/python-3-13:20250620
FROM ${BASE_IMAGE}
WORKDIR /app
RUN apt-get update && apt-get install -y curl procps && rm -rf /var/lib/apt/lists/*
RUN pip install torch==2.7.1 transformers==4.55.0 pytest==8.4.1
# Exact upstream binary/data assets and request workload.
COPY assets/weights.pt /app/weights.pt
COPY assets/dataset.pt /app/dataset.pt
COPY assets/task_file /app/task_file
COPY assets/profiles /app/profiles
# Hidden tests, verifier scripts, oracle code and reference solutions are
# injected only into an isolated post-episode verifier clone.
CMD ["bash", "-lc", "sleep infinity"]
