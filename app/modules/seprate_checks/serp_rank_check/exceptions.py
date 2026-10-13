"""Typed exceptions for the SERP rank check pipeline.

Retryable provider errors (``SerpProviderTimeout`` /
``SerpProvider5xx``) are retried by the Celery task; the rest fail
the job immediately without a retry.
"""


class SerpProviderTimeout(Exception):
    """Provider request timed out or the transport failed (retryable)."""


class SerpProvider4xx(Exception):
    """Provider rejected the request with a 4xx status (not retryable)."""


class SerpProvider5xx(Exception):
    """Provider failed with a 5xx status (retryable)."""


class SerpParseError(Exception):
    """Provider response could not be parsed (not retryable)."""
