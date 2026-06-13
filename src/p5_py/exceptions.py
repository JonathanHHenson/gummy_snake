"""Package-specific exceptions."""


class P5PyError(Exception):
    """Base class for p5-py errors."""


class ContextError(P5PyError):
    """Raised when a p5-py API requires an active sketch context."""


class UnsupportedFeatureError(P5PyError):
    """Raised when an API is intentionally excluded or not supported by a backend."""


class BackendCapabilityError(UnsupportedFeatureError):
    """Raised when the active backend cannot perform a requested operation."""


class ArgumentValidationError(P5PyError, TypeError):
    """Raised when a p5-style overloaded API receives invalid arguments."""


class ShaderError(P5PyError):
    """Base class for shader loading, compilation, and binding errors."""


class ShaderCompilationError(ShaderError):
    """Raised when a shader fails to compile or link on the active backend."""


class ShaderUniformError(ShaderError):
    """Raised when a shader uniform cannot be applied."""
