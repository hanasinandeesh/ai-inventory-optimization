from app.core.config import Settings


def test_default_settings() -> None:
    settings = Settings()
    assert settings.PROJECT_NAME == "AI-Driven Inventory Optimization & Fulfillment Intelligence"
    assert settings.VERSION == "0.1.0"
    assert settings.API_V1_STR == "/api/v1"
    assert settings.ENVIRONMENT in ["development", "testing", "staging", "production"]
    assert isinstance(settings.DEBUG, bool)
    assert settings.DATABASE_URL.startswith("sqlite")
