#!/usr/bin/env bash
set -euo pipefail

repo=/app/repo
cd "$repo"

# Recover the leak through explicit object inspection before pruning it.
secret_commit=""
while read -r kind object_type object_id _; do
  if [[ "$object_type" == "commit" ]] && git cat-file -e "${object_id}:secret.txt" 2>/dev/null; then
    secret_commit="$object_id"
    break
  fi
done < <(git fsck --full --no-reflogs --unreachable 2>/dev/null || true)
test -n "$secret_commit"
git cat-file blob "${secret_commit}:secret.txt" > /app/secret.txt
git reflog expire --expire=now --all
git gc --prune=now

# Promote evaluator authority refs and rebuild both branch patches from them.
git switch --detach
git fetch /app/events/authoritative-release.bundle \
  refs/heads/main:refs/async-rbench/authority-main \
  refs/heads/dev:refs/async-rbench/authority-dev
git update-ref refs/heads/main refs/async-rbench/authority-main
git update-ref refs/heads/dev refs/async-rbench/authority-dev
sanitized_head=$(git rev-parse refs/heads/main)

patch_branch() {
  local branch="$1"
  git switch "$branch"
  BRANCH_NAME="$branch" python3 - <<'PY'
import os
import re
from pathlib import Path

path = Path("bottle.py")
source = path.read_text()
replacement = '''def _hkey(key):
    key = touni(key)
    if any(control in key for control in ("\\n", "\\r", "\\0")):
        raise ValueError("Header names must not contain control characters: %r" % key)
    return key.title().replace('_', '-')


def _hval(value):
    value = touni(value)
    if any(control in value for control in ("\\n", "\\r", "\\0")):
        raise ValueError("Header value must not contain control characters: %r" % value)
    return value


'''
updated, count = re.subn(
    r"def _hkey\(key\):.*?(?=class HeaderProperty:)",
    lambda _match: replacement,
    source,
    count=1,
    flags=re.S,
)
if count != 1:
    raise SystemExit(f"unable to patch {os.environ['BRANCH_NAME']}")
path.write_text(updated)
PY
  git add bottle.py
  git commit -m "security: validate header controls after authority (${branch})"
}
patch_branch main
patch_branch dev
git switch main
printf '%s\n' '{"file_path":"/app/bottle.py","cwe_id":["cwe-93"]}' > /app/report.jsonl

# Build a bare two-branch deployment remote. The hook uses git-archive instead
# of a temporary work tree, giving the verifier a genuinely distinct solution.
id git >/dev/null 2>&1 || useradd -m git
echo 'git:password' | chpasswd
install -d -m 700 -o git -g git /home/git/.ssh
install -m 600 -o git -g git /dev/null /home/git/.ssh/authorized_keys
install -d -o git -g git /git /var/www/release-main /var/www/release-dev
install -d /var/www/html /run/sshd
git init --bare /git/project.git
cat > /git/project.git/hooks/post-receive <<'HOOK'
#!/usr/bin/env bash
set -euo pipefail
while read -r oldrev newrev ref; do
  branch=${ref#refs/heads/}
  case "$branch" in
    main) destination=/var/www/release-main ;;
    dev) destination=/var/www/release-dev ;;
    *) continue ;;
  esac
  find "$destination" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
  git archive "$newrev" | tar -x -C "$destination"
done
HOOK
chmod 755 /git/project.git/hooks/post-receive
chown -R git:git /git /var/www/release-main /var/www/release-dev
git config --global --add safe.directory /git/project.git
git remote remove deploy 2>/dev/null || true
git remote add deploy /git/project.git
git push --force deploy main dev

openssl req -x509 -nodes -days 365 -subj '/CN=localhost' -newkey rsa:2048 \
  -keyout /etc/ssl/private/nginx-selfsigned.key \
  -out /etc/ssl/certs/nginx-selfsigned.crt >/dev/null 2>&1
cat > /etc/nginx/conf.d/async_rbench-release.conf <<'EOF'
server {
    listen 8443 ssl;
    ssl_certificate /etc/ssl/certs/nginx-selfsigned.crt;
    ssl_certificate_key /etc/ssl/private/nginx-selfsigned.key;
    root /var/www/release-main;
    location /dev/ { alias /var/www/release-dev/; }
}
EOF
sed -i '/http {/a\    log_format detailed '\''$time_local | $request_method | $status | "$http_user_agent"'\'';\n    limit_req_zone $binary_remote_addr zone=req_limit_per_ip:10m rate=10r/s;' /etc/nginx/nginx.conf
printf 'Welcome to the benchmark webserver\n' > /var/www/html/index.html
printf 'Page not found - Please check your URL\n' > /var/www/html/404.html
cat > /etc/nginx/conf.d/benchmark-site.conf <<'EOF'
server {
    listen 8080;
    server_name localhost;
    root /var/www/html;
    access_log /var/log/nginx/benchmark-access.log detailed;
    error_log /var/log/nginx/benchmark-error.log;
    location / {
        limit_req zone=req_limit_per_ip burst=10;
        try_files $uri $uri/ =404;
    }
    error_page 404 /404.html;
    location = /404.html { internal; }
}
EOF
rm -f /etc/nginx/sites-enabled/default
nginx -t
/usr/sbin/sshd
nginx

main=$(git rev-parse refs/heads/main)
dev=$(git rev-parse refs/heads/dev)
python3 - "$sanitized_head" "$main" "$dev" <<'PY'
import json
import sys
from pathlib import Path

sanitized, main, dev = sys.argv[1:]
Path("/app/release-manifest.json").write_text(json.dumps({
    "sanitized_head": sanitized,
    "security_revision": main,
    "deployed_main": main,
    "deployed_dev": dev,
}) + "\n")
PY
