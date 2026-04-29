ARG BUILD_FROM
FROM $BUILD_FROM

ENV TZ=Europe/Warsaw

# Install Python and dependencies
RUN apk add --no-cache \
    python3 \
    py3-pip \
    py3-cryptography \
    py3-bcrypt \
    py3-pillow \
    curl \
    ca-certificates \
    tzdata

# Install cloudflared based on architecture
ARG BUILD_ARCH
RUN ARCH="${BUILD_ARCH}" && \
    case "$ARCH" in \
        amd64)   CF_ARCH="linux-amd64" ;; \
        aarch64) CF_ARCH="linux-arm64" ;; \
        armv7)   CF_ARCH="linux-armv6" ;; \
        *)       echo "Unsupported arch: $ARCH" && exit 1 ;; \
    esac && \
    curl -fsSL "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-${CF_ARCH}" \
        -o /usr/local/bin/cloudflared && \
    chmod +x /usr/local/bin/cloudflared

# Copy application files
COPY requirements.txt /
RUN pip3 install --no-cache-dir --break-system-packages -r /requirements.txt

COPY run.sh /run.sh
COPY register.py /register.py
COPY addon_server.py /addon_server.py
COPY templates/ /templates/

RUN chmod +x /run.sh

CMD ["/run.sh"]
