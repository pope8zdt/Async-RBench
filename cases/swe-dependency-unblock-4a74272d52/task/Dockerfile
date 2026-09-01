FROM jefzda/sweap-images:element-hq.element-element-hq__element-web-fe14847bb9bb07cab1b9c6c54335ff22ca5e516a
RUN PIP_INDEX_URL=https://pypi.org/simple python3 -m pip install --no-cache-dir pytest==8.3.5 pytest-rerunfailures==14.0
RUN ln -s /app /testbed && mkdir -p /app/task_file /app/output_data
COPY task_file /app/task_file
WORKDIR /testbed
ENTRYPOINT []
CMD ["bash", "-lc", "sleep infinity"]
