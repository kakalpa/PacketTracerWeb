FROM certbot/certbot:latest

RUN command -v flock >/dev/null 2>&1 || apk add --no-cache util-linux

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
