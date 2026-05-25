import re


def generate_unit_prefix(property_name: str) -> str:
    words = property_name.strip().split()
    if len(words) >= 2:
        prefix = ''.join(w[0] for w in words[:3]).upper()
    elif len(words) == 1 and words[0]:
        prefix = words[0][:3].upper()
    else:
        prefix = 'PR'
    if len(prefix) < 2:
        prefix = prefix.ljust(2, 'P')
    return prefix
