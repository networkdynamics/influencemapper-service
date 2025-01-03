import asyncio
import json
import os
import logging
from contextlib import asynccontextmanager
import redis.asyncio as aioredis
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from pandas import DataFrame
from pydantic import BaseModel
import pandas as pd
import io
import zipfile

from starlette.responses import FileResponse

log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(level=log_level)

redis_client = None
pubsub = None


async def get_redis_client():
    redis_host = os.getenv('REDIS_HOST', 'localhost')
    redis_port = os.getenv('REDIS_PORT', 6379)
    return await aioredis.from_url(f"redis://{redis_host}:{redis_port}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client, pubsub
    redis_client = await get_redis_client()
    pubsub = redis_client.pubsub()
    await pubsub.subscribe('result', ignore_subscribe_messages=True)
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
    tasks = []
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
        tasks.append(redis_client.publish(channel, data_dump))
    return tasks


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

@app.post('/upload')
async def upload_csv(request: Request, file: UploadFile = File(...)):
    if not file.filename.endswith(".csv"):
        return {"error": "File is not a CSV"}
    else:
        content = await file.read()
        df = pd.read_csv(io.StringIO(content.decode("utf-8")))
        author_tasks = await publish_infos(df, 'author_channel')
        study_tasks = await publish_infos(df, 'study_channel')
        total_message = len(author_tasks) + len(study_tasks)
        await asyncio.gather(*(author_tasks+study_tasks))
        message_count = 0
        results = []
        while message_count < total_message:
            message = await pubsub.get_message()
            if message:
                try:
                    result = json.loads(message['data'])
                    results.append(result)
                    logging.info(f"Received message: {result}")
                    message_count += 1
                except TypeError as e:
                    logging.error(f"Could not decode message: {message}.\n Error: {e}")
                    continue
                logging.info(f'Received {message_count} of {total_message } messages')
        open('results.json', 'w').write(json.dumps(results))
        with zipfile.ZipFile('results.zip', 'w') as zipf:
            zipf.write('results.json')
        return FileResponse('results.zip')
