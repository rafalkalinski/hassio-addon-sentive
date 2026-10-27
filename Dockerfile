ARG BUILD_FROM
FROM $BUILD_FROM

# Supervisor passes the add-on version (config.yaml) as a build arg. ARG values are
# part of the build environment of all following RUN steps, so a version bump
# invalidates the layer cache below and forces a full rebuild on every HA.
ARG BUILD_VERSION

# Install Python and dependencies
RUN apk add --no-cache \
    python3 \
    py3-pip \
    py3-cryptography \
    py3-bcrypt \
    py3-pillow \
    curl \
    ca-certificates \
    tzdata && \
    cp /usr/share/zoneinfo/Europe/Warsaw /etc/localtime && \
    echo "Europe/Warsaw" > /etc/timezone

ENV TZ=Europe/Warsaw

# Install cloudflared based on architecture (pinned; bump to update the fleet)
ARG BUILD_ARCH
ARG CLOUDFLARED_VERSION=2026.10.4
RUN ARCH="${BUILD_ARCH}" && \
    case "$ARCH" in \
        amd64)   CF_ARCH="linux-amd64" ;; \
        aarch64) CF_ARCH="linux-arm64" ;; \
        armv7)   CF_ARCH="linux-armhf" ;; \
        *)       echo "Unsupported arch: $ARCH" && exit 1 ;; \
    esac && \
    curl -fsSL "https://github.com/cloudflare/cloudflared/releases/download/${CLOUDFLARED_VERSION}/cloudflared-${CF_ARCH}" \
        -o /usr/local/bin/cloudflared && \
    chmod +x /usr/local/bin/cloudflared

# Copy application files
COPY requirements.txt /
RUN pip3 install --no-cache-dir --break-system-packages -r /requirements.txt

COPY run.sh /run.sh
COPY register.py /register.py
COPY addon_server.py /addon_server.py
COPY config.yaml /config.yaml
COPY templates/ /templates/

RUN chmod +x /run.sh

CMD ["/run.sh"]
