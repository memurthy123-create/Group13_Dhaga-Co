"""Transparent deterministic demo; never presented as an AI model."""
import re
from .schemas import ReturnDecision, CatalogueDecision

def clean(value):
    return re.sub(r"\s+", " ", str(value).strip().lower())

def demo_return(text):
    t = clean(text)
    patterns = {
        "fit_too_small": ["tight", "too small", "chhota", "chota", "छोटा", "तंग"],
        "fit_too_large": ["too large", "loose", "bada", "बड़ा", "ढीला"],
        "fabric_quality": ["itch", "fabric rough", "kapda kharab", "कपड़ा खराब", "thin fabric"],
        "damaged": ["torn", "broken", "damaged", "phata", "फटा"],
        "wrong_item": ["wrong item", "wrong product", "galat item", "गलत सामान"],
        "colour_mismatch": ["wrong colour", "color different", "colour different", "rang alag", "रंग अलग"],
        "changed_mind": ["changed my mind", "pasand nahi", "पसंद नहीं"],
        "delivery_issue": ["late delivery", "bahut late", "देर से"],
    }
    hits = [reason for reason, phrases in patterns.items() if any(x in t for x in phrases)]
    negation = bool(re.search(r"\b(not|nahi|nahin|never)\b", t)) or "नहीं" in t
    if not t or len(t) < 5:
        reason, confidence, review = "insufficient_information", .1, True
    elif negation:
        reason, confidence, review = "insufficient_information", .3, True
    elif hits:
        reason, confidence, review = hits[0], .9, len(hits) > 1
    elif any(x in t for x in ["where is my order", "order status", "mera order kahan", "tracking"]):
        reason, confidence, review = "not_return", .9, False
    else:
        reason, confidence, review = "insufficient_information", .2, True
    return ReturnDecision(primary_reason=reason, secondary_reasons=hits[1:] if hits else [], evidence=text if hits else "", confidence=confidence, needs_review=review, explanation="Offline keyword demo: negations, mixed or unfamiliar language need human review. Not an AI quality measurement.")

COLOUR_MAP = {
    "blue": ("Blue", "Blue"), "blu": ("Blue", "Blue"), "blue colour": ("Blue", "Blue"),
    "navy": ("Blue", "Navy"), "navy blue": ("Blue", "Navy"), "indigo": ("Blue", "Indigo"),
    "neela": ("Blue", "Neela"), "नीला": ("Blue", "नीला"),
    "red": ("Red", "Red"), "lal": ("Red", "Lal"), "लाल": ("Red", "लाल"),
    "black": ("Black", "Black"), "blk": ("Black", "Black"), "kala": ("Black", "Kala"),
    "white": ("White", "White"), "green": ("Green", "Green"), "grey": ("Grey", "Grey"),
    "gray": ("Grey", "Grey"), "pink": ("Pink", "Pink"), "yellow": ("Yellow", "Yellow"),
}
FABRIC_MAP = {"cotton": "Cotton", "cottn": "Cotton", "100% cotton": "Cotton", "polyester": "Polyester", "poly": "Polyester", "linen": "Linen", "silk": "Silk", "denim": "Denim", "viscose": "Viscose", "rayon": "Viscose", "wool": "Wool"}
SIZE_MAP = {"xs": "XS", "s": "S", "small": "S", "m": "M", "medium": "M", "l": "L", "large": "L", "xl": "XL", "x-large": "XL", "xxl": "XXL", "2xl": "XXL", "xxxl": "XXXL", "3xl": "XXXL", "free size": "One Size", "one size": "One Size"}

def standardise_rules(row):
    colour, fabric, size = (clean(row[k]) for k in ["colour_raw", "fabric_raw", "size_raw"])
    family, shade = COLOUR_MAP.get(colour, ("Unknown", row["colour_raw"]))
    material = FABRIC_MAP.get(fabric, "Unknown")
    if any(x in fabric for x in ["blend", "%", "/", "+"]) and fabric not in FABRIC_MAP:
        material = "Blend" if any(x in fabric for x in ["cotton", "poly", "linen", "viscose", "wool", "silk"]) else "Unknown"
    size_label = SIZE_MAP.get(size, "Vendor Specific" if size else "Unknown")
    review = family == "Unknown" or material == "Unknown" or size_label in ["Vendor Specific", "Unknown"]
    # A letter label is standardised, not a cross-vendor fit equivalence.
    review = review or size_label == "One Size"
    return CatalogueDecision(colour_family=family, colour_shade=shade, fabric=material, fabric_detail=row["fabric_raw"], size_label=size_label, confidence=.5 if review else .95, needs_review=review, explanation="Exact alias/unit-free label mapping. Original values and vendor measurements retained; no fit equivalence inferred.")
