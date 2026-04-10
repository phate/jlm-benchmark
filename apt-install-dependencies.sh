#!/usr/bin/env sh

apt-get update
apt-get install -y \
    wget pipx python3-psutil python3-pandas python3-matplotlib python3-seaborn python3-plotly \
    just bear make ninja-build g++ gfortran autoconf texinfo \
    llvm-18-dev clang-18 clang-format-18 libgtest-dev \
    lmod locales doxygen unzip git \
    \
    \
    build-essential gcc-multilib gcc-mingw-w64 libasound2-dev libpulse-dev libdbus-1-dev \
    libfontconfig-dev libfreetype-dev libgnutls28-dev libgl-dev libunwind-dev \
    libx11-dev libxcomposite-dev libxcursor-dev libxfixes-dev libxi-dev libxrandr-dev \
    libxrender-dev libxext-dev libwayland-bin libwayland-dev libegl-dev \
    libxkbcommon-dev libxkbregistry-dev \
    libxaw7-dev xaw3dg-dev libgtk-3-dev libglib2.0-dev libtree-sitter-dev \
    libgif-dev libxpm-dev libjpeg-dev libtiff-dev libgnutls28-dev \
    libmpfr-dev libxxhash-dev gawk flex bison

# MLIR is only necessary if building with the MLIR dialect or HLS enabled
apt-get install -y libmlir-18-dev mlir-18-tools
# Set up symlinks for libMLIR.so
ln -s /usr/lib/llvm-18/lib/libMLIR.so.18* /usr/lib/x86_64-linux-gnu/
ln -s /usr/lib/llvm-18/lib/libMLIR.so.18* /usr/lib/x86_64-linux-gnu/libMLIR.so
