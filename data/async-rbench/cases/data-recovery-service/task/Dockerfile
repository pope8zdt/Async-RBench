FROM python:3.11-slim
RUN apt-get update && apt-get install -y sqlite3 xxd curl procps && rm -rf /var/lib/apt/lists/*
RUN pip install pytest==8.4.1 pandas==2.2.3 pyarrow==17.0.0 grpcio==1.73.0 grpcio-tools==1.73.0 psutil
WORKDIR /app
# Exact upstream inputs, byte-for-byte.
COPY assets/main.db /app/main.db
COPY assets/main.db-wal.encrypted /app/main.db-wal
COPY assets/data /data
# Hidden tests, verifier scripts, oracle code and reference solutions are
# deliberately absent. The benchmark launches a private verifier clone after
# the participant process has terminated.
CMD ["bash", "-lc", "sleep infinity"]
