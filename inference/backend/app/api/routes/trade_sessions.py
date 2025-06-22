from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db import models, schemas, crud
from app.api.deps import get_db

router = APIRouter()

@router.get("/", response_model=list[schemas.TradeSessionResponse])
def get_trade_sessions(
    skip: int = 0, 
    limit: int = 100, 
    db: Session = Depends(get_db)
) -> list[schemas.TradeSessionResponse]:
    """
    Retrieve a list of trade sessions with pagination.
    """
    return crud.get_trade_sessions(db, skip=skip, limit=limit)

@router.get("/{session_id}", response_model=schemas.TradeSessionResponse)
def get_trade_session(
    session_id: int, 
    db: Session = Depends(get_db)
) -> schemas.TradeSessionResponse:
    """
    Retrieve a specific trade session by its ID.
    """
    session = crud.get_trade_session(db, session_id=session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Trade session not found")
    return session

@router.post("/", response_model=schemas.TradeSessionResponse)
def create_trade_session(
    session: schemas.TradeSessionCreate, 
    db: Session = Depends(get_db)
) -> schemas.TradeSessionResponse:
    """
    Create a new trade session.
    """
    return crud.create_trade_session(db, session=session)

@router.put("/{session_id}", response_model=schemas.TradeSessionResponse)
def update_trade_session(
    session_id: int, 
    session: schemas.TradeSessionCreate, 
    db: Session = Depends(get_db)
) -> schemas.TradeSessionResponse:
    """
    Update an existing trade session by its ID.
    """
    updated_session = crud.update_trade_session(db, session_id=session_id, session=session)
    if not updated_session:
        raise HTTPException(status_code=404, detail="Trade session not found")
    return updated_session

@router.delete("/{session_id}", response_model=schemas.TradeSessionResponse)
def delete_trade_session(
    session_id: int, 
    db: Session = Depends(get_db)
) -> schemas.TradeSessionResponse:
    """
    Delete a trade session by its ID.
    """
    deleted_session = crud.delete_trade_session(db, session_id=session_id)
    if not deleted_session:
        raise HTTPException(status_code=404, detail="Trade session not found")
    return deleted_session