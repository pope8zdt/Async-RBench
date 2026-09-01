# Structure-derived Async-RBench task: gaia2-stockholm-moveout.
# Only public task material is baked in. Private tests, oracle code and the
# reference solution are injected only into isolated verifier/maintenance clones.
FROM python:3.11-slim
RUN pip install --no-cache-dir pytest==8.4.1
WORKDIR /app
COPY task_file /app/task_file
CMD ["bash", "-lc", "sleep infinity"]
