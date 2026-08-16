import base64
import io
import os
import unittest
from PIL import Image
from services.image_compressor import (
    ImageCompressor,
    compress_image_bytes,
    compress_base64_image,
    compress_image_file,
)


class ImageCompressorTestCase(unittest.TestCase):
    def setUp(self):
        # Create a test image in memory (2000x2000 Red RGBA image)
        img = Image.new("RGBA", (2000, 2000), color=(255, 0, 0, 128))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        self.raw_png_bytes = buf.getvalue()
        self.raw_b64_string = base64.b64encode(self.raw_png_bytes).decode("utf-8")
        self.data_uri_string = f"data:image/png;base64,{self.raw_b64_string}"

    def test_compress_bytes_resize_and_format(self):
        compressed = compress_image_bytes(
            self.raw_png_bytes, max_dim=800, quality=75, format="WEBP"
        )
        self.assertIsNotNone(compressed)
        self.assertLess(len(compressed), len(self.raw_png_bytes))

        # Open compressed image to verify dimensions
        with Image.open(io.BytesIO(compressed)) as out_img:
            w, h = out_img.size
            self.assertLessEqual(w, 800)
            self.assertLessEqual(h, 800)
            self.assertEqual(out_img.format, "WEBP")

    def test_compress_bytes_jpeg_conversion(self):
        compressed = compress_image_bytes(
            self.raw_png_bytes, max_dim=500, quality=70, format="JPEG"
        )
        with Image.open(io.BytesIO(compressed)) as out_img:
            self.assertEqual(out_img.format, "JPEG")
            self.assertEqual(out_img.mode, "RGB")

    def test_compress_base64_data_uri(self):
        result_b64 = compress_base64_image(
            self.data_uri_string, max_dim=600, quality=70, format="WEBP"
        )
        self.assertTrue(result_b64.startswith("data:image/webp;base64,"))
        
        # Verify decoded payload can be parsed as an image
        payload = result_b64.split(",", 1)[1]
        raw_decoded = base64.b64decode(payload)
        with Image.open(io.BytesIO(raw_decoded)) as out_img:
            self.assertEqual(out_img.format, "WEBP")
            w, h = out_img.size
            self.assertLessEqual(w, 600)

    def test_compress_file(self):
        test_file = "test_sample_screenshot.png"
        try:
            with open(test_file, "wb") as f:
                f.write(self.raw_png_bytes)

            out_file = compress_image_file(
                test_file, max_dim=1000, quality=75, format="WEBP"
            )
            self.assertTrue(os.path.exists(out_file))
            self.assertTrue(out_file.endswith(".webp"))
            self.assertLess(os.path.getsize(out_file), os.path.getsize(test_file) if os.path.exists(test_file) else 999999)
        finally:
            for path in [test_file, "test_sample_screenshot.webp"]:
                if os.path.exists(path):
                    try:
                        os.remove(path)
                    except OSError:
                        pass

    def test_invalid_input_fallback(self):
        # Invalid image bytes should return original bytes without crashing
        invalid_bytes = b"not an image data string"
        result = compress_image_bytes(invalid_bytes)
        self.assertEqual(result, invalid_bytes)


if __name__ == "__main__":
    unittest.main()
