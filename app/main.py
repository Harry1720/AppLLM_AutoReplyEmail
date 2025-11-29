from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from app.api.auth_router import router as auth_router
from app.api.email_router import email_router
from app.api.user_router import user_router
from app.api.ai_router import ai_router
app = FastAPI(
    title="My AutoReplyEmail App",
    description="Demo AutoReplyEmail with Swagger UI",
    version="1.0.0"
)

# Thêm CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include router
app.include_router(auth_router, tags=["Authentication"])
app.include_router(email_router, tags=["Email Management"])
app.include_router(user_router, tags=["User Profile"])
app.include_router(ai_router, tags=["AI Agents"])


@app.get("/")
def read_root():
    return {"message": "Hello FastAPI"}