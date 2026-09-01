# Direct composite of Terminal-Bench tasks locked in upstream/terminal-bench/SOURCE_LOCK.json
ARG BASE_IMAGE=ghcr.io/laude-institute/t-bench/ubuntu-24-04:20250624
FROM ${BASE_IMAGE}
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y \
    git nginx openssh-server curl openssl python3 python3-pip expect ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN pip3 install --break-system-packages pytest==8.4.1 requests==2.32.4
WORKDIR /app
COPY assets/challenge-setup.sh /app/challenge-setup.sh
RUN chmod +x /app/challenge-setup.sh && /app/challenge-setup.sh && rm /app/challenge-setup.sh
RUN git clone -o origin --single-branch https://github.com/bottlepy/bottle.git /tmp/bottle && \
    git -C /tmp/bottle reset --hard 0207a34f0c5716cd292dd4480253ad35d3da49f3 && \
    sed -i -e '1562,1563d' -e '1567,1568d' /tmp/bottle/bottle.py
RUN cd /app/repo && git branch -M main && \
    cp /tmp/bottle/bottle.py bottle.py && echo 'main branch content' > index.html && \
    git add bottle.py index.html && git commit -m 'feat: main secure release' && \
    git switch -c dev && echo 'dev branch content' > index.html && \
    git add index.html && git commit -m 'feat: developer release' && git switch main && \
    ln -s /app/repo/bottle.py /app/bottle.py
COPY assets/create-authoritative-baseline.sh /tmp/create-authoritative-baseline.sh
RUN chmod +x /tmp/create-authoritative-baseline.sh && \
    /tmp/create-authoritative-baseline.sh && rm /tmp/create-authoritative-baseline.sh
COPY assets/default.conf /etc/nginx/sites-available/default
RUN mkdir -p /var/www/html /var/www/dev /run/sshd
# Hidden tests and oracle code are never included in the participant image.
# They are available only in isolated benchmark-maintenance/verifier runs.
CMD ["bash", "-lc", "sleep infinity"]
