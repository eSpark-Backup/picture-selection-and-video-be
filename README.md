# FastAPI Backend Deployment Guide

This guide explains how to deploy the FastAPI backend for this project on a production server from start to finish.

---

## Step 1: Clone the Repository

```bash
git clone <repository_url>
cd <project_folder_name>
```

## Step 2: Create a Virtual Environment

Create an isolated Python environment for the project.

**For Linux / macOS:**

```bash
python3 -m venv venv
source venv/bin/activate
```

**For Windows:**

```bash
python -m venv venv
venv\Scripts\activate
```

## Step 3: Install Dependencies

Install all required Python packages.

```bash
pip install -r requirements.txt
```

## Step 4: Configure Environment Variables

Copy the example environment file:

**Linux / macOS:**

```bash
cp .env.example .env
```

**Windows (PowerShell):**

```bash
copy .env.example .env
```

Then open `.env` and set your environment variables.

**Database configuration:**

```ini
DB_USER=postgres
DB_PASS=your_password
DB_HOST=localhost
DB_PORT=5432
DB_NAME=photo_video_db
```

**JWT secret key:**

```ini
JWT_SECRET_KEY=your_secret_key
```

**AWS S3 configuration:**

```ini
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret
AWS_REGION=ap-southeast-1
AWS_BUCKET_NAME=your_bucket_name
```

## Step 5: Setup PostgreSQL Database

Log into PostgreSQL:

```bash
psql -U postgres
```

Create a new database:

```sql
CREATE DATABASE photo_video_db;
```

(Optional) Create a database user with password and grant privileges:

```sql
CREATE USER your_username WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE photo_video_db TO your_username;
```

## Step 6: Run Database Initialization (if applicable)

If your project includes a script to initialize tables or migrations, run it:

```bash
python app/database/init_db.py
```

## Step 7: Start the FastAPI Server

For development:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Visit the app at:

```
http://<server-ip>:8000/docs
```

## Step 8: Run FastAPI in Production

**Linux/macOS (Recommended):**

Install Gunicorn and Uvicorn worker:

```bash
pip install gunicorn uvicorn
```

Run the app using Gunicorn:

```bash
gunicorn -w 4 -k uvicorn.workers.UvicornWorker app.main:app --bind 0.0.0.0:8000
```

**Windows (Alternative):**
Use Uvicorn directly since Gunicorn and systemd are not supported on Windows.

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Step 9: Create a systemd Service (Linux Only)

To keep the app running in the background:

Create a systemd service file:

```bash
sudo nano /etc/systemd/system/fastapi.service
```

Add the following content:

```ini
[Unit]
Description=FastAPI Application
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/path/to/your/project
Environment="PATH=/path/to/your/project/venv/bin"
ExecStart=/path/to/your/project/venv/bin/gunicorn -w 4 -k uvicorn.workers.UvicornWorker app.main:app --bind 0.0.0.0:8000
Restart=always

[Install]
WantedBy=multi-user.target
```

Save and enable the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable fastapi
sudo systemctl start fastapi
```

Check if it’s running:

```bash
sudo systemctl status fastapi
```

## Step 10: Verify Deployment

Visit your server at:

```
http://<server-ip>:8000/docs
```

Check logs in real-time:

```bash
sudo journalctl -u fastapi -f
```

## Step 11: Common Maintenance Commands (Linux)

| Action                     | Command                         |
| -------------------------- | ------------------------------- |
| Restart the app            | sudo systemctl restart fastapi  |
| Stop the app               | sudo systemctl stop fastapi     |
| View logs                  | sudo journalctl -u fastapi -f   |
| Edit environment variables | sudo nano /path/to/project/.env |

---

**Deployment Completed**  
Your FastAPI backend is now live and running on the server.  
You can connect your frontend or API testing tools to your deployed instance.

# Celery & Redis Background Processing Setup Guide

This guide explains how to set up **Celery** and **Redis** for background task processing in this FastAPI backend project.

---

## Step 1: Install Dependencies

Make sure Celery and Redis dependencies are installed.

```bash
pip install celery redis
```

If not already installed, add them to your requirements:

```bash
pip freeze > requirements.txt
```

---

## Step 2: Configure Environment Variables

Ensure your `.env` file includes the Redis connection URL:

```ini
REDIS_URL=redis://localhost:6379/0
```

If you're deploying to a remote server, replace `localhost` with your server's Redis hostname or IP.

---

## Step 3: Redis Installation

### For Linux (Ubuntu):

```bash
sudo apt update
sudo apt install redis-server -y
sudo systemctl enable redis-server
sudo systemctl start redis-server
sudo systemctl status redis-server
```

### For macOS:

```bash
brew install redis
brew services start redis
```

### For Windows (WSL Recommended):

Use Ubuntu (WSL) and install Redis inside it using the Linux instructions above.

Verify Redis is running:

```bash
redis-cli ping
```

Expected output:

```
PONG
```

---

## Step 4: Celery Configuration

Celery setup files are located in the project under `app/background_tasks`.

### File: `app/background_tasks/celery_app.py`

Defines the main Celery app and connects it to Redis.

### File: `app/background_tasks/tasks.py`

Contains all registered background tasks:

- `upload_original_photos_task`
- `process_photos_task`
- `create_video_for_user_task`

### Root Files:

- `celery_worker.py`: Starts the Celery worker.
- `celery_flower.py`: Starts the Celery monitoring dashboard.

---

## Step 5: Run Celery Worker

Start the worker process to execute background tasks.

**Linux / macOS:**

```bash
python celery_worker.py
```

**Windows (Git Bash or PowerShell):**

```bash
python celery_worker.py
```

You should see logs like:

```
celery@your-host ready.
```

---

## Step 6: Start Flower Dashboard (Optional but Recommended)

Flower is a powerful web UI to monitor Celery tasks.

```bash
python celery_flower.py
```

Visit the dashboard in your browser:

```
http://localhost:5555
```

---

## Step 7: Integration with FastAPI Routes

The following background tasks are automatically triggered by your API endpoints:

| Task                          | Triggered Route                        |
| ----------------------------- | -------------------------------------- |
| `upload_original_photos_task` | `/api/v1/user/upload-original-photos`  |
| `process_photos_task`         | `/api/v1/user/submit-processed-photos` |
| `create_video_for_user_task`  | `/api/v1/reviewer/create-video`        |

These tasks now run **asynchronously**, allowing the API to respond immediately while heavy operations continue in the background.

---

## Step 8: Production Deployment

### 1. Run Redis as a service

Ensure Redis is running persistently on your server.

### 2. Run Celery with systemd (Linux only)

Create a Celery service file:

```bash
sudo nano /etc/systemd/system/celery.service
```

Add the following content (adjust paths accordingly):

```ini
[Unit]
Description=Celery Background Worker
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/path/to/project
Environment="PATH=/path/to/project/venv/bin"
ExecStart=/path/to/project/venv/bin/python /path/to/project/celery_worker.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Then enable and start it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable celery
sudo systemctl start celery
sudo systemctl status celery
```

---

## Step 9: Verify Everything Works

1. Start Redis

   ```bash
   redis-server
   ```

2. Start Celery Worker

   ```bash
   python celery_worker.py
   ```

3. Start FastAPI

   ```bash
   python run.py
   ```

4. (Optional) Start Flower
   ```bash
   python celery_flower.py
   ```

Then hit API routes from Postman or frontend.  
The background tasks will process independently of API responses.

---

**✅ Background Processing Setup Complete**  
Celery and Redis are now fully configured for distributed background task execution.
