# Docker image for building Katapult RP2040 bootloader
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y \
    gcc-arm-none-eabi \
    libnewlib-arm-none-eabi \
    binutils-arm-none-eabi \
    libstdc++-arm-none-eabi-newlib \
    git \
    make \
    python3 \
    build-essential \
    libncurses-dev \
    && rm -rf /var/lib/apt/lists/*

RUN arm-none-eabi-gcc --version && \
    test -f /usr/include/newlib/string.h || \
    test -f /usr/arm-none-eabi/include/string.h

WORKDIR /work
