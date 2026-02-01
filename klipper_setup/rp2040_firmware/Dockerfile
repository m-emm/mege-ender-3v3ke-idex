FROM debian:bookworm-slim

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc-arm-none-eabi \
    libnewlib-arm-none-eabi \
    binutils-arm-none-eabi \
    libstdc++-arm-none-eabi-newlib \
    git \
    make \
    python3 \
    python3-dev \
    libffi-dev \
    build-essential \
    libncurses-dev \
    avrdude \
    gcc-avr \
    binutils-avr \
    avr-libc \
    stm32flash \
    dfu-util \
    libnewlib-dev \
    gcc-arm-linux-gnueabi \
    binutils-arm-linux-gnueabi \
    libusb-1.0-0 \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Verify toolchain installation
RUN arm-none-eabi-gcc --version && \
    test -f /usr/include/newlib/string.h || \
    test -f /usr/arm-none-eabi/include/string.h

WORKDIR /work
CMD ["/bin/bash"]

