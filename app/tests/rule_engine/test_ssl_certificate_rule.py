import asyncio

from app.modules.rule_engine.category_rules.security import SSLCertificateRule
from app.modules.rule_engine.models.rule_result import Severity


def _evaluate(data):
    return asyncio.run(SSLCertificateRule().evaluate(data))[0]


def test_ssl_certificate_rule_passes_after_verified_tls_handshake():
    result = _evaluate({
        "site_security": {
            "tls": {
                "certificate_valid": True,
                "chain_trusted": True,
                "certificate_issuer": "Example CA",
            },
        },
    })

    assert result.passed is True
    assert result.severity == Severity.PASSED
    assert result.data["certificate_status"] == "valid"


def test_ssl_certificate_rule_fails_for_certificate_verification_error():
    result = _evaluate({
        "site_security": {
            "tls": {
                "certificate_valid": False,
                "chain_trusted": False,
                "error": "Certificate verification failed: certificate has expired",
            },
        },
    })

    assert result.passed is False
    assert result.severity == Severity.CRITICAL
    assert "certificate has expired" in result.message
    assert result.data["certificate_status"] == "invalid"


def test_ssl_certificate_rule_does_not_call_connection_error_invalid_certificate():
    result = _evaluate({
        "site_security": {
            "tls": {
                "certificate_valid": False,
                "chain_trusted": False,
                "error": "Connection error: timed out",
            },
        },
    })

    assert result.passed is False
    assert result.severity == Severity.WARNING
    assert result.score_impact == 0
    assert result.data["certificate_status"] == "unverified"


def test_ssl_certificate_rule_does_not_treat_https_flag_as_certificate_failure():
    result = _evaluate({
        "url": {"https": True},
        "ssl": {"is_https": True},
    })

    assert result.passed is False
    assert result.severity == Severity.WARNING
    assert result.score_impact == 0
    assert result.data["certificate_status"] == "unverified"


def test_ssl_certificate_rule_skips_check_for_http_when_probe_is_unavailable():
    result = _evaluate({
        "url": {"https": False},
    })

    assert result.passed is True
    assert result.severity == Severity.INFO
    assert result.data["certificate_status"] == "not_applicable"
