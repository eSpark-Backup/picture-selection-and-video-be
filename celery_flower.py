import os
os.system("celery -A app.background_tasks.celery_app flower")
