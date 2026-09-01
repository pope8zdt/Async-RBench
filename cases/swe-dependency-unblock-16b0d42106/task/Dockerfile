FROM mswebench/ponylang_m_ponyc:pr-2205
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates wget bzip2 && rm -rf /var/lib/apt/lists/*
RUN wget -q https://repo.anaconda.com/miniconda/Miniconda3-py39_4.12.0-Linux-x86_64.sh -O /tmp/miniconda.sh && bash /tmp/miniconda.sh -b -p /opt/conda && rm /tmp/miniconda.sh
ENV PATH="/opt/conda/bin:${PATH}"
RUN /opt/conda/bin/python -m pip install --no-cache-dir pytest==8.3.5 pytest-rerunfailures==14.0
RUN ln -s /home/ponyc /testbed && mkdir -p /app/task_file /app/output_data
COPY task_file /app/task_file
WORKDIR /testbed
ENTRYPOINT []
CMD ["bash", "-lc", "sleep infinity"]
