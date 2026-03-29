from fastapi import FastAPI, Request, Response
from contextlib import asynccontextmanager
import time, json, asyncio

import coordinator

SESSION_TIMEOUT = 30 #seconds
SESSION_CLEANUP_INTERVAL = 10 #seconds

class Session:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.last_active = time.time()
        self.data = None
    
    def touch(self):
        self.last_active = time.time()

sessions: dict[str, Session] = {}

def getSession(session_id: str) -> Session:
    if session_id in sessions:
        session = sessions[session_id]
        session.touch()
        return session
    else:
        new_session = Session(session_id)
        sessions[session_id] = new_session
        return new_session

async def cleanup_sessions():
    while True:
        now = time.time()
        expired_sessions = [sid for sid, session in sessions.items() if now - session.last_active > SESSION_TIMEOUT]
        for sid in expired_sessions:
            del sessions[sid]
        await asyncio.sleep(SESSION_CLEANUP_INTERVAL)
        
def closeSession(session_id: str):
    if session_id in sessions:
        del sessions[session_id]

@asynccontextmanager  
async def lifespan(app: FastAPI):
    asyncio.create_task(cleanup_sessions())
    coordinator.start()
    yield
    coordinator.stop()

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def get_root(request: Request):
    body_bytes = await request.body()
    json_str = body_bytes.decode("utf-8")
    requestData = json.loads(json_str)
    if "session_id" in requestData:
        getSession(requestData["session_id"]) #create or touch, don't care about session data here    

    resultData = json.dumps(coordinator.handle_get(requestData))

    return Response(
        content=resultData,
        media_type="application/json"
    )

@app.patch("/")
async def patch_root(request: Request):
    body_bytes = await request.body()
    json_str = body_bytes.decode("utf-8")
    requestData = json.loads(json_str)
    if "session_id" in requestData:
        getSession(requestData["session_id"]) #create or touch, don't care about session data here

    resultData = json.dumps(coordinator.handle_patch(requestData))

    return Response(
        content=resultData,
        media_type="application/json"
    )