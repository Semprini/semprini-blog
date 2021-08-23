FROM postgres:alpine
LABEL maintainer="someone <some.one@gmail.com>"

RUN apk add --no-cache python3 py3-pip
RUN pip install awscli

COPY start.sh /usr/local/bin/
COPY backup.sh /usr/local/bin/

CMD ["sh", "start.sh"]
