from fastapi import FastAPI
from app.api.routes import router as api_router
from fastapi.middleware.cors import CORSMiddleware

import sys
import os

print("==Python Path==")
for path in sys.path:
    print(path)

print("== File system check ==")
print("Exists", os.path.exists("/usr/local/lib/python3.10/site-packages/trading_functions"))


app = FastAPI()

origins = [
    "http://localhost:3002",
    "http://localhost:3000",
    "http://localhost:3001",
    "https://rahulpradeep.com",
    "http://localhost:6202",
    "http://localhost:8501",
    "http://streamlit:8501",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")