INPUT, FOR BOTH WEB & MOBILE

- User uploads their image
- FASTAPI enpoint gets the image plus metadata. Need to figure out how to extract and store metadata with it. Store all relevant information obtained in a MealUpload Object
- Store image in S3, even if rejected, store meal info and stuff in postgresql

IMAGE QUALITY

- Figure out algorithm for this, chat suggests that opencv/pillow, can check for blur, brightness, overexposure... using a formula, I'd have to do more research to see how much this can be trusted
- Another thing is use a small vision model or multimodal model to check if food is visible, plate is, food too cropped, dish is covered, food overlaps, no scale reference..., Identify concrete things to flag and develop a system for it.
- All this goes into another object, with all the necessary info and if anything is bad, it should most likely flag the meal

IMAGE STORAGE

- After that analysis, each image is stored correctly in S3, in folders that sort them. They can be useful in the future.
- Set up AWS RDS for Postresql
