FROM ubuntu:25.04@sha256:27771fb7b40a58237c98e8d3e6b9ecdd9289cec69a857fccfb85ff36294dac20

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        ca-certificates \
        iproute2 \
        libatomic1 \
        libcapstone5 \
        libfdt1 \
        libgcrypt20 \
        libglib2.0-0t64 \
        libpcre2-8-0 \
        libpixman-1-0 \
        libselinux1 \
        nftables \
        procps \
        python3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
