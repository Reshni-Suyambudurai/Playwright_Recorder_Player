"""Pydantic models for API request validation"""
from pydantic import BaseModel


class URLRequest(BaseModel):
    """Request model for opening a URL"""
    url: str


class CoordinatesRequest(BaseModel):
    """Request model for finding element at coordinates"""
    x: int
    y: int
