FROM ubuntu:24.04

ARG DEBIAN_FRONTEND=noninteractive

# Install packages needed to build jlm-opt, and packages needed for the benchmarks
RUN apt-get update && \
    apt-get install -y \
    git wget pipx python3-psutil python3-pandas python3-matplotlib python3-seaborn \
    lmod locales doxygen make ninja-build just g++ gfortran bear autoconf texinfo \
    llvm-18-dev clang-18 clang-format-18 libgtest-dev \
    \
    build-essential gcc-multilib gcc-mingw-w64 libasound2-dev libpulse-dev libdbus-1-dev \
    libfontconfig-dev libfreetype-dev libgnutls28-dev libgl-dev libunwind-dev \
    libx11-dev libxcomposite-dev libxcursor-dev libxfixes-dev libxi-dev libxrandr-dev \
    libxrender-dev libxext-dev libwayland-bin libwayland-dev libegl-dev \
    libxkbcommon-dev libxkbregistry-dev \
    libxaw7-dev xaw3dg-dev libgtk-3-dev libglib2.0-dev libtree-sitter-dev \
    libgif-dev libxpm-dev libjpeg-dev libtiff-dev libgnutls28-dev \
    libmpfr-dev libxxhash-dev gawk flex bison

# Clean apt and setup locale
RUN apt-get clean && \
    locale-gen en_US.UTF-8 && \
    update-locale

ENV LANG en_US.UTF-8
ENV LANGUAGE en_US:en
ENV LC_ALL en_US.UTF-8

RUN mkdir /benchmark
WORKDIR /benchmark
CMD ["/usr/bin/bash"]
