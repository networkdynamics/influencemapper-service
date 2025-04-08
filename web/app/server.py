import asyncio
import json
import os
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Optional

import redis.asyncio as aioredis
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from influencemapper.util import infer_is_funded
from pandas import DataFrame
from pandas.core.apply import relabel_result
from pydantic import BaseModel
import pandas as pd
import io
import zipfile

from starlette.middleware.cors import CORSMiddleware
from starlette.responses import FileResponse, StreamingResponse
from starlette.staticfiles import StaticFiles

log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(level=log_level)

redis_client: Optional[aioredis.Redis] = None
pubsub: Optional[aioredis.client.PubSub] = None

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
app.mount("/assets", StaticFiles(directory=os.path.join("dist", "assets")), name="assets")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "dist"))


class AuthorInfoRequest(BaseModel):
    authors: list[str]
    disclosure: str
    title: str
    affiliation: list[str]
    email: list[str]

class StudyInfoRequest(BaseModel):
    disclosure: str
    title: str


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


async def publish_infos(df: DataFrame, channel: str):
    tasks = []
    data_id = 0
    data_ids = []

    for key, group in df.groupby("Title"):
        if channel == 'author_channel':
            data = AuthorInfoRequest(
                authors=group["Author Name"].tolist(),
                disclosure=group["Disclosure Statement"].iloc[0],
                title=group['Title'].iloc[0],
                affiliation=group['Affiliation'].tolist(),
                email=group['Email'].tolist()
            )
        else:
            data = StudyInfoRequest(
                disclosure=group["Disclosure Statement"].iloc[0],
                title=group['Title'].iloc[0]
            )
        data = {
            'id': data_id,
            'payload': data.model_dump(),
            'channel': channel
        }
        tasks.append(redis_client.publish(channel, json.dumps(data)))
        data_ids.append(data_id)
        data_id += 1
    return tasks, data_ids


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

async def postprocess_study_results(results):
    sources = []
    orgs = []
    rel_types = []
    study_results = []
    # study_relationships = ['Perform analysis', 'Collect data', 'Coordinate the study', 'Design the study',
    #                     'Fund the study', 'Participate in the study', 'Review the study', 'Supply the study',
    #                     'Supply data to the study', 'Support the study', 'Write the study', 'Other']
    for result in results:
        id = result['id']
        source = result['source']
        study_info = result['payload']['study_info']
        for i in range(len(study_info)):
            org_name = study_info[i]['org_name']
            orgs.append(org_name)
            relationships = study_info[i]['relationships']
            for rel in relationships:
                rel_types.append(rel['relationship_type'])
        sources.append((id, source['title'], source['disclosure']))
    # A roundabout way to get unique source, ent. If we implemented database, this will be refactored
    df_source = pd.DataFrame(sources, columns=['id', 'title', 'disclosure'])
    df_ent = pd.DataFrame([(f'ent-{i}', org, infer_is_funded(org)) for i, org in enumerate(set(orgs))], columns=['ent_id', 'org_name', 'ent-ind support'])
    df_rel_type = pd.DataFrame([(f'rel-{i}', rel) for i, rel in enumerate(set(rel_types))], columns=['rel_id', 'relationship_type'])

    dict_ent = dict(zip(df_ent['org_name'], df_ent['ent_id']))
    dict_rel_type = dict(zip(df_rel_type['relationship_type'], df_rel_type['rel_id']))

    result_id = 0
    for result in results:
        study_info = result['payload']['study_info']
        for i in range(len(study_info)):
            org_name = study_info[i]['org_name']
            orgs.append(org_name)
            relationships = study_info[i]['relationships']
            for rel in relationships:
                relationship_type = rel['relationship_type']
                relationship_indication = rel['relationship_indication']
                study_results.append({
                    'res_id': f'res_{result_id}',
                    'source': result['id'],
                    'entity': dict_ent[org_name],
                    'relationship_type': dict_rel_type[relationship_type],
                    'relationship_indication': relationship_indication
                })
                result_id += 1
    df_results = pd.DataFrame(study_results, columns=['res_id', 'source', 'entity', 'relationship_type', 'relationship_indication'])
    return df_source, df_ent, df_rel_type, df_results


