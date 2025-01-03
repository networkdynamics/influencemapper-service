import asyncio
import json
import os
import logging
import threading
import time
from pathlib import Path

import redis.asyncio as redis
from openai import OpenAI


from influencemapper.author_org.infer import build_prompt as author_org_build_prompt, infer as author_org_infer, \
    AuthorInfoRequest
from influencemapper.study_org.infer import build_prompt as study_org_build_prompt, infer as study_org_infer, \
    StudyInfoRequest


def infer_study(data: dict, client):
    data = StudyInfoRequest(disclosure=data['disclosure'])
    prompt = study_org_build_prompt(data)
    return  study_org_infer(client, prompt)

def infer_author(data: dict, client):
    data = AuthorInfoRequest(authors=data['authors'], disclosure=data['disclosure'])
    prompt = author_org_build_prompt(data)
    return author_org_infer(client, prompt)

async def process_message(redis_client, data, client, channel_name):
    result, result_channel, parse_result = None, None, None
    if channel_name == 'study_channel':
        result = infer_study(data, client)
        result_channel = 'study_result'
    elif channel_name == 'author_channel':
        result = infer_author(data, client)
        result_channel = 'author_result'
    finish_reason = result.choices[0].finish_reason
    if finish_reason == 'stop':
        parse_result = json.loads(result.choices[0].message.content)
    else:
        parse_result = {'result': result}
    await redis_client.publish(result_channel, json.dumps(parse_result))

async def handle_messages(channel_name, client, redis_client):
    """
    Function to listen to messages for a specific channel.
    """
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(channel_name)
    print(f"Listening to messages from channel: {channel_name}")
    logging.info("Starting to listen for messages...")
    async for message in pubsub.listen():
        if message["type"] == "message":
            data = json.loads(message["data"])
            await process_message(redis_client, data, client, channel_name)

def run_listener(secret_key, channel_name, pool):
    openAI_client = OpenAI(api_key=secret_key)
    redis_client = redis.Redis(connection_pool=pool)
    asyncio.run(handle_messages(channel_name, openAI_client, redis_client), debug=True)

def get_redis_pool():
    redis_host = os.getenv('REDIS_HOST', 'localhost')
    redis_port = os.getenv('REDIS_PORT', 6379)
    return redis.ConnectionPool.from_url(f"redis://{redis_host}:{redis_port}")

def main():
    log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
    logging.basicConfig(level=log_level)
    secret_path = Path(__file__).parent.parent / 'secret_key'
    with secret_path.open() as f:
        secret_key = f.read().strip()
    pool = get_redis_pool()
    asyncio.create_task(run_listener(secret_key, 'author_channel', pool))
    asyncio.create_task(run_listener(secret_key, 'study_channel', pool))

if __name__ == "__main__":
    main()