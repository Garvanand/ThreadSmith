"""
ThreadSmith FastAPI Application
AgentOS Day 21
"""
import uvicorn
from fastapi import FastAPI
from api.ingestion import router as ingestion_router

app = FastAPI(title="ThreadSmith", version="1.0.0")
app.include_router(ingestion_router)

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "ThreadSmith"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8021, reload=True)
