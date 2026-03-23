FROM ubuntu:24.04

ARG DEBIAN_FRONTEND=noninteractive

# Install packages needed to build jlm-opt, and packages needed for the benchmarks
COPY apt-install-dependencies.sh .
RUN ./apt-install-dependencies.sh

# Clean apt and setup locale
RUN apt-get clean && \
    locale-gen en_US.UTF-8 && \
    update-locale

ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US:en
ENV LC_ALL=en_US.UTF-8

RUN mkdir /benchmark
WORKDIR /benchmark
CMD ["/usr/bin/bash"]
