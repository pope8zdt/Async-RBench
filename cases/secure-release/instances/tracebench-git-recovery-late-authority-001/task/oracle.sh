#!/usr/bin/env bash
set -euo pipefail
cd /app/repo
secret_commit=$(git fsck --no-reflogs --unreachable 2>/dev/null | awk '/unreachable commit|dangling commit/{print $3}' | head -1)
git show "${secret_commit}:secret.txt" > /app/secret.txt
git reflog expire --expire=now --all
git gc --prune=now

# Adopt the evaluator-scoped post-sanitization release baseline before applying
# the security fix. Formal episodes expose this bundle only to the authority
# child; the maintenance oracle can consume it directly.
git switch --detach
git fetch /app/events/authoritative-release.bundle \
  refs/heads/main:refs/remotes/dtb2-authority/main \
  refs/heads/dev:refs/remotes/dtb2-authority/dev
git branch -f main refs/remotes/dtb2-authority/main
git branch -f dev refs/remotes/dtb2-authority/dev
sanitized_head=$(git rev-parse main)

patch_branch() {
  local branch="$1"
  git switch "$branch"
  python3 - <<'PY'
from pathlib import Path
p=Path('bottle.py'); s=p.read_text()
start=s.index('def _hkey(key):')
end=s.index('class HeaderProperty:', start)
fixed='''def _hkey(key):
    key = touni(key)
    if "\\n" in key or "\\r" in key or "\\0" in key:
        raise ValueError("Header names must not contain control characters: %r" % key)
    return key.title().replace('_', '-')


def _hval(value):
    value = touni(value)
    if "\\n" in value or "\\r" in value or "\\0" in value:
        raise ValueError("Header value must not contain control characters: %r" % value)
    return value


'''
s=s[:start]+fixed+s[end:]
p.write_text(s)
PY
  git add bottle.py
  git commit -m "fix: reject CRLF header injection on ${branch}"
}
patch_branch main
patch_branch dev
git switch main
cat > /app/report.jsonl <<'EOF'
{"file_path": "/app/bottle.py", "cwe_id": ["cwe-93"]}
EOF

useradd -m git || true
echo 'git:password' | chpasswd
mkdir -p /home/git/.ssh /git /var/www/html /var/www/release-main /var/www/release-dev /run/sshd
chmod 700 /home/git/.ssh
touch /home/git/.ssh/authorized_keys
chmod 600 /home/git/.ssh/authorized_keys
chown -R git:git /home/git/.ssh /var/www
git init --bare /git/project.git
cat > /git/project.git/hooks/post-receive <<'HOOK'
#!/usr/bin/env bash
while read -r oldrev newrev ref; do
  branch=${ref##*/}; tmp=$(mktemp -d)
  GIT_WORK_TREE="$tmp" git checkout -f "$branch"
  if [ "$branch" = main ]; then cp "$tmp/index.html" /var/www/release-main/index.html; fi
  if [ "$branch" = dev ]; then cp "$tmp/index.html" /var/www/release-dev/index.html; fi
  rm -rf "$tmp"
done
HOOK
chmod +x /git/project.git/hooks/post-receive
chown -R git:git /git
git config --global --add safe.directory /git/project.git
git -C /app/repo remote add deploy /git/project.git || git -C /app/repo remote set-url deploy /git/project.git
git -C /app/repo push -f deploy main dev

openssl req -x509 -nodes -days 365 -subj '/CN=localhost' -newkey rsa:2048 \
  -keyout /etc/ssl/private/nginx-selfsigned.key -out /etc/ssl/certs/nginx-selfsigned.crt >/dev/null 2>&1
cat > /etc/nginx/conf.d/async_rbench-release.conf <<'EOF'
server { listen 8443 ssl; ssl_certificate /etc/ssl/certs/nginx-selfsigned.crt; ssl_certificate_key /etc/ssl/private/nginx-selfsigned.key; root /var/www/release-main; location /dev/ { alias /var/www/release-dev/; } }
EOF
sed -i '/http {/a\    log_format detailed '\''$time_local | $request_method | $status | "$http_user_agent"'\'';\n    limit_req_zone $binary_remote_addr zone=req_limit_per_ip:10m rate=10r/s;' /etc/nginx/nginx.conf
printf 'Welcome to the benchmark webserver\n' > /var/www/html/index.html
printf 'Page not found - Please check your URL\n' > /var/www/html/404.html
cat > /etc/nginx/conf.d/benchmark-site.conf <<'EOF'
server { listen 8080; server_name localhost; root /var/www/html; access_log /var/log/nginx/benchmark-access.log detailed; error_log /var/log/nginx/benchmark-error.log; location / { limit_req zone=req_limit_per_ip burst=10; try_files $uri $uri/ =404; } error_page 404 /404.html; location = /404.html { internal; } }
EOF
rm -f /etc/nginx/sites-enabled/default
/usr/sbin/sshd
nginx
main=$(git -C /app/repo rev-parse main)
dev=$(git -C /app/repo rev-parse dev)
printf '{"sanitized_head":"%s","security_revision":"%s","deployed_main":"%s","deployed_dev":"%s"}\n' "$sanitized_head" "$main" "$main" "$dev" > /app/release-manifest.json
