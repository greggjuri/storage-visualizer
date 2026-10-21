_UNITS = "KMGTPE"


def df_size(n: int) -> str:
    """Format bytes like `df -h` (coreutils human_ceiling, base 1024)."""
    if n < 1024:
        return str(n)
    k = 1
    while k < len(_UNITS) and n >= 1024 ** (k + 1):
        k += 1
    base = 1024**k
    unit = _UNITS[k - 1]
    if n < 10 * base:
        tenths = -(-10 * n // base)
        if tenths < 100:
            return f"{tenths // 10}.{tenths % 10}{unit}"
        return f"10{unit}"
    whole = -(-n // base)
    if whole == 1024 and k < len(_UNITS):
        return f"1.0{_UNITS[k]}"
    return f"{whole}{unit}"
