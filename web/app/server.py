import asyncio
import json
import os
import logging
from contextlib import asynccontextmanager

import aioredis
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from pandas import DataFrame
from pydantic import BaseModel
import pandas as pd
import io

log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(level=log_level)

redis_client = None
pubsub_author = None
pubsub_study = None

async def get_redis_client():
    redis_host = os.getenv('REDIS_HOST', 'localhost')
    redis_port = os.getenv('REDIS_PORT', 6379)
    return await aioredis.from_url(f"redis://{redis_host}:{redis_port}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client, pubsub_author, pubsub_study
    redis_client = await get_redis_client()
    pubsub_author = redis_client.pubsub()
    pubsub_study = redis_client.pubsub()
    await pubsub_author.subscribe('author_result')
    await pubsub_study.subscribe('study_result')
    await asyncio.sleep(1)
    await pubsub_author.get_message()
    await pubsub_study.get_message()
    yield
    await redis_client.close()
    await redis_client.connection_pool.disconnect()

app = FastAPI(lifespan=lifespan)

templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

class AuthorInfoRequest(BaseModel):
    authors: list[str]
    disclosure: str

class StudyInfoRequest(BaseModel):
    disclosure: str

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

async def publish_infos(df: DataFrame, channel: str):
     for key, group in df.groupby("Article title"):
        if channel == 'author_channel':
            data = AuthorInfoRequest(
                authors=group["Author Name"].tolist(),
                disclosure=group["Disclosure Statement"].iloc[0]
            )
        else:
            data = StudyInfoRequest(
                disclosure=group["Disclosure Statement"].iloc[0]
            )
        data_dump = json.dumps(data.model_dump())
        await redis_client.publish(channel, data_dump)

async def publish_author_infos(df: DataFrame):
    await publish_infos(
        df,
        'author_channel'
    )

async def publish_study_infos(df: DataFrame):
    await publish_infos(
        df,
        'study_channel'
    )


async def process_infos(df: DataFrame, channel: str, pubsub: aioredis.client.PubSub):
    print(f"Processing data for {channel}")
    await publish_infos(df, channel)
    print(f"Data published to {channel}")
    while True:
        # await for the next message
        message = await pubsub.get_message(ignore_subscribe_messages=True)
        if message:
            print(f"Received message: {message['data']}")
            result = json.loads(message['data'].decode('utf-8'))
            finish_reason = result['response']['body']['choices'][0]['finish_reason']
            if finish_reason == 'stop':
                parse_result = json.loads(result['response']['body']['choices'][0]['message']['content'])
            else:
                parse_result = {'result': result}
            return parse_result


@app.post('/upload')
async def upload_csv(file: UploadFile = File(...)):
    if not file.filename.endswith(".csv"):
        return {"error": "File is not a CSV"}
    try:
        # Read the uploaded CSV
        content = await file.read()
        df = pd.read_csv(io.StringIO(content.decode("utf-8")))
        author_result = asyncio.create_task(process_infos(df, 'author_channel', pubsub_author))
        study_result = asyncio.create_task(process_infos(df, 'study_channel', pubsub_study))
        await author_result
        await study_result
        # await asyncio.wait([author_result, study_result])
        print("Waiting for results...")
        print(author_result)
        print(study_result)
        return "Data uploaded successfully"
    except Exception as e:
        return {"error": f"An error occurred: {e}"}
