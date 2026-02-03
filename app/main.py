
#IMPORTS
from fastapi import FastAPI, File, UploadFile, HTTPException
#from transformers import pipeline
from pydantic import BaseModel # data validation & parsing
from PIL import Image # IMAGE HANDLING
import io
from dotenv import load_dotenv
import os
import requests
from ultralytics import YOLO

# TO RUN SERVER type - uvicorn main:app --reload
# go to http://127.0.0.1:8000/docs

load_dotenv()

#VARIABLES-----------------------------------------------------------------

API_KEY = os.environ["USDA_API_KEY"] # getting usda key for access
#classifier = pipeline("image-classification", model="nateraw/food")
app = FastAPI()
NUTRIENT_ID = [1008, 1005, 1003, 1079, 2000, 1004, 1257, 1258, 1292, 1293]
NUTRIENT_NAME = ['Energy', 'Carbohydrate', 'Protein', 'Fiber', 'Sugars', 'Total Fat', 'Trans Fat', 'Saturated fats', 'Monosaturated fats', 'Polysaturated fats']
NUTRIENT_MAP = dict(zip(NUTRIENT_ID, NUTRIENT_NAME))

model = YOLO("yolov8n-cls.pt")


# ---------------------FUNCTIONS--------------------------------------------

# This function takes an image and returns the name






# ---------------------POST REQUESTS----------------------------------------


# Getting image------------------------------------------------------------
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

    # Uses AI on Image
    result = classifier(image)

    return {"imgName": result} 


# Searching USDA------------------------------------------------
class FoodQuery(BaseModel):
    name: str

@app.post("/usda/search")
async def search_usda(query: FoodQuery):
    url = "https://api.nal.usda.gov/fdc/v1/foods/search"
    params = {
        "api_key": API_KEY,
        "query": query.name,
        "pageSize": 15
    }

    # gets json data
    r = requests.get(url, params=params).json()
    foods = r["foods"]

    # returns one with
    for food in foods:
        ids = {n["nutrientId"] for n in food.get("foodNutrients", []) if n.get("amount") is not None}
        if all(nid in ids for nid in NUTRIENT_ID):  # Has ALL needed
            return food
    
    macros = {}

    #gets nutrient info
    for i, n in enumerate(food.get("foodNutrients", [])):
        if n["nutrientId"] in NUTRIENT_ID:
            name = NUTRIENT_MAP[n["nutrientId"]]
            macros[name] = {
                "value": n["value"],
                "unit": n.get("unitName", "")
            }
    

    return {
        "Food": food["description"],
        "fdcId": food["fdcId"],
        "Serving": f"{food.get('servingSize', 100)}g",
        "macros": macros
    }


