import boto3, os
from fastapi import UploadFile
from botocore.config import Config
import mimetypes

s3_config = Config(
    retries={
        "max_attempts": 3,   # retry up to 3 times
        "mode": "standard",  # standard AWS retry mode
    }
)

s3 = boto3.client(
    "s3",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", "AKIAXW5OGZH2FVQHOXV2"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", "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"),
    region_name=os.getenv("AWS_REGION", "ap-southeast-1"),
    config=s3_config,  # ✅ add this line
)

BUCKET_NAME = os.getenv("AWS_BUCKET_NAME", "espark-nfc-project")

def upload_to_s3(file, filename: str):
    fileobj = getattr(file, "file", file)
    content_type = getattr(file, "content_type", None) or mimetypes.guess_type(filename)[0] or "application/octet-stream"

    s3.upload_fileobj(fileobj, BUCKET_NAME, filename, ExtraArgs={"ContentType": content_type})
    presigned_url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": BUCKET_NAME, "Key": filename},
        ExpiresIn=31536000,
    )
    return presigned_url


def delete_from_s3(filename: str):
    try:
        s3.delete_object(Bucket=BUCKET_NAME, Key=filename)
        return True
    except Exception as e:
        print(f"Error deleting file from S3: {e}")
        return False


