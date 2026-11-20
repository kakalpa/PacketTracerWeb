#!/bin/sh
set -eu

# Only create container-writable directories; never mkdir on :ro bind mounts
mkdir -p /etc/ssl/certs /etc/ssl/private

# Maintain compatibility symlinks pointing to directory-mounted /etc/ssl/ptweb
if [ -d /etc/ssl/ptweb ]; then
  if [ ! -e /etc/ssl/certs/server.crt ] || [ -L /etc/ssl/certs/server.crt ]; then
    ln -sfn /etc/ssl/ptweb/server.crt /etc/ssl/certs/server.crt
  fi
  if [ ! -e /etc/ssl/private/server.key ] || [ -L /etc/ssl/private/server.key ]; then
    ln -sfn /etc/ssl/ptweb/server.key /etc/ssl/private/server.key
  fi
fi

# Validate static Nginx configuration before starting master process
nginx -t

hash_file() {
  p="$1"
  if [ -z "$p" ]; then
    return
  fi
  resolved=$(readlink -f "$p" 2>/dev/null || printf '%s' "$p")
  if [ -f "$resolved" ]; then
    h=$(sha256sum "$resolved" 2>/dev/null | awk '{print $1}')
    printf '%s=%s\n' "$p" "$h"
  else
    printf '%s=MISSING\n' "$p"
  fi
}

compute_fingerprint() {
  hash_file /etc/nginx/nginx.conf
  hash_file /etc/nginx/conf.d/ptweb.conf

  if [ -f /etc/nginx/conf.d/ptweb.conf ]; then
    active_paths=$(awk '/^[[:space:]]*(ssl_certificate|ssl_certificate_key)[[:space:]]+/ { sub(/;[[:space:]]*$/, "", $2); print $2 }' /etc/nginx/conf.d/ptweb.conf 2>/dev/null | sort -u)
    for ap in $active_paths; do
      hash_file "$ap"
    done
  fi

  hash_file /etc/ssl/ptweb/server.crt
  hash_file /etc/ssl/ptweb/server.key

  if [ -f /etc/letsencrypt/.nginx-reload-requested ]; then
    st=$(stat -c '%Y:%s' /etc/letsencrypt/.nginx-reload-requested 2>/dev/null || echo "")
    h=$(sha256sum /etc/letsencrypt/.nginx-reload-requested 2>/dev/null | awk '{print $1}')
    printf 'trigger=%s:%s\n' "$st" "$h"
  else
    printf 'trigger=MISSING\n'
  fi
}

WATCH_INTERVAL="${NGINX_CERT_WATCH_INTERVAL:-15}"
case "$WATCH_INTERVAL" in
  ''|*[!0-9]*) WATCH_INTERVAL=15 ;;
  0) WATCH_INTERVAL=15 ;;
esac

# Background certificate & config reload watcher
(
  set +e
  last_fp=$(compute_fingerprint)
  while :; do
    sleep "$WATCH_INTERVAL"
    curr_fp=$(compute_fingerprint)
    if [ "$curr_fp" != "$last_fp" ]; then
      sleep 2
      last_fp=$(compute_fingerprint)
      if nginx -t >/dev/null 2>&1; then
        echo "INFO: Certificate or Nginx config change detected; reloading nginx..." >&2
        nginx -s reload >/dev/null 2>&1 || echo "WARN: nginx -s reload failed" >&2
      else
        echo "WARN: nginx -t failed during reload watch; keeping existing workers alive" >&2
      fi
    fi
  done
) &

exec "$@"
