from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT_DIR / "assets"
DATA_DIR = ROOT_DIR / "data"
TEMP_DIR = ROOT_DIR / "temp"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    log_level: int = 20
    MONGO_DB_URI: str = "mongodb://localhost:27017"
    MONGO_DB_NAME: str = "VersusWorld"
    PAGE_ACCESS_TOKEN: str = ""
    FB_APP_ID: str = "460194157076033"
    FB_PAGE_ID: str = "2193680277385179"


def temp_dir() -> Path:
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    return TEMP_DIR
