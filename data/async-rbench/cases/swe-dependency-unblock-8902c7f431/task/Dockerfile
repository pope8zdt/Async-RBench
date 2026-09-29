FROM swebench/sweb.eval.x86_64.django_1776_django-12125:latest
RUN python -m pip install --no-cache-dir pytest==8.3.5
RUN mkdir -p /app/task_file /app/output_data
COPY task_file /app/task_file
WORKDIR /testbed
CMD ["bash", "-lc", "sleep infinity"]
