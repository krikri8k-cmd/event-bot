#!/usr/bin/env python3
"""
API для работы с ракетами пользователей
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from rockets_service import add_rockets, get_user_rockets, spend_rockets

app = FastAPI()


class RocketRequest(BaseModel):
    user_id: int
    amount: int
    reason: str = ""


@app.get("/rockets/{user_id}")
async def get_rockets(user_id: int):
    """Получить количество ракет пользователя"""
    rockets = get_user_rockets(user_id)
    return {"user_id": user_id, "rockets": rockets}


@app.post("/rockets/add")
async def add_rockets_endpoint(request: RocketRequest):
    """Добавить ракеты пользователю"""
    success = add_rockets(request.user_id, request.amount, request.reason)
    if success:
        new_balance = get_user_rockets(request.user_id)
        return {"success": True, "new_balance": new_balance}
    else:
        raise HTTPException(status_code=400, detail="Failed to add rockets")


@app.post("/rockets/spend")
async def spend_rockets_endpoint(request: RocketRequest):
    """Потратить ракеты пользователя"""
    success = spend_rockets(request.user_id, request.amount, request.reason)
    if success:
        new_balance = get_user_rockets(request.user_id)
        return {"success": True, "new_balance": new_balance}
    else:
        raise HTTPException(status_code=400, detail="Insufficient rockets or user not found")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
