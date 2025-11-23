from fastapi import FastAPI, File, UploadFile, HTTPException

# TO RUN SERVER type - uvicorn main:app --reload
# go to http://127.0.0.1:8000/docs
app = FastAPI()

# Getting image
@app.post("/upload/")
async def upload_img(file: UploadFile = File(...)):

    #if not file.content_type.startswith("image/"): # if not an image
    #    raise HTTPException(status_code=400, detail="File is not an Image") # temporary stop
    
    with open(f"uploads/{file.filename}", "wb") as f: #syntax for file opening
        f.write(file.file.read())
        
    return {"imgName": file.filename}