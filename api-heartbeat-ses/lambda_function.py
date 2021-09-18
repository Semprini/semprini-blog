import os
import json
import requests

def lambda_handler(event, context):
    response = requests.get(os.environ.get("URL", ""))
    
    return {
        'statusCode': response.status_code,
        'body': response.text
    }
