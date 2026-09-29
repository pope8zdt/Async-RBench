# Structure-derived SWE-bench case: swe-bench-selective-patch.
#
# Only public task material is baked in: the trimmed sklearn package (buggy
# base state), the module-group tests, the participant scripts and the build-time
# base-revision manifest. Private tests, oracle code and the reference solution
# are injected only into isolated benchmark-maintenance / verifier clones and
# never enter this image.
FROM python:3.11-slim

RUN pip install --no-cache-dir numpy==1.26.4 scipy==1.11.4 pytest==8.4.1

WORKDIR /app

COPY task_file /app/task_file

# Build the deterministic fixture (record the base revision of the fix target
# and prepare the output directory), then REMOVE the setup script so no
# fixture-building material stays in the image.
RUN bash /app/task_file/setup_package.sh \
    && rm -f /app/task_file/setup_package.sh

CMD ["bash", "-lc", "sleep infinity"]
