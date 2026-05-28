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



## DB Foundations

```python
class DatabaseSettings(BaseModel)
def create_db_engine(settings: DatabaseSettings) -> Engine
def create_session_factory(engine: Engine) -> sessionmaker[Session]

@dataclass(frozen=True)
class IngestionRun

class IngestionRunRepository(Protocol):
    def get_by_id(self, run_id: str) -> IngestionRun | None
```


## SDK / CLI Shell

```python
def fetch_health(base_url: str, timeout_seconds: float = 5.0) -> HealthPayload
def run_health_check(base_url: str) -> str
```


## Application Workflow Shell

```python
def get_ingestion_run(repository: IngestionRunRepository, run_id: str) -> IngestionRunLookupResult
```


## Streaming Shell

```python
@dataclass(frozen=True)
class StreamingEnvelope
```


## Runtime Store + Data Quality Shell

```python
class RuntimeStore(Protocol):
    def get_heartbeat(self, service_name: str, instance_id: str) -> HeartbeatRecord | None

class QualityCheck(Protocol):
    def evaluate(self, dataset_id: str) -> QualityCheckResult
```


## Ingestion Shell

```python
@dataclass(frozen=True)
class IngestionPayload

@dataclass(frozen=True)
class NormalizedRecord
```
