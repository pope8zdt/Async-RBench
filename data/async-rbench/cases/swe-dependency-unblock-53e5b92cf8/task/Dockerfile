FROM jefzda/sweap-images:internetarchive.openlibrary-internetarchive__openlibrary-e1e502986a3b003899a8347ac8a7ff7b08cbfc39-v08d8e8889ec945ab821fb156c04c7
RUN PIP_INDEX_URL=https://pypi.org/simple python3 -m pip install --break-system-packages --no-cache-dir pytest==8.3.5 pytest-rerunfailures==14.0
RUN ln -s /app /testbed && mkdir -p /app/task_file /app/output_data
COPY task_file /app/task_file
WORKDIR /testbed
ENTRYPOINT []
CMD ["bash", "-lc", "sleep infinity"]
