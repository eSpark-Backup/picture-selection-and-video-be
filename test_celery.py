# test_celery.py
from app.background_tasks.celery_app import celery_app

@celery_app.task(name="test_task")
def test_task():
    print("Celery task executed successfully")
    return "ok"

if __name__ == "__main__":
    result = test_task.delay()
    print("Task dispatched, ID:", result.id)
