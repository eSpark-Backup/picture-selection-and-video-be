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

| Action | Command |
|--------|----------|
| Restart the app | sudo systemctl restart fastapi |
| Stop the app | sudo systemctl stop fastapi |
| View logs | sudo journalctl -u fastapi -f |
| Edit environment variables | sudo nano /path/to/project/.env |

---

**Deployment Completed**  
Your FastAPI backend is now live and running on the server.  
You can connect your frontend or API testing tools to your deployed instance.
