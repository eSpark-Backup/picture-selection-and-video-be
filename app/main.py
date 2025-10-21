from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes.video_creation_routes import router as video_creation_router
from app.routes import user_routes
from app.routes import reviewer_routes

app = FastAPI(title="Photo Background Processor")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # or list of allowed frontend URLs
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "Backend setup successful!"}

app.include_router(video_creation_router)
app.include_router(user_routes.router)
app.include_router(reviewer_routes.router)
