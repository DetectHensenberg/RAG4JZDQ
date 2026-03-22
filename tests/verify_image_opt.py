
import asyncio
import os
from pathlib import Path
from src.ingestion.storage.image_storage import ImageStorage
import numpy as np
from PIL import Image

async def test_image_optimization():
    db_path = "data/test_image_index.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    
    storage = ImageStorage(db_path=db_path, images_root="data/test_images")
    
    # Create a dummy "content" image (high gradient)
    content_img_path = "data/test_images/content.png"
    Path("data/test_images").mkdir(parents=True, exist_ok=True)
    
    # Noise pattern for high gradient
    data = np.random.randint(0, 255, (200, 200, 3), dtype=np.uint8)
    Image.fromarray(data).save(content_img_path)
    
    # Create a dummy "background" image (low gradient / flat color)
    bg_img_path = "data/test_images/background.png"
    data_bg = np.zeros((200, 200, 3), dtype=np.uint8) + 128
    Image.fromarray(data_bg).save(bg_img_path)
    
    print("Registering images...")
    storage.register_image("img_content", content_img_path)
    storage.register_image("img_bg", bg_img_path)
    
    print("Testing adetect_background...")
    is_bg_content = await storage.adetect_background("img_content", str(Path(content_img_path).resolve()))
    is_bg_bg = await storage.adetect_background("img_bg", str(Path(bg_img_path).resolve()))
    
    print(f"Content image is background: {is_bg_content} (Expected: False)")
    print(f"Background image is background: {is_bg_bg} (Expected: True)")
    
    # Check persistence
    meta_content = await storage.aget_image_metadata("img_content")
    meta_bg = await storage.aget_image_metadata("img_bg")
    
    print(f"Persisted is_background for content: {meta_content['is_background']}")
    print(f"Persisted is_background for bg: {meta_bg['is_background']}")
    
    # Test register_image with is_background
    storage.register_image(
        image_id="img_manual",
        file_path=content_img_path,
        is_background=1
    )
    meta_manual = await storage.aget_image_metadata("img_manual")
    print(f"Manual is_background: {meta_manual['is_background']} (Expected: 1)")
    
    storage.close()
    print("Test finished.")

if __name__ == "__main__":
    asyncio.run(test_image_optimization())
