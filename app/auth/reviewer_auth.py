from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.database.connection import get_db
from app.models.reviewer import Reviewer
import jwt, os

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/reviewer/login")
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "supersecretkey")


def get_current_reviewer(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        reviewer_id: int = payload.get("reviewer_id")

        if reviewer_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token.",
            )

        reviewer = db.query(Reviewer).filter(Reviewer.id == reviewer_id).first()

        if not reviewer:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Reviewer not found.",
            )

        return reviewer

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired.",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token.",
        )
