from fastapi import FastAPI
from app.routes.bg_remove_routes import router as bg_router

app = FastAPI(title="Photo Background Processor")

@app.get("/")
async def root():
    return {"message": "Backend setup successful!"}

app.include_router(bg_router)
