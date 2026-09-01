FROM mswebench/facebook_m_zstd:pr-2094
RUN python3 -m pip install --no-cache-dir pytest==8.3.5
RUN ln -s /home/zstd /testbed && mkdir -p /app/task_file /app/output_data
COPY task_file /app/task_file
WORKDIR /testbed
CMD ["bash", "-lc", "sleep infinity"]
