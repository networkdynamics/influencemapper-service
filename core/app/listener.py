import json
import os
import logging
import threading
from pathlib import Path

import aioredis
from openai import OpenAI


from influencemapper.author_org.infer import build_prompt as author_org_build_prompt, infer as author_org_infer, \
    AuthorInfoRequest
from influencemapper.study_org.infer import build_prompt as study_org_build_prompt, infer as study_org_infer, \
    StudyInfoRequest


def infer_study(data: dict, client):
    data = StudyInfoRequest(disclosure=data['disclosure'])
    prompt = study_org_build_prompt(data)
    result = study_org_infer(client, prompt)
    return {'result': result}

def infer_author(data: dict, client):
    data = AuthorInfoRequest(authors=data['authors'], disclosure=data['disclosure'])
    prompt = author_org_build_prompt(data)
    result = author_org_infer(client, prompt)
    return {'result': result}

async def process_message(redis_client, data, client, channel_name):
    result, result_channel, parse_result = None, None, None
    if channel_name == 'study_channel':
        result = infer_study(data, client)
        result_channel = 'study_result'
    elif channel_name == 'author_channel':
        result = infer_author(data, client)
        result_channel = 'author_result'
    finish_reason = result['response']['body']['choices'][0]['finish_reason']
    if finish_reason == 'stop':
        parse_result = json.loads(result['response']['body']['choices'][0]['message']['content'])
    else:
        parse_result = {'result': result}
    await redis_client.publish(result_channel, json.dumps(parse_result))

async def handle_messages(redis_client, channel_name, client):
    """
    Function to listen to messages for a specific channel.
    """
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(channel_name)
    print(f"Listening to messages from channel: {channel_name}")
    for message in pubsub.listen():
        if message["type"] == "message":
            data = json.loads(message["data"])
            await process_message(redis_client, data, client, channel_name)

async def get_redis_client():
    redis_host = os.getenv('REDIS_HOST', 'localhost')
    redis_port = os.getenv('REDIS_PORT', 6379)
    return await aioredis.from_url(f"redis://{redis_host}:{redis_port}")

def main():
    log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
    logging.basicConfig(level=log_level)
    secret_path = Path(__file__).parent.parent / 'secret_key'
    with secret_path.open() as f:
        secret_key = f.read().strip()
        client = OpenAI(api_key=secret_key)
    redis_client = get_redis_client()
    channel_names = ['author_channel', 'study_channel']
    threads = []
    for channel in channel_names:
        thread = threading.Thread(target=handle_messages, args=(redis_client, channel, client))
        threads.append(thread)
        thread.start()

if __name__ == "__main__":
    main()