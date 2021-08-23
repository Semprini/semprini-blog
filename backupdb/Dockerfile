FROM postgres:13-alpine
LABEL maintainer="someone <some.one@gmail.com>"

RUN apk add --no-cache python3 py3-pip
RUN pip install awscli

COPY start.sh /code/start.sh
COPY backup.sh /code/backup.sh
# Set the working directory to /code/
WORKDIR /code/

RUN chmod +x /code/start.sh
RUN chmod +x /code/backup.sh

CMD ["sh", "/code/start.sh"]
