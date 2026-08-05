FROM --platform=linux/x86_64 sweb.env.py.x86_64.a9f0574db63de49f4c6646:latest

COPY ./setup_repo.sh /root/
RUN sed -i -e 's/\r$//' /root/setup_repo.sh
RUN /bin/bash /root/setup_repo.sh

WORKDIR /testbed/
