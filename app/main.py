from fastapi import FastAPI, File, UploadFile, HTTPException
import cv2 as cv # might remove this as well as requirement
import numpy as np
from transformers import pipeline
from PIL import Image
import io

classifier = pipeline("image-classification", model="nateraw/food")

# TO RUN SERVER type - uvicorn main:app --reload
# go to http://127.0.0.1:8000/docs

app = FastAPI()

# Getting image
@app.post("/upload/")
async def upload_img(file: UploadFile = File(...)):

    if not file.content_type.startswith("image/"): # if not an image
        raise HTTPException(status_code=400, detail="File is not an Image") # temporary stop

    content = await file.read()

    # Turn bytes into a Pillow Image
    try:
        image = Image.open(io.BytesIO(content)).convert("RGB")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid image file")

    result = classifier(image)

    return {"imgName": result} 