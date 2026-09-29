FROM ghcr.io/laude-institute/t-bench/python-3-13:20250620@sha256:236734f0cafcce942ca09316d57236c2273a2b5411e116454a22cf6d718d95f5
WORKDIR /app
COPY logs /app/logs
COPY task_file/count_shard.py /app/count_shard.py
RUN mkdir -p /app/shards && python -m pip install --no-cache-dir pytest==8.4.2
CMD ["sleep", "infinity"]
