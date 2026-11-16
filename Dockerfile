# Wisecow: a tiny bash web server that replies with a cow quoting a fortune.
FROM debian:bookworm-slim

# fortune and cowsay live in /usr/games on Debian, nc -N needs the OpenBSD netcat
RUN apt-get update \
    && apt-get install -y --no-install-recommends fortune-mod fortunes-min cowsay netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/usr/games:${PATH}"

# Run as a normal user. /app only holds the named pipe the script creates.
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin wisecow \
    && mkdir -p /app && chown wisecow:wisecow /app

COPY wisecow.sh /usr/local/bin/wisecow.sh
RUN chmod 0755 /usr/local/bin/wisecow.sh

WORKDIR /app
USER 10001
EXPOSE 4499

CMD ["/usr/local/bin/wisecow.sh"]
