"""Helpers for masking operational data before public exposure."""


def coarse_coord(value):
    """Reduce coordinate precision to ~1.1km (barangay-level), never exact."""
    if value is None:
        return None
    return round(float(value), 2)


def mask_name(name):
    """'Juan Dela Cruz' -> 'J. D.'."""
    if not name:
        return 'Anonymous'
    parts = [p for p in name.strip().split() if p]
    if not parts:
        return 'Anonymous'
    return ' '.join(f'{p[0].upper()}.' for p in parts)


def mask_phone(phone):
    if not phone:
        return None
    digits = ''.join(c for c in phone if c.isdigit())
    if len(digits) < 4:
        return '••••'
    return '•' * 6 + digits[-2:]
