FROM jefzda/sweap-images:ansible.ansible-ansible__ansible-4c5ce5a1a9e79a845aff4978cfeb72a0d4ecf7d6-v1055803c3a812189a1133297f7f5468579283f86
RUN PIP_INDEX_URL=https://pypi.org/simple python3 -m pip install --no-cache-dir pytest==8.3.5 pytest-rerunfailures==14.0
RUN ln -s /app /testbed && mkdir -p /app/task_file /app/output_data
COPY task_file /app/task_file
WORKDIR /testbed
ENTRYPOINT []
CMD ["bash", "-lc", "sleep infinity"]
