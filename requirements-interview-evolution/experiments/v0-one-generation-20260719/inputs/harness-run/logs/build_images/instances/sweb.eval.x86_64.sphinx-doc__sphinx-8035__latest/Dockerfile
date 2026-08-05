FROM --platform=linux/x86_64 sweb.env.py.x86_64.248ab44ae6a9f2d5ca6d01:latest

COPY ./setup_repo.sh /root/
RUN sed -i -e 's/\r$//' /root/setup_repo.sh
RUN /bin/bash /root/setup_repo.sh

WORKDIR /testbed/
