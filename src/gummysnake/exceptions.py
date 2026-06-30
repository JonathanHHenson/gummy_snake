"""Package-specific exceptions."""


class GummySnakeError(Exception):
    """Base class for Gummy Snake errors."""


class ContextError(GummySnakeError):
    """Raised when a Gummy Snake API requires an active sketch context."""


class UnsupportedFeatureError(GummySnakeError):
    """Raised when an API is intentionally excluded or not supported by a backend."""


class BackendCapabilityError(UnsupportedFeatureError):
    """Raised when the active backend cannot perform a requested operation."""


class CanvasClosedError(GummySnakeError):
    """Internal signal raised when the native canvas is closed mid-frame."""


class ArgumentValidationError(GummySnakeError, TypeError):
    """Raised when a Gummy Snake-style overloaded API receives invalid arguments."""


class EcsError(GummySnakeError):
    """Base class for ECS errors."""


class ComponentSchemaError(EcsError, TypeError):
    """Raised when an ECS component or resource schema is invalid."""


class EntityNotFoundError(EcsError):
    """Raised when an ECS entity lookup fails."""


class StaleEntityError(EntityNotFoundError):
    """Raised when an ECS entity handle refers to a despawned/reused slot."""


class MissingComponentError(EcsError, KeyError):
    """Raised when an entity does not have a requested component."""


class MissingResourceError(EcsError, KeyError):
    """Raised when an ECS resource is not present in the active world."""


class SystemPlanError(EcsError):
    """Raised when an ECS system action plan is invalid."""


class SystemExecutionError(EcsError):
    """Raised when an ECS system fails during execution."""


class ShaderError(GummySnakeError):
    """Base class for shader loading, compilation, and binding errors."""


class ShaderCompilationError(ShaderError):
    """Raised when a shader fails to compile or link on the active backend."""


class ShaderUniformError(ShaderError):
    """Raised when a shader uniform cannot be applied."""
