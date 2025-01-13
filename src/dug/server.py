import logging
import os
import uvicorn

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dug.config import Config
from dug.core.async_search import Search
from pydantic import BaseModel
import asyncio
from typing import Optional

logger = logging.getLogger (__name__)

APP = FastAPI(
    title="Dug Search API",
    root_path=os.environ.get("ROOT_PATH", ""),
)

APP.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class GetFromIndex(BaseModel):
    index: str = "concepts_index"
    size: int = 0


class SearchConceptQuery(BaseModel):
    query: str
    index: str = "concepts_index"
    offset: int = 0
    size: int = 20
    types: list = None

class SearchVariablesQuery(BaseModel):
    query: str
    index: str = "variables_index"
    concept: str = ""
    offset: int = 0
    size: int = 1000

class SearchKgQuery(BaseModel):
    query: str
    unique_id: str
    index: str = "kg_index"
    size:int = 100

class SearchStudyQuery(BaseModel):
    #query: str
    study_id: Optional[str] = None
    study_name: Optional[str] = None
    #index: str = "variables_index"
    size:int = 100
class SearchProgramQuery(BaseModel):
    #query: str
    program_id: Optional[str] = None
    program_name: Optional[str] = None
    #index: str = "variables_index"
    size:int = 100   

search = Search(Config.from_env())

@APP.on_event("shutdown")
def shutdown_event():
    asyncio.run(search.es.close())


@APP.post('/dump_concepts')
async def dump_concepts(request: GetFromIndex):
    return {
        "message": "Dump result",
        "result": await search.dump_concepts(**request.dict()),
        "status": "success"
    }


@APP.get('/agg_data_types')
async def agg_data_types():
    return {
        "message": "Dump result",
        "result": await search.agg_data_type(),
        "status": "success"
    }


@APP.post('/search')
async def search_concepts(search_query: SearchConceptQuery):
    return {
        "message": "Search result",
        # Although index in provided by the query we will keep it around for backward compatibility, but
        # search concepts should always search against "concepts_index"
        "result": await search.search_concepts(**search_query.dict(exclude={"index"})),
        "status": "success"
    }


@APP.post('/search_kg')
async def search_kg(search_query: SearchKgQuery):
    return {
        "message": "Search result",
        # Although index in provided by the query we will keep it around for backward compatibility, but
        # search concepts should always search against "kg_index"
        "result": await search.search_kg(**search_query.dict(exclude={"index"})),
        "status": "success"
    }


@APP.post('/search_var')
async def search_var(search_query: SearchVariablesQuery):
    return {
        "message": "Search result",
        # Although index in provided by the query we will keep it around for backward compatibility, but
        # search concepts should always search against "variables_index"
        "result": await search.search_variables(**search_query.dict(exclude={"index"})),
        "status": "success"
    }


@APP.post('/search_var_grouped')
async def search_var_grouped(search_query: SearchVariablesQuery):
    results = await search.search_variables(**search_query.dict(exclude={"index"}))
    all_elements = []
    for program_name in results:
        studies = results[program_name]
        for s in studies:
            elements = s['elements']
            for e in elements:
                new_element = e
                new_element.update(
                    {k: v for k, v in s.items() if k != 'elements'}
                )
                new_element['program_name'] = program_name
                all_elements.append(new_element)
    # regroup by variables
    by_id = {}
    for e in all_elements:
        by_id[e['id']] = by_id.get(e['id'], [])
        by_id[e['id']].append(e)
    var_info = None
    study_info_keys = [
        'c_id', 'c_link', 'c_name', 'program_name'
    ]
    final_variables = []
    for var_id in by_id:
        var_studies = by_id[var_id]
        for s in var_studies:
            if not var_info:
                var_info = {
                    k: v for k, v in s.items() if k not in study_info_keys
                }
                var_info.update(var_info['metadata'])
                var_info.pop('metadata')
                var_info['studies'] = []
            study_data = {k: v for k, v in s.items() if k in study_info_keys}
            var_info['studies'].append(study_data)
        final_variables.append(var_info)
        var_info = None
    return final_variables


@APP.get('/search_study')
async def search_study(study_id: Optional[str] = None, study_name: Optional[str] = None):
    """
    Search for studies by unique_id (ID or name) and/or study_name.
    """
    result = await search.search_study(study_id=study_id, study_name=study_name)
    return {
        "message": "Search result",
        "result": result,
        "status": "success"
    }


@APP.get('/search_program')
async def search_program( program_name: Optional[str] = None):
    """
    Search for studies by unique_id (ID or name) and/or study_name.
    """
    result = await search.search_program(program_name=program_name)
    return {
        "message": "Search result",
        "result": result,
        "status": "success"
    }

@APP.get('/program_list')
async def get_program_list():
    """
    Search for program by program name.
    """
    result = await search.search_program_list()
    return {
  
        "result": result,
        "status": "success"
    }
if __name__ == '__main__':
    uvicorn.run(APP,port=8181)
