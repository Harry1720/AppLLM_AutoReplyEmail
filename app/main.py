from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from app.api.auth_router import router as auth_router
from app.api.email_router import email_router
from app.api.user_router import user_router
app = FastAPI(
    title="My FastAPI App",
    description="Demo FastAPI with Swagger UI",
    version="1.0.0"
)

# Include router
app.include_router(auth_router)
app.include_router(email_router)
app.include_router(user_router, tags=["User Profile"])

@app.get("/")
def read_root():
    return {"message": "Hello FastAPI"}


