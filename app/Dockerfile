# Use an official Python runtime based on Debian 10 "buster" as a parent image.
FROM python:slim-bookworm

# Add user that will be used in the container.
RUN useradd wagtail

# Port used by this container to serve HTTP.
EXPOSE 8000

# Set environment variables.
# 1. Force Python stdout and stderr streams to be unbuffered.
# 2. Set PORT variable that is used by Gunicorn. This should match "EXPOSE"
#    command.
ENV PYTHONUNBUFFERED=1 \
    PORT=8000

# Install system packages required by Wagtail and Django.
# ffmpeg/ffprobe are used only by the narrator worker, which runs this same
# image, to join per-segment narration clips and measure their durations.
RUN apt-get update --yes --quiet && apt-get install --yes --quiet --no-install-recommends \
    build-essential \
    libpq-dev \
    libjpeg62-turbo-dev \
    zlib1g-dev \
    libwebp-dev \
    git \
    ffmpeg \
 && rm -rf /var/lib/apt/lists/*

# Install the application server.
# gunicorn 21+ dropped the pkg_resources/setuptools dependency, required on
# Python 3.12+ (the slim-bookworm image now ships Python 3.14).
RUN pip install "gunicorn==23.0.0"

# Install the project requirements.
COPY requirements.txt /
COPY requirements_nodeps.txt /
RUN pip install -r /requirements.txt
RUN pip install --no-deps -r /requirements_nodeps.txt

# Use /app folder as a directory where the source code is stored.
WORKDIR /app

# Set this directory to be owned by the "wagtail" user. This Wagtail project
# uses SQLite, the folder needs to be owned by the user that
# will be writing to the database file.
RUN chown wagtail:wagtail /app

# Copy the source code of the project into the container.
COPY --chown=wagtail:wagtail . .

# Use user "wagtail" to run the build commands below and the server itself.
USER wagtail

# Collect static files.
RUN python manage.py collectstatic --noinput --clear

# Runtime command that executes when "docker run" is called, it does the
# following:
#   1. Migrate the database.
#   2. Start the application server.
# WARNING:
#   Migrating database at the same time as starting the server IS NOT THE BEST
#   PRACTICE. The database should be migrated manually or using the release
#   phase facilities of your hosting platform. This is used only so the
#   Wagtail instance can be started with a simple "docker run" command.
CMD echo KEY=$SECRET_KEY; set -xe; python manage.py migrate --noinput; gunicorn --log-level debug --capture-output --enable-stdio-inheritance wsgi:application
