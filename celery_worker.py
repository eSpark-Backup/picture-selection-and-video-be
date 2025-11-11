# from app.background_tasks.celery_app import celery_app

# if __name__ == "__main__":
#     celery_app.worker_main(["worker", "--loglevel=info", "--pool=solo"])

from app.background_tasks.celery_app import celery_app

if __name__ == "__main__":
    celery_app.worker_main([
        "worker",
        "--loglevel=info",
        "--concurrency=4",
        "--time-limit=3600",
        "--soft-time-limit=3500",
        "--prefetch-multiplier=1",
        "--queues=default"
    ])
