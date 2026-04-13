"""
GitCode/AtomGit 数据获取模块
通过 AtomGit API v5 获取 PR 评论数据
"""
from .service import AtomGitService
from .config import ATOMGIT_CONFIG

__all__ = ['AtomGitService', 'ATOMGIT_CONFIG']
