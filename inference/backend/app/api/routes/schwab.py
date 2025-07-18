from urllib import response
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from app.methods.schwab_methods import (
    get_schwab_config, 
    exchange_code_for_token, 
    update_schwab_config,
    check_schwab_connection
)

router = APIRouter()

@router.get("/callback", response_class=HTMLResponse)
async def schwab_callback(request: Request):
    """
    Handle the callback from Schwab after user authorization.
    """
    try:
        # Extract the authorization code from the request
        auth_code = request.query_params.get('code')
        if not auth_code:
            raise HTTPException(status_code=400, detail="Authorization code not found in the request.")

        # Exchange the authorization code for an access token
        schwab_config = get_schwab_config()
        token_response = exchange_code_for_token(auth_code, schwab_config)
        if not token_response:
            raise HTTPException(status_code=500, detail="Failed to exchange authorization code for access token.")
        access_token = token_response.get("access_token")
        refresh_token = token_response.get("refresh_token")
        if not access_token or not refresh_token:
            raise HTTPException(status_code=500, detail="Access token or refresh token not found in the response.")

        # Update the configuration with the new tokens
        update_schwab_config("access_token", access_token)
        update_schwab_config("refresh_token", refresh_token)

        # Return a success message with the token information
        return HTMLResponse(content=f"Authorization successful!<br/> Access Token and refresh token updated in the configuration file.<br/>")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

@router.get("/check_connection")
async def check_connection():
    """
    Check the connection to the Schwab API.
    """
    try:
        schwab_config = get_schwab_config()
        connection_status = check_schwab_connection(schwab_config)
        return connection_status
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))