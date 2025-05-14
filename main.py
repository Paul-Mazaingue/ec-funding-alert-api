from fastapi import FastAPI
from app.routes import router
from src.core import periodic_checker, weekly_facet_api_task

from contextlib import asynccontextmanager
import asyncio
import logging

# Lifespan event handler
@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_event_loop()
    loop.create_task(periodic_checker())
    loop.create_task(weekly_facet_api_task())
    logging.info("Background task started.")
    yield

app = FastAPI(lifespan=lifespan)

# Include routes
app.include_router(router)