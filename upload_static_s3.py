#!/usr/bin/env python3
"""Upload collected static files to S3 with correct ContentType headers.

Credentials are read from .env.prod.db (or the file named in ENV_FILE env var).
Required vars: S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY
Optional vars: S3_REGION (default ap-southeast-2), S3_BUCKET (default semprini.me)
"""

import mimetypes
import os
import sys
from pathlib import Path


def _load_env(path):
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, _, val = line.partition('=')
                    os.environ.setdefault(key.strip(), val.strip())
    except FileNotFoundError:
        pass


_load_env(os.environ.get('ENV_FILE', Path(__file__).parent / '.env.prod.db'))

ACCESS_KEY = os.environ.get('S3_ACCESS_KEY_ID')
SECRET_KEY = os.environ.get('S3_SECRET_ACCESS_KEY')
REGION     = os.environ.get('S3_REGION', 'ap-southeast-2')
BUCKET     = os.environ.get('S3_BUCKET', 'semprini.me')
S3_PREFIX  = 'static'
LOCAL_DIR  = Path(os.environ.get('STATIC_DIR', Path(__file__).parent / 'data' / 'static_collected'))

if not ACCESS_KEY or not SECRET_KEY:
    sys.exit('ERROR: S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY must be set (via .env.prod.db or environment)')

import boto3  # noqa: E402 — imported after env is loaded

MIME_OVERRIDES = {
    '.css':  'text/css',
    '.js':   'application/javascript',
    '.mjs':  'application/javascript',
    '.json': 'application/json',
    '.svg':  'image/svg+xml',
    '.woff': 'font/woff',
    '.woff2':'font/woff2',
    '.ttf':  'font/ttf',
    '.eot':  'application/vnd.ms-fontobject',
    '.html': 'text/html',
    '.txt':  'text/plain',
    '.map':  'application/json',
    '.glb':  'model/gltf-binary',
    '.gltf': 'model/gltf+json',
}

s3 = boto3.client(
    's3',
    region_name=REGION,
    aws_access_key_id=ACCESS_KEY,
    aws_secret_access_key=SECRET_KEY,
)

files = [f for f in LOCAL_DIR.rglob('*') if f.is_file()]
print(f'Uploading {len(files)} files to s3://{BUCKET}/{S3_PREFIX}/')

for i, path in enumerate(files, 1):
    key = f"{S3_PREFIX}/{path.relative_to(LOCAL_DIR)}"
    ext = path.suffix.lower()
    content_type = MIME_OVERRIDES.get(ext) or mimetypes.guess_type(str(path))[0] or 'application/octet-stream'
    s3.upload_file(
        str(path), BUCKET, key,
        ExtraArgs={'ContentType': content_type, 'ACL': 'public-read', 'CacheControl': 'max-age=86400'},
    )
    if i % 50 == 0 or i == len(files):
        print(f'  {i}/{len(files)} uploaded')

print('Done.')
