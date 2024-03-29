#!/usr/bin/env bash

if [ -z "${POSTGRES_PORT}" ]; then
	POSTGRES_PORT=5432
fi

if [ -z "${S3_ENDPOINT}" ]; then
	AWS_ARGS="${AWS_EXTRA_OPTS}"
else
	AWS_ARGS="--endpoint-url ${S3_ENDPOINT} ${AWS_EXTRA_OPTS}"
fi

# env vars needed for aws tools
export AWS_ACCESS_KEY_ID=$S3_ACCESS_KEY_ID
export AWS_SECRET_ACCESS_KEY=$S3_SECRET_ACCESS_KEY
export AWS_DEFAULT_REGION=$S3_REGION

export PGPASSWORD=$POSTGRES_PASSWORD
POSTGRES_HOST_OPTS="-h $POSTGRES_HOST -p $POSTGRES_PORT -U $POSTGRES_USER $POSTGRES_EXTRA_OPTS"

echo "Creating dump of ${POSTGRES_DB} database from ${POSTGRES_HOST}..."

pg_dump $POSTGRES_HOST_OPTS $POSTGRES_DB | gzip > dump.sql.gz

DESTINATION="$S3_PATH/${POSTGRES_DB}_$(date +"%Y-%m-%dT%H:%M:%SZ").sql.gz"
echo "Uploading dump to $DESTINATION"

cat dump.sql.gz | aws $AWS_ARGS s3 cp - $DESTINATION
rm dump.sql.gz

echo "SQL backup uploaded successfully"
