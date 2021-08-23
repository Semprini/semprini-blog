#!/usr/bin/env bash

if [ -z "${S3_ACCESS_KEY_ID}" ]; then
	echo "You need to set the S3_ACCESS_KEY_ID environment variable."
	exit 1
fi

if [ -z "${S3_SECRET_ACCESS_KEY}" ]; then
	echo "You need to set the S3_SECRET_ACCESS_KEY environment variable."
	exit 1
fi

if [ -z "${S3_PATH}" ]; then
	echo "You need to set the S3_PATH environment variable."
	exit 1
fi

if [ -z "${POSTGRES_DB}" ]; then
	echo "You need to set the POSTGRES_DB environment variable."
	exit 1
fi

if [ -z "${POSTGRES_HOST}" ] && [ -z "${POSTGRES_PORT_5432_TCP_ADDR}" ]; then
	echo "You need to set the POSTGRES_HOST environment variable or link to a container named POSTGRES."
	exit 1
fi

if [ -z "${POSTGRES_USER}" ]; then
	echo "You need to set the POSTGRES_USER environment variable."
	exit 1
fi

if [ -z "${BACKUP_SCHEDULE}" ]; then
	/code/backup.sh
else
	# Normal startup
	echo "$BACKUP_SCHEDULE /code/backup.sh" | crontab -
	crontab -l
	crond -f -L /dev/stdout
fi
