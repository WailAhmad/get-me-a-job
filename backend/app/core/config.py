from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "ApplyPilot AI"
    api_prefix: str = "/api"
    database_url: str = "sqlite:///./applypilot.db"
    frontend_origin: str = "http://localhost:3000"
    frontend_origin_127: str = "http://127.0.0.1:3000"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    seed_demo_data: bool = False


settings = Settings()