async def postprocess_author_results(results):
    sources = []
    orgs = []
    authors = []
    author_results = []
    rel_types = []
    # author_relationships = ['Honorarium', 'Named Professor', 'Received research materials directly', 'Patent license',
    #                         'Other/Unspecified', 'Personal fees', 'Salary support', 'Received research materials indirectly',
    #                         'Equity', 'Expert testimony', 'Consultant', 'Board member', 'Founder of entity or organization', 'Received travel support', 'Holds Chair', 'Fellowship', 'Scholarship',
    #                         'Collaborator', 'Received research grant funds directly', 'No Relationship', 'Speakers’ bureau', 'Employee of', 'Received research grant funds indirectly', 'Patent', 'Award',
    #                         'Research Trial committee member', 'Supported', 'Former employee of']
    for result in results:
        id = result['id']
        source = result['source']
        author_info = result['payload']['author_info']
        for i in range(len(author_info)):
            author = author_info[i]['author_name']
            rels = author_info[i]['organization']
            affiliation = author_info[i]['affiliation']
            email = author_info[i]['email']
            for rel in rels:
                orgs.append(rel['org_name'])
                relationships = rel['relationship_type']
                for relationship in relationships:
                    rel_types.append(relationship)
            authors.append((author, affiliation, email))
        sources.append((id, source['title'], source['disclosure']))
    df_source = pd.DataFrame(sources, columns=['id', 'title', 'disclosure'])
    df_ent = pd.DataFrame([(f'ent-{i}', org, infer_is_funded(org)) for i, org in enumerate(set(orgs))], columns=['ent_id', 'org_name', 'ent-ind support'])
    # TODO: deal with authors with similar name
    df_author = pd.DataFrame([(f'author-{i}', author[0], author[1], author[2]) for i, author in enumerate(set(authors))], columns=['author_id', 'author_name', 'affiliation', 'email'])
    df_rel_type = pd.DataFrame([(f'rel-{i}', rel) for i, rel in enumerate(set(rel_types))],
                               columns=['rel_id', 'relationship_type'])
    dict_ent = dict(zip(df_ent['org_name'], df_ent['ent_id']))
    dict_author = dict(zip(df_author['author_name'], df_author['author_id']))
    dict_rel_type = dict(zip(df_rel_type['relationship_type'], df_rel_type['rel_id']))

    result_id = 0
    for result in results:
        author_info = result['payload']['author_info']
        for i in range(len(author_info)):
            author = author_info[i]['author_name']
            rels = author_info[i]['organization']
            for rel in rels:
                org_name = rel['org_name']
                relationships = rel['relationship_type']
                for relationship in relationships:
                    author_results.append({
                        'res_id': f'res_{result_id}',
                        'source': result['id'],
                        'entity': dict_ent[org_name],
                        'author': dict_author[author],
                        'relationship_type': dict_rel_type[relationship]
                    })
                    result_id += 1
    df_results = pd.DataFrame(author_results, columns=['res_id', 'source', 'entity', 'author', 'relationship_type'])
    return df_source, df_ent, df_author, df_rel_type, df_results

