from __future__ import annotations

import argparse
from pathlib import Path

import boto3


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload a Lambda zip package to S3.")
    parser.add_argument("--file", required=True, help="Path to the local zip package.")
    parser.add_argument("--bucket", required=True, help="Destination S3 bucket.")
    parser.add_argument("--key", required=True, help="Destination S3 object key.")
    parser.add_argument("--region", default="ap-northeast-2", help="AWS region for the client.")
    args = parser.parse_args()

    file_path = Path(args.file).resolve()
    if not file_path.exists():
        raise SystemExit(f"Package not found: {file_path}")

    s3 = boto3.client("s3", region_name=args.region)
    extra_args = {"ContentType": "application/zip"}
    s3.upload_file(str(file_path), args.bucket, args.key, ExtraArgs=extra_args)

    head = s3.head_object(Bucket=args.bucket, Key=args.key)
    version_id = head.get("VersionId", "")

    print(f"bucket={args.bucket}")
    print(f"key={args.key}")
    if version_id:
        print(f"version_id={version_id}")


if __name__ == "__main__":
    main()
