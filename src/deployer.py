import os
import tempfile
import json
from pathlib import Path

import coco
import config


def cors_ok():
    return ({
        "isBase64Encoded": False,
        "statusCode": 200,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Allow-Methods": "*"
        },
        "body": ""
    })
    

def deploy_handler(event, context):
    """Cohesion deployer as an http handler function.

    Supports Step Functions, Lambdas, and docker containers to run in ECS.

    Both input and output are a "filesystem in a dictionary": 
    { "files": { filepath: contents, ... } }

    We'll eventually get too big for this to make sense, so we'll need
    some API escape hatch, s3 references, etc.  For now just put
    everything under a /v1 route.

    """
    print("--- event start ---")
    print(event)
    print("--- event end ---")

    if event['httpMethod'].lower() == 'options':
        return cors_ok()

    body = json.loads(event['body'])
    files = body['files']

    cfg = config.Config()
    if 'config' in body:
        cfg = config.Config(obj = body['config'])


    # stuff
    # stuff
    # stuff
    # stuff
    
        
    responseEvent = {
        "isBase64Encoded": False,
        "statusCode": 200,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Allow-Methods": "*"
        },
        "body": json.dumps({ "files": result })
    }
    return responseEvent


