"""Package-specific exceptions."""


class GummySnakeError(Exception):
    """Base class for Gummy Snake errors."""


class ContextError(GummySnakeError):
    """Raised when a Gummy Snake API requires an active sketch context."""


class UnsupportedFeatureError(GummySnakeError):
    """Raised when an API is intentionally excluded or not supported by a backend."""


class BackendCapabilityError(UnsupportedFeatureError):
    """Raised when the active backend cannot perform a requested operation."""


class ArgumentValidationError(GummySnakeError, TypeError):
    """Raised when a Gummy Snake-style overloaded API receives invalid arguments."""


class ShaderError(GummySnakeError):
    """Base class for shader loading, compilation, and binding errors."""


class ShaderCompilationError(ShaderError):
    """Raised when a shader fails to compile or link on the active backend."""


class ShaderUniformError(ShaderError):
    """Raised when a shader uniform cannot be applied."""
