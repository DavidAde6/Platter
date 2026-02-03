import os, random, shutil
random.seed(42)

SRC = "../data/images"            # current 22 folders
TRAIN = "../data/train"
VAL = "../data/val"

os.makedirs(TRAIN, exist_ok=True)
os.makedirs(VAL, exist_ok=True)

for cls in os.listdir(SRC):
    src_dir = os.path.join(SRC, cls)
    files = [f for f in os.listdir(src_dir) if f.lower().endswith((".jpg", ".png", ".jpeg"))]
    random.shuffle(files)
    split = int(0.8 * len(files))
    train_files = files[:split]
    val_files = files[split:]

    os.makedirs(os.path.join(TRAIN, cls), exist_ok=True)
    os.makedirs(os.path.join(VAL, cls), exist_ok=True)

    for f in train_files:
        shutil.copy2(os.path.join(src_dir, f), os.path.join(TRAIN, cls, f))
    for f in val_files:
        shutil.copy2(os.path.join(src_dir, f), os.path.join(VAL, cls, f))
