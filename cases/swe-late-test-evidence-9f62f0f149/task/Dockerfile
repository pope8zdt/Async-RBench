FROM jefzda/sweap-images:ansible.ansible-ansible__ansible-bf98f031f3f5af31a2d78dc2f0a58fe92ebae0bb-v1055803c3a812189a1133297f7f5468579283f86
RUN python3 -m pip --version >/dev/null 2>&1 || (apt-get update && apt-get install -y --no-install-recommends python3 python3-pip && rm -rf /var/lib/apt/lists/*)
RUN if [ ! -d /testbed/.git ]; then repo_git="$(find /home /app /workspace -maxdepth 5 -type d -name .git 2>/dev/null | head -n 1)"; test -n "$repo_git"; if [ -d /testbed ]; then rmdir /testbed; fi; ln -s "$(dirname "$repo_git")" /testbed; fi && test -d /testbed/.git
RUN cd /testbed && test "$(git rev-parse HEAD)" = "17332532973343248297e3d3c746738d1f3b2f56"
RUN mkdir -p /app/task_file /app/output_data
COPY task_file /app/task_file
WORKDIR /testbed
ENTRYPOINT []
CMD ["bash", "-lc", "sleep infinity"]
