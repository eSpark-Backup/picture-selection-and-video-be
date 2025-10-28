import os
import mimetypes
import threading
import boto3
from fastapi import UploadFile
from typing import Any
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv
load_dotenv()

# ---- AWS CONFIG ----
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "AKIAXW5OGZH2FVQHOXV2")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "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")
AWS_REGION = os.getenv("AWS_REGION", "ap-southeast-1")
BUCKET_NAME = os.getenv("AWS_BUCKET_NAME", "espark-nfc-project")


# ---- OPTIMIZED CLIENT CONFIG ----
s3_config = Config(
    connect_timeout=5,
    read_timeout=30,
    max_pool_connections=50,
    retries={"max_attempts": 5, "mode": "adaptive"},
)

_session = boto3.session.Session()
s3 = _session.client(
    "s3",
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION,
    config=s3_config,
)

_s3_lock = threading.Lock()


# ---- INTERNAL MULTIPART UPLOAD ----
def _upload_multipart(fileobj, filename: str, content_type: str):
    """Handles large, high-speed multipart uploads."""
    from boto3.s3.transfer import TransferConfig

    transfer_config = TransferConfig(
        multipart_threshold=5 * 1024 * 1024,  # 5 MB
        multipart_chunksize=5 * 1024 * 1024,
        max_concurrency=10,  # parallel threads
        use_threads=True,
    )

    with _s3_lock:
        s3.upload_fileobj(
            fileobj,
            BUCKET_NAME,
            filename,
            ExtraArgs={"ContentType": content_type},
            Config=transfer_config,
        )


# ---- MAIN UPLOAD FUNCTION ----
def upload_to_s3(file: UploadFile | Any, filename: str) -> str:
    """
    Ultra-fast and reliable uploader.
    - Automatically detects MIME type
    - Uses multipart + parallel uploads
    - Returns presigned URL (valid 1 year)
    """
    try:
        fileobj = getattr(file, "file", file)
        content_type = (
            getattr(file, "content_type", None)
            or mimetypes.guess_type(filename)[0]
            or "application/octet-stream"
        )

        _upload_multipart(fileobj, filename, content_type)

        presigned_url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": BUCKET_NAME, "Key": filename},
            ExpiresIn=31536000,
        )
        return presigned_url

    except (BotoCoreError, ClientError) as e:
        raise RuntimeError(f"S3 upload failed for {filename}: {str(e)}")
    except Exception as e:
        raise RuntimeError(f"Unexpected upload error: {e}")


# ---- DELETE FUNCTION ----
def delete_from_s3(filename: str) -> bool:
    """Deletes a file from S3 safely with error handling."""
    try:
        with _s3_lock:
            s3.delete_object(Bucket=BUCKET_NAME, Key=filename)
        return True
    except Exception as e:
        print(f"Error deleting file from S3: {e}")
        return False
