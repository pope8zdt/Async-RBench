# Structure-derived Terminal-Bench task: git-leak-recovery.
# Only public task material is baked in. Private tests, oracle code and the
# upstream solution are injected only into isolated verifier/maintenance clones.
FROM python:3.11-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir pytest==8.4.1
WORKDIR /app
COPY task_file /app/task_file
# Build the deterministic leak fixture, then REMOVE the setup script so the
# fixture's secret value never remains in the participant image as plaintext.
RUN bash /app/task_file/setup_repo.sh \
    && rm -f /app/task_file/setup_repo.sh
CMD ["bash", "-lc", "sleep infinity"]
