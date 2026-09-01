FROM jefzda/sweap-images:ansible.ansible-ansible__ansible-709484969c8a4ffd74b839a673431a8c5caa6457-vba6da65a0f3baefda7a058ebbd0a8dcafb8512f5
RUN python3 -m pip --version >/dev/null 2>&1 || (apt-get update && apt-get install -y --no-install-recommends python3 python3-pip && rm -rf /var/lib/apt/lists/*)
RUN if [ ! -d /testbed/.git ]; then repo_git="$(find /home /app /workspace -maxdepth 5 -type d -name .git 2>/dev/null | head -n 1)"; test -n "$repo_git"; if [ -d /testbed ]; then rmdir /testbed; fi; ln -s "$(dirname "$repo_git")" /testbed; fi && test -d /testbed/.git
RUN cd /testbed && test "$(git rev-parse HEAD)" = "35809806d3ab5d66fbb9696dc6a0009383e50673"
RUN mkdir -p /app/task_file /app/output_data
# Native and hidden tests must import the pinned checkout, not the Ansible
# package preinstalled in the SWEAP image.  Include the test helpers as well
# so the source regression file resolves its `units` package in-container.
ENV PYTHONPATH=/testbed/lib:/testbed/test
COPY task_file /app/task_file
WORKDIR /testbed
ENTRYPOINT []
CMD ["bash", "-lc", "sleep infinity"]
