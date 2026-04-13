"""
Pydantic 数据模型
定义 API 请求和响应的数据模型
"""
from typing import List
from pydantic import BaseModel


class ProjectRequest(BaseModel):
    """项目请求模型"""
    owner: str
    repo: str


class MultiProjectRequest(BaseModel):
    """多项目请求模型"""
    projects: List[ProjectRequest]


class PRDetailsRequest(BaseModel):
    """PR详细信息请求模型"""
    owner: str
    repo: str
    pr_numbers: List[int]
