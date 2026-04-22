from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    deepseek_api_key: str = Field(default="", alias="DEEPSEEK_API_KEY")
    deepseek_base_url: str = Field(default="https://api.deepseek.com", alias="DEEPSEEK_BASE_URL")
    deepseek_model: str = Field(default="deepseek-chat", alias="DEEPSEEK_MODEL")

    wechat_mp_app_id: str = Field(default="", alias="WECHAT_MP_APP_ID")
    wechat_mp_app_secret: str = Field(default="", alias="WECHAT_MP_APP_SECRET")
    wechat_mp_author: str = Field(default="小编", alias="WECHAT_MP_AUTHOR")
    wechat_mp_thumb_media_id: str = Field(default="", alias="WECHAT_MP_THUMB_MEDIA_ID")
    wechat_mp_thumb_local_path: str = Field(default="", alias="WECHAT_MP_THUMB_LOCAL_PATH")

    schedule_enabled: bool = Field(default=False, alias="SCHEDULE_ENABLED")
    schedule_timezone: str = Field(default="Asia/Shanghai", alias="SCHEDULE_TIMEZONE")
    schedule_morning_hour: int = Field(default=8, ge=0, le=23, alias="SCHEDULE_MORNING_HOUR")
    schedule_evening_hour: int = Field(default=20, ge=0, le=23, alias="SCHEDULE_EVENING_HOUR")

    search_queries: str = Field(default="低空经济,无人机,eVTOL", alias="SEARCH_QUERIES")
    # 目标站点（逗号分隔域名），搜索时优先按 site:domain 检索，再做全域检索
    search_target_sites: str = Field(default="", alias="SEARCH_TARGET_SITES")
    # 兼容根目录旧字段
    schedule_search_site_domain: str = Field(default="", alias="SCHEDULE_SEARCH_SITE_DOMAIN")
    search_max_results: int = Field(default=20, ge=1, le=100, alias="SEARCH_MAX_RESULTS")
    max_article_age_hours: int = Field(default=14, ge=0, le=168, alias="MAX_ARTICLE_AGE_HOURS")
    max_publish_per_run: int = Field(default=20, ge=1, le=50, alias="MAX_PUBLISH_PER_RUN")
    news_search_fallback: str = Field(default="all", alias="NEWS_SEARCH_FALLBACK")

    data_dir: str = Field(default="./data", alias="DATA_DIR")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    def parsed_queries(self) -> list[str]:
        raw = self.search_queries.strip()
        if not raw:
            return []
        return [x.strip() for x in raw.replace("，", ",").split(",") if x.strip()]

    def parsed_target_sites(self) -> list[str]:
        raw = self.search_target_sites.strip()
        if not raw:
            raw = self.schedule_search_site_domain.strip()
        if not raw:
            return []
        parts = [x.strip() for x in raw.replace("，", ",").split(",") if x.strip()]
        out: list[str] = []
        seen: set[str] = set()
        for p in parts:
            site = p.lower().replace("https://", "").replace("http://", "").strip().strip("/")
            if "/" in site:
                site = site.split("/", 1)[0]
            if site.startswith("www."):
                site = site[4:]
            if site and site not in seen:
                seen.add(site)
                out.append(site)
        return out

    def data_path(self) -> Path:
        p = Path(self.data_dir).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    def wechat_ready(self) -> bool:
        return bool(self.wechat_mp_app_id.strip() and self.wechat_mp_app_secret.strip())
