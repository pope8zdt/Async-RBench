FROM jefzda/sweap-images:future-architect.vuls-future-architect__vuls-b8db2e0b74f60cb7d45f710f255e061f054b6afc
RUN PIP_INDEX_URL=https://pypi.org/simple python3 -m pip install --break-system-packages --no-cache-dir pytest==8.3.5 pytest-rerunfailures==14.0
RUN ln -s /app /testbed && mkdir -p /app/task_file /app/output_data
COPY task_file /app/task_file
WORKDIR /testbed
ENTRYPOINT []
CMD ["bash", "-lc", "sleep infinity"]
