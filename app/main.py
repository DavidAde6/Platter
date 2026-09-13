from fastapi import Depends, FastAPI, File, HTTPException, Query, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from pathlib import Path

from auth import create_access_token, get_current_user_id
from image_metadata import extract_image_metadata
from meals import (
    MealDetail,
    MealPublic,
    MealUploadResponse,
    create_meal_with_metadata,
    get_meal_for_user,
    get_meal_image_ref,
    list_meals_for_user,
)
from storage import fetch_meal_image
from users import (
    AuthResponse,
    LoginRequest,
    SignupRequest,
    UpdateUserRequest,
    UserPublic,
    authenticate_user,
    create_user,
    get_user_by_id,
    update_user,
)

BASE_DIR = Path(__file__).resolve().parent

# TO RUN SERVER (from the app/ directory):
#   cd app
#   uvicorn main:app --reload
# go to http://127.0.0.1:8000/docs
# cd frontend
# npm run dev

load_dotenv(BASE_DIR / ".env")

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8080",
        "https://useplatter.ca",
        "https://www.useplatter.ca",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
}

MAX_FILE_SIZE_BYTES = 15 * 1024 * 1024  # 15 MB


@app.get("/")
async def root():
    return {"message": "Platter backend is running"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/api/auth/signup", response_model=AuthResponse)
async def signup(body: SignupRequest):
    try:
        user = create_user(body)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    token = create_access_token(user.user_id)
    return AuthResponse(access_token=token, user=user)


@app.post("/api/auth/login", response_model=AuthResponse)
async def login(body: LoginRequest):
    user = authenticate_user(body)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token(user.user_id)
    return AuthResponse(access_token=token, user=user)


@app.get("/api/users/me", response_model=UserPublic)
async def get_me(user_id: int = Depends(get_current_user_id)):
    user = get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@app.patch("/api/users/me", response_model=UserPublic)
async def patch_me(
    body: UpdateUserRequest,
    user_id: int = Depends(get_current_user_id),
):
    user = update_user(user_id, body)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@app.get("/api/meals", response_model=list[MealPublic])
async def get_meals(
    limit: int = Query(default=100, ge=1, le=200),
    user_id: int = Depends(get_current_user_id),
):
    return list_meals_for_user(user_id, limit=limit)


@app.get("/api/meals/{meal_id}", response_model=MealDetail)
async def get_meal(meal_id: int, user_id: int = Depends(get_current_user_id)):
    """One meal with its gate verdict and identified foods.

    Everything a calorie or macro display needs is here, including
    `nutrition_ready` -- which is the flag to branch on, not `status`.
    """
    meal = get_meal_for_user(user_id, meal_id)
    if meal is None:
        # Also the response for a meal owned by someone else: a caller must
        # not be able to distinguish "not yours" from "does not exist".
        raise HTTPException(status_code=404, detail="Meal not found")
    return meal


@app.get("/api/meals/{meal_id}/image")
def get_meal_image(
    meal_id: int,
    variant: str = "thumbnail",
    user_id: int = Depends(get_current_user_id),
):
    # Kept as input validation so a typo is a 400 rather than a 404. The
    # value itself is now a bound query parameter against meal_images.role,
    # not a lookup into a map of column names.
    if variant not in ("original", "thumbnail"):
        raise HTTPException(status_code=400, detail="Invalid image variant")

    ref = get_meal_image_ref(user_id, meal_id, variant)
    if ref is None:
        raise HTTPException(status_code=404, detail="Image not found")

    try:
        content, fetched_content_type = fetch_meal_image(ref.object_key)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return Response(
        content=content,
        # Prefer what we recorded at upload time over whatever R2 echoes back.
        media_type=ref.content_type or fetched_content_type,
        # private: only this authenticated user; never store in shared caches.
        headers={"Cache-Control": "private, max-age=3600"},
    )


@app.post("/api/upload", response_model=MealUploadResponse)
async def upload_img(
    image: UploadFile = File(...),
    user_id: int = Depends(get_current_user_id),
):
    content = await image.read()

    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    if image.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {image.content_type}",
        )

    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="File too large")

    try:
        metadata = extract_image_metadata(content, image)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        return create_meal_with_metadata(
            user_id,
            "web_upload",
            metadata,
            content,
            image.content_type or "application/octet-stream",
            image.filename,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Failed to store meal upload") from exc
