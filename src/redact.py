import re


REDACTED = "[REDACTED]"

# Whole-value credentials: the match itself is the secret.
_SECRET_PATTERNS = (
    # GitHub tokens: ghp_ (personal), ghs_ (server), gho_/ghu_ (OAuth), ghr_ (refresh).
    re.compile(r"\b(?:ghp|ghs|gho|ghu|ghr)_[A-Za-z0-9]{20,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    # AWS access key IDs: AKIA (long-lived), ASIA (temporary).
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    # Slack bot/app/user/refresh tokens.
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    # PEM private key blocks, header through footer.
    re.compile(
        r"-----BEGIN[^-]*PRIVATE KEY-----.*?-----END[^-]*PRIVATE KEY-----",
        re.DOTALL,
    ),
)

# Credentials with a prefix worth keeping: the prefix identifies what leaked,
# which stays useful to the model, so only the value is replaced.
_PREFIXED_PATTERNS = (
    # Authorization: Bearer <token>
    (
        re.compile(
            r"(?i)((?:proxy-)?authorization\s*:\s*(?:bearer|basic|token|digest)\s+)[^\s\"']+"
        ),
        rf"\g<1>{REDACTED}",
    ),
    # scheme://user:password@host
    (
        re.compile(r"(?i)([a-z][a-z0-9+.\-]*://[^\s/:@]+:)[^\s/@]+(@)"),
        rf"\g<1>{REDACTED}\g<2>",
    ),
)

# Long opaque runs catch keys the named patterns miss (AWS secret keys,
# base64 blobs). _is_credential_like() filters out the look-alikes.
_LONG_RUN = re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}")
_HEX_OR_DIGITS = re.compile(r"[0-9a-f]+|[0-9A-F]+|[0-9]+")

# A deep path ("a/b/c/d/e/f") is long and opaque but is not a secret.
# Real base64 keys carry a slash or two at most.
_MAX_SLASHES = 3


def _is_credential_like(value: str) -> bool:
    """Decide whether a long run looks like a key rather than log noise.

    Keeps the values that are long for innocent reasons - commit SHAs,
    checksums, numeric IDs and deep file paths - all of which carry real
    diagnostic value in a CI log.

    Args:
        value: A run of characters matched by _LONG_RUN.

    Returns:
        True when the run has the character mix of a random credential.
    """
    if _HEX_OR_DIGITS.fullmatch(value):
        return False
    if value.count("/") > _MAX_SLASHES:
        return False
    if "+" in value or "=" in value:
        # base64 padding and plus signs are rare outside encoded data.
        return True
    return (
        any(c.isupper() for c in value)
        and any(c.islower() for c in value)
        and any(c.isdigit() for c in value)
    )


def _redact_long_runs(text: str) -> tuple[str, int]:
    """Redact long opaque strings that look like credentials.

    Args:
        text: Log text to scan.

    Returns:
        Tuple of (redacted text, number of replacements).
    """
    hits = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal hits
        value = match.group(0)
        if not _is_credential_like(value):
            return value
        hits += 1
        return REDACTED

    return _LONG_RUN.sub(replace, text), hits


def redact_secrets(text: str) -> tuple[str, int]:
    """Replace credential-looking values in log text with a placeholder.

    Runs before any log content is sent to the LLM provider. GitHub masks
    its own registered secrets, but tokens minted or echoed during a job
    reach the log unmasked.

    Args:
        text: Log text that may contain credentials.

    Returns:
        Tuple of (redacted text, number of replacements).
    """
    total = 0
    for pattern in _SECRET_PATTERNS:
        text, count = pattern.subn(REDACTED, text)
        total += count
    for pattern, replacement in _PREFIXED_PATTERNS:
        text, count = pattern.subn(replacement, text)
        total += count
    text, count = _redact_long_runs(text)
    return text, total + count


def redact_sections(sections: dict[str, str]) -> tuple[dict[str, str], int]:
    """Redact every parsed log section.

    Args:
        sections: Parsed sections from parse_log_sections().

    Returns:
        Tuple of (redacted sections, total number of replacements).
    """
    redacted: dict[str, str] = {}
    total = 0
    for key, value in sections.items():
        redacted[key], count = redact_secrets(value)
        total += count
    return redacted, total
