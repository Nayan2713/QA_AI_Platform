import base64
import io
import logging
import os
from PIL import Image

logger = logging.getLogger(__name__)


class ImageCompressor:
    """
    Service for optimizing, resizing, and compressing screenshot images
    to reduce database payload size and disk storage overhead.
    """

    @staticmethod
    def compress_bytes(
        image_bytes: bytes,
        max_dim: int = 1280,
        quality: int = 75,
        format: str = "WEBP"
    ) -> bytes:
        """
        Compress raw image bytes by resizing to max_dim (preserving aspect ratio)
        and applying format-specific compression.

        :param image_bytes: Raw binary image data.
        :param max_dim: Maximum width or height in pixels.
        :param quality: Compression quality (1-100).
        :param format: Output image format ('WEBP', 'JPEG', 'PNG').
        :return: Compressed binary image bytes (or original bytes on error).
        """
        if not image_bytes:
            return image_bytes

        try:
            with Image.open(io.BytesIO(image_bytes)) as img:
                fmt = format.upper()
                
                # Resize if larger than max_dim in either dimension
                width, height = img.size
                if width > max_dim or height > max_dim:
                    img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

                # Color mode adjustments for target format
                if fmt in ["JPG", "JPEG"]:
                    if img.mode in ("RGBA", "LA", "P"):
                        # Convert alpha channels to solid white background for JPEG
                        background = Image.new("RGB", img.size, (255, 255, 255))
                        if img.mode == "P":
                            img = img.convert("RGBA")
                        background.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
                        img = background
                    elif img.mode != "RGB":
                        img = img.convert("RGB")
                elif fmt in ["WEBP", "PNG"]:
                    if img.mode not in ("RGB", "RGBA"):
                        img = img.convert("RGBA" if "transparency" in img.info else "RGB")

                output = io.BytesIO()
                save_kwargs = {"format": fmt, "optimize": True}
                if fmt in ["WEBP", "JPEG", "JPG"]:
                    save_kwargs["quality"] = quality

                img.save(output, **save_kwargs)
                compressed_data = output.getvalue()
                
                logger.debug(
                    f"Image compressed from {len(image_bytes)} to {len(compressed_data)} bytes "
                    f"({round((1 - len(compressed_data)/len(image_bytes)) * 100, 1)}% reduction)"
                )
                return compressed_data
        except Exception as e:
            logger.error(f"Image compression failed: {e}. Returning uncompressed bytes.")
            return image_bytes

    @classmethod
    def compress_base64(
        cls,
        b64_string: str,
        max_dim: int = 1280,
        quality: int = 75,
        format: str = "WEBP"
    ) -> str:
        """
        Compress a base64-encoded image string. Preserves data URI prefix if present.

        :param b64_string: Base64 image string (with or without data URI prefix).
        :param max_dim: Maximum width or height.
        :param quality: Compression quality (1-100).
        :param format: Output format ('WEBP', 'JPEG', 'PNG').
        :return: Base64 string of compressed image.
        """
        if not b64_string:
            return b64_string

        try:
            prefix = ""
            raw_b64 = b64_string

            # Extract data URI prefix if present (e.g. data:image/png;base64,...)
            if "," in b64_string:
                parts = b64_string.split(",", 1)
                prefix = parts[0] + ","
                raw_b64 = parts[1]

            image_bytes = base64.b64decode(raw_b64)
            compressed_bytes = cls.compress_bytes(
                image_bytes, max_dim=max_dim, quality=quality, format=format
            )

            # Update mime type in data URI prefix if format changed
            if prefix:
                mime_type = f"image/{format.lower()}"
                prefix = f"data:{mime_type};base64,"

            compressed_b64 = base64.b64encode(compressed_bytes).decode("utf-8")
            return f"{prefix}{compressed_b64}"
        except Exception as e:
            logger.error(f"Base64 image compression failed: {e}. Returning original string.")
            return b64_string

    @classmethod
    def compress_file(
        cls,
        file_path: str,
        max_dim: int = 1280,
        quality: int = 75,
        format: str = "WEBP"
    ) -> str:
        """
        Compress an image file stored on disk.

        :param file_path: Path to target file.
        :param max_dim: Maximum width or height.
        :param quality: Compression quality.
        :param format: Output image format.
        :return: Path to compressed image file.
        """
        if not os.path.exists(file_path):
            return file_path

        try:
            with open(file_path, "rb") as f:
                raw_bytes = f.read()

            compressed_bytes = cls.compress_bytes(
                raw_bytes, max_dim=max_dim, quality=quality, format=format
            )

            # Determine output filename extension based on format
            ext = f".{format.lower()}"
            base, old_ext = os.path.splitext(file_path)
            out_path = f"{base}{ext}" if old_ext.lower() != ext else file_path

            with open(out_path, "wb") as f:
                f.write(compressed_bytes)

            # Remove old file if extension changed
            if out_path != file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except OSError:
                    pass

            return out_path
        except Exception as e:
            logger.error(f"File image compression failed for {file_path}: {e}")
            return file_path


# Helper functions for module-level import
def compress_image_bytes(image_bytes: bytes, max_dim: int = 1280, quality: int = 75, format: str = "WEBP") -> bytes:
    return ImageCompressor.compress_bytes(image_bytes, max_dim=max_dim, quality=quality, format=format)


def compress_base64_image(b64_string: str, max_dim: int = 1280, quality: int = 75, format: str = "WEBP") -> str:
    return ImageCompressor.compress_base64(b64_string, max_dim=max_dim, quality=quality, format=format)


def compress_image_file(file_path: str, max_dim: int = 1280, quality: int = 75, format: str = "WEBP") -> str:
    return ImageCompressor.compress_file(file_path, max_dim=max_dim, quality=quality, format=format)
