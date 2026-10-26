#!/usr/bin/env python3
"""TLS context construction shared by the Device Service and worker client."""

from __future__ import annotations

import ssl
from pathlib import Path


class TransportSecurityError(ValueError):
    """Raised when a TLS certificate or key configuration is invalid."""


def _existing_file(value: str | Path, label: str) -> Path:
    path = Path(value)
    if not path.is_file():
        raise TransportSecurityError(f"{label} does not exist: {path}")
    return path


def build_server_tls_context(
    cert_file: str | Path,
    key_file: str | Path,
    client_ca_file: str | Path | None = None,
    previous_client_ca_file: str | Path | None = None,
) -> ssl.SSLContext:
    """Build a TLS 1.2+ server context, optionally requiring client certs."""

    cert_path = _existing_file(cert_file, "TLS certificate")
    key_path = _existing_file(key_file, "TLS private key")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.options |= ssl.OP_NO_COMPRESSION
    try:
        context.load_cert_chain(str(cert_path), str(key_path))
    except (OSError, ssl.SSLError) as error:
        raise TransportSecurityError(
            f"unable to load TLS certificate/key: {error}"
        ) from error
    client_ca_files = [
        path
        for path in (client_ca_file, previous_client_ca_file)
        if path is not None
    ]
    if client_ca_files:
        for value in client_ca_files:
            client_ca_path = _existing_file(
                value,
                "TLS client CA certificate",
            )
            try:
                context.load_verify_locations(cafile=str(client_ca_path))
            except (OSError, ssl.SSLError) as error:
                raise TransportSecurityError(
                    f"unable to load TLS client CA: {error}"
                ) from error
        context.verify_mode = ssl.CERT_REQUIRED
    else:
        context.verify_mode = ssl.CERT_NONE
    return context


def build_client_tls_context(
    ca_file: str | Path | None = None,
    client_cert_file: str | Path | None = None,
    client_key_file: str | Path | None = None,
) -> ssl.SSLContext:
    """Build a verified client context with optional mutual-TLS credentials."""

    if (client_cert_file is None) != (client_key_file is None):
        raise TransportSecurityError(
            "TLS client certificate and key must be provided together"
        )
    ca_path = (
        _existing_file(ca_file, "TLS CA certificate")
        if ca_file is not None
        else None
    )
    context = (
        ssl.create_default_context(cafile=str(ca_path))
        if ca_path is not None
        else ssl.create_default_context()
    )
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.options |= ssl.OP_NO_COMPRESSION
    if client_cert_file is not None and client_key_file is not None:
        cert_path = _existing_file(
            client_cert_file,
            "TLS client certificate",
        )
        key_path = _existing_file(client_key_file, "TLS client private key")
        try:
            context.load_cert_chain(str(cert_path), str(key_path))
        except (OSError, ssl.SSLError) as error:
            raise TransportSecurityError(
                f"unable to load TLS client certificate/key: {error}"
            ) from error
    return context
