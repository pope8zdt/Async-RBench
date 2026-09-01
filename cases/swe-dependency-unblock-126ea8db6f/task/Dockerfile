FROM jefzda/sweap-images:ansible.ansible-ansible__ansible-cb94c0cc550df9e98f1247bc71d8c2b861c75049-v1055803c3a812189a1133297f7f5468579283f86
RUN PIP_INDEX_URL=https://pypi.org/simple python3 -m pip install --break-system-packages --no-cache-dir pytest==8.3.5 pytest-rerunfailures==14.0
RUN ln -s /app /testbed && mkdir -p /app/task_file /app/output_data
COPY task_file /app/task_file
WORKDIR /testbed
ENTRYPOINT []
CMD ["bash", "-lc", "sleep infinity"]
