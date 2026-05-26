# Function Signature Catalog

This catalog records callable shell surfaces created during bootstrap.

## API Entrypoint

```python
from apps.api.main import app
```

## App Factory

```python
def create_app(settings: Settings | None = None) -> FastAPI
```

## Route Profiles

```python
def get_route_profile(name: str | ApiProfileName) -> ApiRouteProfile
def register_routes(app: FastAPI, profile: str | ApiRouteProfile = "development") -> ApiRouteProfile
```

## Core Settings

```python
class Settings(BaseModel):
    @classmethod
    def from_env(cls) -> "Settings"

def get_settings() -> Settings
```

## API Routes

```python
def health(request: Request) -> HealthResponse
```

## Core Models And Errors

```python
class HealthResponse(BaseModel)
class EurogasNexusError(Exception)
class ConfigurationError(EurogasNexusError)
```

