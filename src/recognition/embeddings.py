from PIL import Image, ImageOps


class DinoEmbeddingModel:
    def __init__(self, name: str = "facebook/dinov2-small", device: str = "auto", batch_size: int = 16, offline: bool = True):
        import torch
        from transformers import AutoImageProcessor, AutoModel
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        if device in {"auto", "cpu"}:
            torch.set_num_threads(min(4, torch.get_num_threads()))
        self.name, self.batch_size = name, batch_size
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu") if device == "auto" else torch.device(device)
        self.processor = AutoImageProcessor.from_pretrained(name, local_files_only=offline)
        self.model = AutoModel.from_pretrained(name, local_files_only=offline).to(self.device).eval()

    def encode(self, images: list[Image.Image]):
        import torch
        import torch.nn.functional as F
        chunks = []
        with torch.inference_mode():
            for start in range(0, len(images), self.batch_size):
                # Square padding retains the entire crop and its aspect ratio.
                batch = [ImageOps.pad(im.convert("RGB"), (224, 224), color=(127, 127, 127))
                         for im in images[start:start+self.batch_size]]
                inputs = self.processor(images=batch, return_tensors="pt", do_resize=False, do_center_crop=False).to(self.device)
                vectors = self.model(**inputs).last_hidden_state[:, 0]
                # Keep embeddings on the accelerator. Moving every batch to CPU made
                # reference matching the dominant cost for large reference libraries.
                chunks.append(F.normalize(vectors, dim=1))
        return (torch.cat(chunks) if chunks else
                torch.empty((0, self.model.config.hidden_size), device=self.device))
