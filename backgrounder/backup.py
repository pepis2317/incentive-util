import datetime
import gzip
import os
import shutil
import sqlite3
import threading
from signal import SIGINT, SIGTERM, signal

import boto3

DB_PATH = os.environ.get("DB_PATH", "../data/incentive-util.db")
INTERVAL = int(os.environ.get("BACKUP_INTERVAL_SECONDS", 6*3600))

stop = threading.Event()
signal(SIGTERM, lambda *_: stop.set())
signal(SIGINT, lambda *_: stop.set())

s3 = boto3.client(
    "s3",
    aws_access_key_id=os.environ["S3_KEY_ID"],
    aws_secret_access_key=os.environ["S3_SECRET"],
)
BUCKET = os.environ["S3_BUCKET"]

def run_backup():
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snap = f"/tmp/backup_{stamp}.db"
    gz = snap + ".gz"
    try:
        src = sqlite3.connect(DB_PATH)
        dst = sqlite3.connect(snap)
        with dst:
            src.backup(dst)
        dst.close(); src.close()

        with open(snap, "rb") as fi, gzip.open(gz, "wb") as fo:
            shutil.copyfileobj(fi, fo)

        s3.upload_file(gz, BUCKET, f"backups/{stamp}.db.gz")
        print(f"backup ok: {stamp}", flush=True)
    finally:
        for p in (snap, gz):
            if os.path.exists(p):
                os.remove(p)

if __name__ == "__main__":
    while not stop.is_set():
        try:
            run_backup()
        except Exception as e:
            print(f"backup failed: {e}", flush=True)
        stop.wait(INTERVAL)