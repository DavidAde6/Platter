
#IMPORTS
from fastapi import FastAPI, Request, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import requests
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
templates = Jinja2Templates(directory="templates")

model = YOLO("last.pt")
rows = []

# ---------------------FUNCTIONS--------------------------------------------




#---------------------GET REQUESTS---------------------------------------
@app.get("/", response_class=HTMLResponse)
async def show_form(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "rows": None}
    )

# ---------------------POST REQUESTS----------------------------------------

# @app.post("/", response_class=HTMLResponse)
# async def handle_form(request: Request, name: str = Form(...)):
#     rows = search_usda(name)
#     return templates.TemplateResponse(
#         "index.html",
#         {"request": request, "rows": rows, "query": name}
#     )

# Getting image------------------------------------------------------------
@app.post("/", response_class=HTMLResponse)
async def upload_img(request: Request,file: UploadFile = File(...)):

    if not file.content_type.startswith("image/"): # if not an image
        raise HTTPException(status_code=400, detail="File is not an Image") # temporary stop

    content = await file.read()

    # Turn bytes into a Pillow Image
    try:
        image = Image.open(io.BytesIO(content)).convert("RGB")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid image file")

    # Uses AI on Image
    result = model.predict(image)
    r = result[0]

    # stores values
    top_idx = int(r.probs.top1)
    top_conf = float(r.probs.top1conf)
    class_name = r.names[top_idx].replace("_", " ") # the name u need

    #USDA QUERY USING NAME!
    url = "https://api.nal.usda.gov/fdc/v1/foods/search"
    params = {
        "api_key": API_KEY,
        "query": class_name,
        "pageSize": 15
    }

    # gets json data
    r = requests.get(url, params=params).json()
    foods = r["foods"]
    chosen_food = foods[0]
    # returns one with
    for food in foods:
        ids = {n["nutrientId"] for n in food.get("foodNutrients", []) if n.get("amount") is not None}
        if all(nid in ids for nid in NUTRIENT_ID):  # Has ALL needed
            chosen_food = food
            break
    
    macros = {}

    #gets nutrient info
    for i, n in enumerate(chosen_food.get("foodNutrients", [])):
        if n["nutrientId"] in NUTRIENT_ID:
            name = NUTRIENT_MAP[n["nutrientId"]]
            macros[name] = {
                "value": n["value"],
                "unit": n.get("unitName", "")
            }
    
    row = {
        "Food": chosen_food["description"],
        "fdcId": chosen_food["fdcId"],
        "Serving": f"{chosen_food.get('servingSize', 100)}g",
        "macros": macros
    }

    rows.append(row)
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "rows": rows, "query": class_name}
    )

