import asyncio
import json
import os
from pathlib import Path

import redis.asyncio as redis
import pytest

import server
import listener
import pandas as pd


def mock_infer(client, prompt):
    mock_result = {
        'response': {
            'body': {
                'choices': [
                    {
                        'finish_reason': 'stop',
                        'message': {
                            'content': json.dumps('mocked response')
                        }
                    }
                ]
            }
        }
    }
    return mock_result

@pytest.fixture
def my_client(mocker):
    mock_client = mocker.MagicMock()
    mock_client.beta.chat.completions.parse.return_value = {
        'response': {
            'body': {
                'choices': [
                    {
                        'finish_reason': 'stop',
                        'message': {
                            'content': json.dumps('mocked response')
                        }
                    }
                ]
            }
        }
    }
    return mock_client

@pytest.fixture
def test_df():
    resource_path = Path(__file__).parent / 'resources' / 'data.csv'
    return pd.read_csv(resource_path)

@pytest.fixture
async def redisdb():
    redis_host = os.getenv('REDIS_HOST', 'localhost')
    redis_port = os.getenv('REDIS_PORT', 6379)
    return await redis.from_url(f"redis://{redis_host}:{redis_port}")


@pytest.mark.asyncio
async def test_infer_study(redisdb, monkeypatch, my_client, test_df):
    monkeypatch.setattr(server, 'redis_client', redisdb)
    pubsub = redisdb.pubsub()
    await pubsub.subscribe(*['study_channel', 'study_result'])
    await asyncio.sleep(1)
    await pubsub.get_message()
    await pubsub.get_message()
    await server.publish_infos(test_df, 'study_channel')
    await asyncio.sleep(1)
    message = await pubsub.get_message()
    data = json.loads(message['data'].decode('utf-8'))
    monkeypatch.setattr(listener, 'infer_study', mock_infer)
    await listener.process_message(redisdb, data, my_client, 'study_channel')
    await asyncio.sleep(1)
    message2 = await pubsub.get_message()
    assert message2['data'].decode('utf-8') == json.dumps('mocked response')

@pytest.mark.asyncio
async def test_infer_author(redisdb, monkeypatch, my_client, test_df):
    monkeypatch.setattr(server, 'redis_client', redisdb)
    pubsub = redisdb.pubsub()
    await pubsub.subscribe(*['author_channel', 'author_result'])
    await asyncio.sleep(1)
    await pubsub.get_message()
    await pubsub.get_message()
    await server.publish_infos(test_df, 'author_channel')
    await asyncio.sleep(1)
    message = await pubsub.get_message()
    data = json.loads(message['data'].decode('utf-8'))
    monkeypatch.setattr(listener, 'infer_author', mock_infer)
    await listener.process_message(redisdb, data, my_client, 'author_channel')
    await asyncio.sleep(1)
    message2 = await pubsub.get_message()
    assert message2['data'].decode('utf-8') == json.dumps('mocked response')
