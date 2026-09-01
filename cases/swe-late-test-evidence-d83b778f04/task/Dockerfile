FROM mswebench/clap-rs_m_clap:pr-3179
ENV PATH="/usr/local/cargo/bin:${PATH}"
RUN python3 -m pip --version >/dev/null 2>&1 || (apt-get update && apt-get install -y --no-install-recommends python3 python3-pip && rm -rf /var/lib/apt/lists/*)
RUN python3 -m pip install --no-cache-dir pytest==8.3.5 pytest-rerunfailures==14.0 || python3 -m pip install --break-system-packages --no-cache-dir pytest==8.3.5 pytest-rerunfailures==14.0
RUN if [ ! -d /testbed/.git ]; then repo_git="$(find /home /app /workspace -maxdepth 5 -type d -name .git 2>/dev/null | head -n 1)"; test -n "$repo_git"; if [ -d /testbed ]; then rmdir /testbed; fi; ln -s "$(dirname "$repo_git")" /testbed; fi && test -d /testbed/.git
RUN cd /testbed && test "$(git rev-parse HEAD)" = "56ed9981da3a28205efa03a0e4f162359bab1dfe"
RUN mkdir -p /app/task_file /app/output_data
COPY task_file /app/task_file
WORKDIR /testbed
ENTRYPOINT []
CMD ["bash", "-lc", "sleep infinity"]
