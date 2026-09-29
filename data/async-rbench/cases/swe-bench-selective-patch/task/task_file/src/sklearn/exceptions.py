"""Minimal exception classes needed by the trimmed sklearn package."""


class NotFittedError(ValueError, AttributeError):
    """Exception class to raise if estimator is used before fitting."""


class DataConversionWarning(UserWarning):
    """Warning used to notify implicit data conversions happening in the code."""


class PositiveSpectrumWarning(UserWarning):
    """Warning raised when the eigenvalues of a PSD matrix have a positive
    real part, and therefore we cannot guarantee convergence."""


class ConvergenceWarning(UserWarning):
    """Custom warning to capture convergence problems."""
