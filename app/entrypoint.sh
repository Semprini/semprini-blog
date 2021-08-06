#!/bin/sh

exec python manage.py migrate
exec gunicorn semprini.wsgi:application --bind 0.0.0.0:8000 --workers 3
