# Use a pipeline as a high-level helper
from transformers import pipeline

model = pipeline("image-to-text", model="ardaocak/llava-1.5-7b-food-calorie-estimator")
response = model("")