@app.get('/events')
async def events(session_id: str):
    async def event_stream():
        message_count = 0
        total_message = await redis_client.hget(session_id, 'total_message')
        yield f"event: start\ndata: {int(total_message)}\n\n"
        total_message = int(total_message) if total_message else 0
        study_results = []
        author_results = []
        while message_count < total_message:
            message = await pubsub.get_message()
            if message:
                try:
                    result = json.loads(message['data'])
                    if result['channel'] == 'study_channel':
                        msg = f"event: received_study"
                        study_results.append(result)
                    else:
                        msg = f"event: received_author"
                        author_results.append(result)
                except TypeError as e:
                    logging.error(f"Could not decode message: {message}.\n Error: {e}")
                    continue
                data = {
                    'id': result['id'],
                    'channel': result['channel']
                }
                msg = f"{msg}\ndata: {json.dumps(data)}"
                yield msg + '\n\n'
                logging.info(f"Received message: {result}")
                message_count += 1
                if message_count == total_message:
                    logging.info(f'Received {message_count} of {total_message} messages')
                    all_study_results = await postprocess_study_results(study_results)
                    study_df_source, study_df_ent, study_df_rel_type, study_df_results = all_study_results
                    open('study_df_source.csv', 'w').write(study_df_source.to_csv(index=False))
                    open('study_df_ent.csv', 'w').write(study_df_ent.to_csv(index=False))
                    open('study_df_rel_type.csv', 'w').write(study_df_rel_type.to_csv(index=False))
                    open('study_df_results.csv', 'w').write(study_df_results.to_csv(index=False))
                    all_author_results = await postprocess_author_results(author_results)
                    author_df_source, author_df_ent, author_df_author, author_df_rel_type, author_df_results = all_author_results
                    open('author_df_source.csv', 'w').write(author_df_source.to_csv(index=False))
                    open('author_df_ent.csv', 'w').write(author_df_ent.to_csv(index=False))
                    open('author_df_author.csv', 'w').write(author_df_author.to_csv(index=False))
                    open('author_df_rel_type.csv', 'w').write(author_df_rel_type.to_csv(index=False))
                    open('author_df_results.csv', 'w').write(author_df_results.to_csv(index=False))
                    open('study_results.json', 'w').write(json.dumps(study_results))
                    open('author_results.json', 'w').write(json.dumps(author_results))
                    with zipfile.ZipFile('results.zip', 'w') as zipf:
                        zipf.write('study_results.json')
                        zipf.write('author_results.json')
                        zipf.write('study_df_source.csv')
                        zipf.write('study_df_ent.csv')
                        zipf.write('study_df_rel_type.csv')
                        zipf.write('study_df_results.csv')
                        zipf.write('author_df_source.csv')
                        zipf.write('author_df_ent.csv')
                        zipf.write('author_df_author.csv')
                        zipf.write('author_df_rel_type.csv')
                        zipf.write('author_df_results.csv')
                    os.remove('study_results.json')
                    os.remove('author_results.json')
                    os.remove('study_df_source.csv')
                    os.remove('study_df_ent.csv')
                    os.remove('study_df_rel_type.csv')
                    os.remove('study_df_results.csv')
                    os.remove('author_df_source.csv')
                    os.remove('author_df_ent.csv')
                    os.remove('author_df_author.csv')
                    os.remove('author_df_rel_type.csv')
                    os.remove('author_df_results.csv')
                    yield f"event: done\ndata: results.zip\n\n"
            else:
                await asyncio.sleep(0.1)
    return StreamingResponse(event_stream(), media_type="text/event-stream")

@app.get('/download/{file_name}')
async def download(file_name: str):
    return FileResponse(file_name)

@app.post('/upload')
async def upload_csv(request: Request, file: UploadFile = File(...)):
    if not file.filename.endswith(".csv"):
        return {"error": "File is not a CSV"}
    else:
        content = await file.read()
        dtype_dict = {
            "PDF File": "string",
            "Title": "string",
            "Author Name": "string",
            "Affiliation": "string",
            "Email": "string",
            "Disclosure Statement": "string"
        }
        df = pd.read_csv(io.StringIO(content.decode("utf-8")), delimiter='\t', dtype=dtype_dict,
                         keep_default_na=False)
        author_tasks, author_ids = await publish_infos(df, 'author_channel')
        study_tasks, study_ids = await publish_infos(df, 'study_channel')
        total_message = len(author_tasks) + len(study_tasks)
        await asyncio.gather(*(author_tasks+study_tasks))
        session_id = str(uuid.uuid4())
        await redis_client.hset(session_id, 'total_message', str(total_message))
        return {"session_id": session_id}

