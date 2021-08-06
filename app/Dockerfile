# Use an official Python runtime as a parent image
FROM python:3.9
LABEL maintainer="someone@semprini"

# Set environment varibles
ENV PYTHONUNBUFFERED 1
ENV DJANGO_ENV dev

COPY ./entrypoint.sh /code/entrypoint.sh
COPY ./requirements.txt /code/requirements.txt
COPY ./requirements_nodeps.txt /code/requirements_nodeps.txt
RUN pip install --upgrade pip
# Install any needed packages specified in requirements.txt
RUN pip install -r /code/requirements.txt
RUN pip install --no-deps -r /code/requirements_nodeps.txt
RUN pip install gunicorn

# Copy the current directory contents into the container at /code/
COPY . /code/
# Set the working directory to /code/
WORKDIR /code/

RUN python manage.py makemigrations

RUN useradd wagtail
RUN chown -R wagtail /code
RUN mkdir -p /home/app/web
RUN chown -R wagtail /home/app/web
RUN chown -R wagtail /code/entrypoint.sh
RUN chmod +x /code/entrypoint.sh
USER wagtail

EXPOSE 8000
CMD /code/entrypoint.sh
