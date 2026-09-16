import importlib
import sys


def test_package_structure_imports() -> None:
    """Verifies all foundational architecture packages exist and import cleanly."""
    packages = [
        "app",
        "app.api",
        "app.core",
        "app.domain",
        "app.services",
        "app.infrastructure",
        "app.infrastructure.ai",
        "app.infrastructure.db",
        "app.schemas",
    ]
    for pkg in packages:
        module = importlib.import_module(pkg)
        assert module is not None


def test_domain_isolation_boundaries() -> None:
    """Verifies domain package is cleanly isolated from infrastructure and API frameworks."""
    import app.domain

    domain_module_name = app.domain.__name__

    # Assert domain submodules do not import prohibited frameworks
    prohibited_frameworks = ["fastapi", "sqlalchemy", "pydantic", "httpx"]

    for mod_name, mod in list(sys.modules.items()):
        if mod_name.startswith(domain_module_name) and mod is not None:
            # Check module globals / attributes for prohibited imports
            for prohibited in prohibited_frameworks:
                assert prohibited not in getattr(mod, "__dict__", {}), (
                    f"Domain submodule '{mod_name}' imports prohibited framework '{prohibited}'"
                )


def test_audit_query_service_dependency_inversion() -> None:
    """Verifies AuditQueryService imports zero FastAPI, SQLAlchemy, or concrete repositories."""
    import app.services.audit_query_service as mod

    mod_dict = getattr(mod, "__dict__", {})
    prohibited = [
        "fastapi",
        "sqlalchemy",
        "SQLAlchemyRiskIncidentRepository",
        "SQLAlchemyAuditRepository",
    ]

    for key, val in mod_dict.items():
        assert key not in prohibited, f"AuditQueryService imports prohibited symbol '{key}'"
        if hasattr(val, "__module__") and val.__module__:
            assert "fastapi" not in val.__module__, f"Prohibited import fastapi in '{key}'"
            assert "sqlalchemy" not in val.__module__, f"Prohibited import sqlalchemy in '{key}'"
            assert "infrastructure" not in val.__module__, (
                f"Prohibited import infrastructure in '{key}'"
            )
