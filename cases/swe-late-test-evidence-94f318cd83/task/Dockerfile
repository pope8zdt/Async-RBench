FROM jefzda/sweap-images:ansible.ansible-ansible__ansible-d58e69c82d7edd0583dd8e78d76b075c33c3151e-v173091e2e36d38c978002990795f66cfc0af30ad
RUN python3 -m pip --version >/dev/null 2>&1 || (apt-get update && apt-get install -y --no-install-recommends python3 python3-pip && rm -rf /var/lib/apt/lists/*)
RUN if [ ! -d /testbed/.git ]; then repo_git="$(find /home /app /workspace -maxdepth 5 -type d -name .git 2>/dev/null | head -n 1)"; test -n "$repo_git"; if [ -d /testbed ]; then rmdir /testbed; fi; ln -s "$(dirname "$repo_git")" /testbed; fi && test -d /testbed/.git
RUN cd /testbed && test "$(git rev-parse HEAD)" = "a6e671db25381ed111bbad0ab3e7d97366395d05"
RUN mkdir -p /app/task_file /app/output_data
COPY task_file /app/task_file
WORKDIR /testbed
ENTRYPOINT []
CMD ["bash", "-lc", "sleep infinity"]
