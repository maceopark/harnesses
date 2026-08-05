FROM --platform=linux/x86_64 sweb.env.py.x86_64.9d279b82a247a99ef60895:latest

COPY ./setup_repo.sh /root/
RUN sed -i -e 's/\r$//' /root/setup_repo.sh
RUN /bin/bash /root/setup_repo.sh

WORKDIR /testbed/
