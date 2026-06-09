from __future__ import annotations

from src.utils.summary_html import summary_plain_for_digest, summary_to_wechat_html_body
import mimetypes
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx


class WeChatDraftClient:
    def __init__(self, *, app_id: str, app_secret: str, author: str):
        self._app_id = app_id.strip()
        self._app_secret = app_secret.strip()
        self._author = (author or "小编").strip() or "小编"

    async def _token(self) -> str:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(
                "https://api.weixin.qq.com/cgi-bin/token",
                params={
                    "grant_type": "client_credential",
                    "appid": self._app_id,
                    "secret": self._app_secret,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        if data.get("errcode"):
            raise RuntimeError(f"token 获取失败: {data}")
        return str(data.get("access_token") or "")

    async def upload_local_cover(self, local_path: str) -> str:
        p = Path(local_path).expanduser().resolve()
        if not p.is_file():
            raise ValueError(f"封面文件不存在: {p}")
        token = await self._token()
        mime, _ = mimetypes.guess_type(str(p))
        files = {"media": (p.name, p.read_bytes(), mime or "image/jpeg")}
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                "https://api.weixin.qq.com/cgi-bin/material/add_material",
                params={"access_token": token, "type": "image"},
                files=files,
            )
            resp.raise_for_status()
            data = resp.json()
        if data.get("errcode"):
            raise RuntimeError(f"素材上传失败: {data}")
        return str(data.get("media_id") or "")

    async def upload_cover_from_url(self, image_url: str) -> str:
        if not (image_url or "").strip():
            raise ValueError("image_url 为空")
        token = await self._token()
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            img_resp = await client.get(image_url, headers={"User-Agent": "Mozilla/5.0"})
            img_resp.raise_for_status()
        content_type = (img_resp.headers.get("content-type") or "").split(";")[0].strip().lower()
        ext = mimetypes.guess_extension(content_type or "") or ".jpg"
        filename = Path(urlparse(image_url).path).name or f"cover{ext}"
        files = {"media": (filename, img_resp.content, content_type or "image/jpeg")}
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                "https://api.weixin.qq.com/cgi-bin/material/add_material",
                params={"access_token": token, "type": "image"},
                files=files,
            )
            resp.raise_for_status()
            data = resp.json()
        if data.get("errcode"):
            raise RuntimeError(f"URL 封面上传失败: {data}")
        return str(data.get("media_id") or "")

    async def add_draft(
        self,
        *,
        title: str,
        summary: str,
        source_url: str,
        thumb_media_id: str,
    ) -> dict[str, Any]:
        token = await self._token()
        body_html = summary_to_wechat_html_body(summary or "")
        content_html = (
            f"{body_html}"
            "<p><br/></p>"
            "<p><strong>引用说明</strong>：本文为基于公开网页内容的摘要整理，仅供信息参考，不构成任何投资或决策建议。</p>"
        )
        digest_text = summary_plain_for_digest(summary or "")
        payload = {
            "articles": [
                {
                    "title": (title or "未命名")[:64],
                    "author": self._author[:16],
                    "digest": digest_text[:120],
                    "content": content_html,
                    "content_source_url": (source_url or "")[:500],
                    "thumb_media_id": thumb_media_id,
                    "show_cover_pic": 1,
                }
            ]
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                "https://api.weixin.qq.com/cgi-bin/draft/add",
                params={"access_token": token},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
        if data.get("errcode"):
            raise RuntimeError(f"草稿创建失败: {data}")
        return data
