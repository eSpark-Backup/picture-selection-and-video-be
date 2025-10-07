from fastapi import FastAPI
from app.routes.bg_remove_routes import router as bg_router
from app.routes.fill_black_bg_routes import router as fill_black_bg_router
from app.routes.face_detection_routes import router as face_detection_router
app = FastAPI(title="Photo Background Processor")

@app.get("/")
async def root():
    return {"message": "Backend setup successful!"}

app.include_router(bg_router)
app.include_router(fill_black_bg_router)
app.include_router(face_detection_router)
