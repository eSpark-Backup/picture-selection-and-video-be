import boto3, os
from fastapi import UploadFile

s3 = boto3.client(
    "s3",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", "AKIAXW5OGZH2FVQHOXV2"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", "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"),
    region_name=os.getenv("AWS_REGION", "ap-south-1"),
)

BUCKET_NAME = os.getenv("AWS_BUCKET_NAME", "espark-nfc-project")


def upload_to_s3(file: UploadFile, filename: str):
    s3.upload_fileobj(file.file, BUCKET_NAME, filename, ExtraArgs={"ContentType": file.content_type})
    file_url = f"https://{BUCKET_NAME}.s3.amazonaws.com/{filename}"
    return file_url
