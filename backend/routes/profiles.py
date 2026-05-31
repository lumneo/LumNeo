# backend/routes/profiles.py
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
from backend.database import get_db

router = APIRouter(prefix="/api/profiles", tags=["profiles"])

class ProfileCreate(BaseModel):
    name: str
    tools: List[str] = []
    profile_prompt: str = ""
    temperature: float = Field(default=1.0, ge=0.0, le=2.0)
    top_p: float = Field(default=1.0, ge=0.0, le=1.0)
    top_k: int = Field(default=40, ge=1, le=100)
    frequency_penalty: float = Field(default=0.0, ge=-2.0, le=2.0) 
    presence_penalty: float = Field(default=0.0, ge=-2.0, le=2.0)

class ProfileResponse(BaseModel):
    id: int
    name: str
    tools: List[str]
    profile_prompt: str
    temperature: float
    top_p: float
    top_k: int
    frequency_penalty: float
    presence_penalty: float

# 创建角色
@router.post("/", response_model=ProfileResponse)
async def create_profile(profile: ProfileCreate):
    db = await get_db()
    tools_json = json.dumps(profile.tools)
    cursor = await db.execute(
        """INSERT INTO profiles 
           (name, tools, profile_prompt, temperature, top_p, top_k, frequency_penalty, presence_penalty)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (profile.name, tools_json, profile.profile_prompt,
         profile.temperature, profile.top_p, profile.top_k, profile.frequency_penalty, profile.presence_penalty)
    )
    await db.commit()
    profile_id = cursor.lastrowid
    await db.close()
    return {
        "id": profile_id,
        "name": profile.name,
        "tools": profile.tools,
        "profile_prompt": profile.profile_prompt,
        "temperature": profile.temperature,
        "top_p": profile.top_p,
        "top_k": profile.top_k,
        "frequency_penalty": profile.frequency_penalty,
        "presence_penalty": profile.presence_penalty
    }

# 更新角色
@router.put("/{profile_id}", response_model=ProfileResponse)
async def update_profile(profile_id: int, profile: ProfileCreate):
    db = await get_db()
    tools_json = json.dumps(profile.tools)
    cursor = await db.execute(
        """UPDATE profiles 
           SET name = ?, tools = ?, profile_prompt = ?,
               temperature = ?, top_p = ?, top_k = ?, frequency_penalty = ?, presence_penalty = ?
           WHERE id = ?""",
        (profile.name, tools_json, profile.profile_prompt,
         profile.temperature, profile.top_p, profile.top_k, profile.frequency_penalty, profile.presence_penalty,
         profile_id)
    )
    if cursor.rowcount == 0:
        await db.close()
        raise HTTPException(status_code=404, detail="角色不存在")
    await db.commit()
    await db.close()
    return {
        "id": profile_id,
        "name": profile.name,
        "tools": profile.tools,
        "profile_prompt": profile.profile_prompt,
        "temperature": profile.temperature,
        "top_p": profile.top_p,
        "top_k": profile.top_k,
        "frequency_penalty": profile.frequency_penalty,
        "presence_penalty": profile.presence_penalty
    }

# 获取所有角色
@router.get("/", response_model=List[ProfileResponse])
async def list_profiles():
    db = await get_db()
    cursor = await db.execute(
        """SELECT id, name, tools, profile_prompt,
                  temperature, top_p, top_k, frequency_penalty, presence_penalty
           FROM profiles"""
    )
    rows = await cursor.fetchall()
    await db.close()
    results = []
    for row in rows:
        results.append({
            "id": row[0],
            "name": row[1],
            "tools": __parse_tools(row[2]),
            "profile_prompt": row[3] or "",
            "temperature": row[4] if row[4] is not None else 1.0,
            "top_p": row[5] if row[5] is not None else 1.0,
            "top_k": row[6] if row[6] is not None else 40,
            "frequency_penalty": row[7] if row[7] is not None else 0.0,
            "presence_penalty": row[8] if row[8] is not None else 0.0
        })
    return results

@router.delete("/{profile_id}")
async def delete_profile(profile_id: int):
    db = await get_db()
    await db.execute("DELETE FROM profiles WHERE id = ?", (profile_id,))
    await db.commit()
    await db.close()
    return {"status": "ok"}

def __parse_tools(tools_str: str) -> List[str]:
    try:
        return json.loads(tools_str)
    except:
        return []