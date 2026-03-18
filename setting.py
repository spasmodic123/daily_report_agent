import os

from starlette.config import Config
from pydantic_settings import BaseSettings


script_dir = os.path.abspath(os.path.dirname(__file__))
env_path = os.path.join(script_dir, ".env.example")
config = Config(env_path if os.path.exists(env_path) else None)

print(f"using env file: {env_path if os.path.exists(env_path) else 'None'}")


class ApplicationSettings(BaseSettings):
    """
    Service Settings
    """

    QWEN_API_KEY: str = config("QWEN_API_KEY")
    APP_ID: str = config("APP_ID")
    QWEN_MODEL: str = config("QWEN_MODEL")
    DING_ACCESS_TOKEN: str = config("DING_ACCESS_TOKEN")
    DING_SECRET: str = config("DING_SECRET")


class Settings(
    ApplicationSettings,
):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


settings = Settings()
