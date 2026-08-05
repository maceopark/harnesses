FROM --platform=linux/x86_64 sweb.env.py.x86_64.08de7b949eab978b5a23ad:latest

COPY ./setup_repo.sh /root/
RUN sed -i -e 's/\r$//' /root/setup_repo.sh
RUN /bin/bash /root/setup_repo.sh

WORKDIR /testbed/
