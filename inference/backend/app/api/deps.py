from app.db.session import SessionLocal

def get_db():
    """
    Dependency that provides a database session for each request.
    
    Yields:
        Session: A new database session.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()