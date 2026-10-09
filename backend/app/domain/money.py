from decimal import ROUND_HALF_UP, Decimal


def D(value: int | str | Decimal) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def round_half_up(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def scaled(base: int, change_pct: int) -> Decimal:
    """Линейная индексация без двоичной дроби: base × (100 + pct) / 100."""
    return D(base) * D(100 + change_pct) / D(100)


def scaled_kopecks(base: int, change_pct: int) -> int:
    return round_half_up(scaled(base, change_pct))
