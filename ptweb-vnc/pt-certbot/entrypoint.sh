#!/bin/sh
set -eu

mkdir -p /var/www/certbot/.well-known/acme-challenge /etc/letsencrypt

SLEEP_PID=""

cleanup() {
  if [ -n "$SLEEP_PID" ]; then
    kill "$SLEEP_PID" 2>/dev/null || true
  fi
  exit 0
}

trap cleanup TERM INT

get_auto_renew() {
  val="${CERTBOT_AUTO_RENEW:-true}"
  env_file="/app/.env"
  if [ -f "$env_file" ]; then
    cr=$(printf '\r')
    tab=$(printf '\t')
    while IFS= read -r line || [ -n "$line" ]; do
      line="${line%"$cr"}"
      while :; do
        case "$line" in
          " "*|"$tab"*) line="${line#?}" ;;
          *) break ;;
        esac
      done
      case "$line" in
        ""|"#"*) continue ;;
        export\ *|export"$tab"*)
          line="${line#export}"
          while :; do
            case "$line" in
              " "*|"$tab"*) line="${line#?}" ;;
              *) break ;;
            esac
          done
          ;;
      esac
      case "$line" in
        CERTBOT_AUTO_RENEW=*)
          raw="${line#CERTBOT_AUTO_RENEW=}"
          while :; do
            case "$raw" in
              " "*|"$tab"*) raw="${raw#?}" ;;
              *" "|*"$tab") raw="${raw%?}" ;;
              *) break ;;
            esac
          done
          case "$raw" in
            \"*\") raw="${raw#\"}"; raw="${raw%\"}" ;;
            \'*\') raw="${raw#\'}"; raw="${raw%\'}" ;;
          esac
          [ -n "$raw" ] && val="$raw"
          ;;
      esac
    done < "$env_file"
  fi
  printf '%s\n' "$val" | tr '[:upper:]' '[:lower:]'
}

INTERVAL="${CERTBOT_RENEW_INTERVAL:-43200}"
case "$INTERVAL" in
  ''|*[!0-9]*) INTERVAL=43200 ;;
  0) INTERVAL=43200 ;;
esac

echo "[pt-certbot] Starting Certbot renewal daemon (interval: ${INTERVAL}s)"

while :; do
  auto_renew=$(get_auto_renew)
  if [ "$auto_renew" = "true" ] || [ "$auto_renew" = "1" ]; then
    set -- /etc/letsencrypt/renewal/*.conf
    if [ -e "$1" ]; then
      echo "[pt-certbot] Checking certificates for renewal..."
      flock -n /etc/letsencrypt/.pt_certbot_op.lock \
        certbot renew --webroot -w /var/www/certbot --non-interactive \
        --deploy-hook 'date -u +%s > /etc/letsencrypt/.nginx-reload-requested' || true
    fi
  fi

  sleep "$INTERVAL" &
  SLEEP_PID=$!
  wait "$SLEEP_PID" || true
  SLEEP_PID=""
done
