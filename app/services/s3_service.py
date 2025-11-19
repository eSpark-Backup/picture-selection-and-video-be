import os
import io
import mimetypes
import logging
import threading
import boto3
from fastapi import UploadFile
from typing import Any, BinaryIO
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from boto3.s3.transfer import TransferConfig
from dotenv import load_dotenv

load_dotenv()

AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION")
BUCKET_NAME = os.getenv("AWS_BUCKET_NAME")

s3_config = Config(
    connect_timeout=3,
    read_timeout=25,
    max_pool_connections=100,
    retries={"max_attempts": 5, "mode": "adaptive"},
    tcp_keepalive=True,
)

_session = boto3.session.Session()
_s3_client = _session.client(
    "s3",
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION,
    config=s3_config,
)

_s3_lock = threading.Lock()

logger = logging.getLogger("s3_service")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

def _get_transfer_config(file_size: int | None = None) -> TransferConfig:
    if not file_size:
        file_size = 10 * 1024 * 1024

    if file_size < 10 * 1024 * 1024:
        return TransferConfig(
            multipart_threshold=10 * 1024 * 1024,
            use_threads=False,
        )

    concurrency = 16 if file_size < 200 * 1024 * 1024 else 20
    chunk_size = 8 * 1024 * 1024 if file_size < 500 * 1024 * 1024 else 16 * 1024 * 1024

    return TransferConfig(
        multipart_threshold=5 * 1024 * 1024,
        multipart_chunksize=chunk_size,
        max_concurrency=concurrency,
        use_threads=True,
    )

def upload_to_s3(file: UploadFile | Any, filename: str) -> str:
    try:
        fileobj: BinaryIO = getattr(file, "file", file)
        if not fileobj:
            raise ValueError("Invalid file object provided.")

        if hasattr(fileobj, "seek"):
            try:
                fileobj.seek(0)
            except Exception:
                pass

        file_size = None
        if hasattr(fileobj, "seek") and hasattr(fileobj, "tell"):
            try:
                pos = fileobj.tell()
                fileobj.seek(0, os.SEEK_END)
                file_size = fileobj.tell()
                fileobj.seek(pos)
            except Exception:
                pass

        content_type = (
            getattr(file, "content_type", None)
            or mimetypes.guess_type(filename)[0]
            or "application/octet-stream"
        )

        transfer_config = _get_transfer_config(file_size)

        with _s3_lock:
            _s3_client.upload_fileobj(
                Fileobj=fileobj,
                Bucket=BUCKET_NAME,
                Key=filename,
                ExtraArgs={"ContentType": content_type},
                Config=transfer_config,
            )

        # presigned_url = _s3_client.generate_presigned_url(
        #     "get_object",
        #     Params={"Bucket": BUCKET_NAME, "Key": filename},
        #     ExpiresIn=7 * 24 * 60 * 60,  # 7 days
        # )

        # logger.info(f"S3 upload success: {filename} ({file_size or 'unknown'} bytes)")
        # return presigned_url
        
        object_url = f"https://{BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{filename}"

        logger.info(f"S3 upload success: {filename} ({file_size or 'unknown'} bytes)")
        return object_url

    except (BotoCoreError, ClientError) as e:
        logger.error(f"S3 upload failed for {filename}: {e}")
        raise RuntimeError(f"S3 upload failed for {filename}: {e}") from e
    except Exception as e:
        logger.error(f"Unexpected upload error for {filename}: {e}")
        raise RuntimeError(f"Unexpected upload error: {e}") from e

def delete_from_s3(filename: str) -> bool:
    """Thread-safe deletion with retry logic."""
    try:
        with _s3_lock:
            _s3_client.delete_object(Bucket=BUCKET_NAME, Key=filename)
        logger.info(f"S3 delete success: {filename}")
        return True
    except Exception as e:
        logger.warning(f"Error deleting {filename} from S3: {e}")
        return False

def file_exists_in_s3(filename: str) -> bool:
    try:
        _s3_client.head_object(Bucket=BUCKET_NAME, Key=filename)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "404":
            return False
        raise

s3 = _s3_client