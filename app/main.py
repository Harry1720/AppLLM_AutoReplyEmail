from fastapi import FastAPI
from app.api.auth_router import router as auth_router

app = FastAPI(
    title="My FastAPI App",
    description="Demo FastAPI with Swagger UI",
    version="1.0.0"
)

# Include router
app.include_router(auth_router)

@app.get("/")
def read_root():
    return {"message": "Hello FastAPI"}


