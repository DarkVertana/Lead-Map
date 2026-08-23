#!/usr/bin/env python3
"""
The categories Google actually recognises, and a check for the ones you type.

Google Places (New) publishes two tables of place types. Table A holds the 478
types you may filter a search by (the `includedType` behind --type); Table B
holds 36 more that come back on a place but are rejected as a filter. Both are
below, copied from the documentation on 2026-08-23:

    https://developers.google.com/maps/documentation/places/web-service/place-types

A category you type is matched against Table A after some tidying: spacing and
punctuation are folded ("Coffee Shop" → coffee_shop), plurals are trimmed, and a
table of everyday and Indian-English names is applied ("chemist" → pharmacy,
"petrol pump" → gas_station, "beauty parlour" → beauty_salon). Longer phrases
are scanned for a type inside them, so "best artisan bakery" matches bakery.

The category still goes to Google as free text — this only catches typos before
the search runs, and always lets you insist.

    python -m leadmap.validate.place_types "coffee shop" "chemist" "dentst"
    python -m leadmap.validate.place_types --list "Health and Wellness"
    python -m leadmap.validate.place_types --stats
"""

from __future__ import annotations

import difflib
import re
import sys
from typing import Optional

from .gazetteer import Match, Verdict

MAX_WORDS = 5        # longest phrase we try to read a type out of

TABLE_A: dict[str, tuple[str, ...]] = {
    "Automotive": (
        "car_dealer", "car_rental", "car_repair", "car_wash",
        "ebike_charging_station", "electric_vehicle_charging_station",
        "gas_station", "parking", "parking_garage", "parking_lot", "rest_stop",
        "tire_shop", "truck_dealer"
    ),
    "Business": (
        "business_center", "corporate_office", "coworking_space", "farm",
        "manufacturer", "ranch", "supplier", "television_studio"
    ),
    "Culture": (
        "art_gallery", "art_museum", "art_studio", "auditorium", "castle",
        "cultural_landmark", "fountain", "historical_place", "history_museum",
        "monument", "museum", "performing_arts_theater", "sculpture"
    ),
    "Education": (
        "academic_department", "educational_institution", "library", "preschool",
        "primary_school", "research_institute", "school", "secondary_school",
        "university"
    ),
    "Entertainment and Recreation": (
        "adventure_sports_center", "amphitheatre", "amusement_center",
        "amusement_park", "aquarium", "banquet_hall", "barbecue_area",
        "botanical_garden", "bowling_alley", "casino", "childrens_camp",
        "city_park", "comedy_club", "community_center", "concert_hall",
        "convention_center", "cultural_center", "cycling_park", "dance_hall",
        "dog_park", "event_venue", "ferris_wheel", "garden", "go_karting_venue",
        "hiking_area", "historical_landmark", "indoor_playground", "internet_cafe",
        "karaoke", "live_music_venue", "marina", "miniature_golf_course",
        "movie_rental", "movie_theater", "national_park", "night_club",
        "observation_deck", "off_roading_area", "opera_house", "paintball_center",
        "park", "philharmonic_hall", "picnic_ground", "planetarium", "plaza",
        "roller_coaster", "skateboard_park", "state_park", "tourist_attraction",
        "video_arcade", "vineyard", "visitor_center", "water_park", "wedding_venue",
        "wildlife_park", "wildlife_refuge", "zoo"
    ),
    "Facilities": (
        "public_bath", "public_bathroom", "stable"
    ),
    "Finance": (
        "accounting", "atm", "bank"
    ),
    "Food and Drink": (
        "acai_shop", "afghani_restaurant", "african_restaurant",
        "american_restaurant", "argentinian_restaurant", "asian_fusion_restaurant",
        "asian_restaurant", "australian_restaurant", "austrian_restaurant",
        "bagel_shop", "bakery", "bangladeshi_restaurant", "bar", "bar_and_grill",
        "barbecue_restaurant", "basque_restaurant", "bavarian_restaurant",
        "beer_garden", "belgian_restaurant", "bistro", "brazilian_restaurant",
        "breakfast_restaurant", "brewery", "brewpub", "british_restaurant",
        "brunch_restaurant", "buffet_restaurant", "burmese_restaurant",
        "burrito_restaurant", "cafe", "cafeteria", "cajun_restaurant", "cake_shop",
        "californian_restaurant", "cambodian_restaurant", "candy_store",
        "cantonese_restaurant", "caribbean_restaurant", "cat_cafe",
        "chicken_restaurant", "chicken_wings_restaurant", "chilean_restaurant",
        "chinese_noodle_restaurant", "chinese_restaurant", "chocolate_factory",
        "chocolate_shop", "cocktail_bar", "coffee_roastery", "coffee_shop",
        "coffee_stand", "colombian_restaurant", "confectionery",
        "croatian_restaurant", "cuban_restaurant", "czech_restaurant",
        "danish_restaurant", "deli", "dessert_restaurant", "dessert_shop",
        "dim_sum_restaurant", "diner", "dog_cafe", "donut_shop",
        "dumpling_restaurant", "dutch_restaurant", "eastern_european_restaurant",
        "ethiopian_restaurant", "european_restaurant", "falafel_restaurant",
        "family_restaurant", "fast_food_restaurant", "filipino_restaurant",
        "fine_dining_restaurant", "fish_and_chips_restaurant", "fondue_restaurant",
        "food_court", "french_restaurant", "fusion_restaurant", "gastropub",
        "german_restaurant", "greek_restaurant", "gyro_restaurant",
        "halal_restaurant", "hamburger_restaurant", "hawaiian_restaurant",
        "hookah_bar", "hot_dog_restaurant", "hot_dog_stand", "hot_pot_restaurant",
        "hungarian_restaurant", "ice_cream_shop", "indian_restaurant",
        "indonesian_restaurant", "irish_pub", "irish_restaurant",
        "israeli_restaurant", "italian_restaurant", "japanese_curry_restaurant",
        "japanese_izakaya_restaurant", "japanese_restaurant", "juice_shop",
        "kebab_shop", "korean_barbecue_restaurant", "korean_restaurant",
        "latin_american_restaurant", "lebanese_restaurant", "lounge_bar",
        "malaysian_restaurant", "meal_delivery", "meal_takeaway",
        "mediterranean_restaurant", "mexican_restaurant",
        "middle_eastern_restaurant", "mongolian_barbecue_restaurant",
        "moroccan_restaurant", "noodle_shop", "north_indian_restaurant",
        "oyster_bar_restaurant", "pakistani_restaurant", "pastry_shop",
        "persian_restaurant", "peruvian_restaurant", "pizza_delivery",
        "pizza_restaurant", "polish_restaurant", "portuguese_restaurant", "pub",
        "ramen_restaurant", "restaurant", "romanian_restaurant",
        "russian_restaurant", "salad_shop", "sandwich_shop",
        "scandinavian_restaurant", "seafood_restaurant", "shawarma_restaurant",
        "snack_bar", "soul_food_restaurant", "soup_restaurant",
        "south_american_restaurant", "south_indian_restaurant",
        "southwestern_us_restaurant", "spanish_restaurant", "sports_bar",
        "sri_lankan_restaurant", "steak_house", "sushi_restaurant",
        "swiss_restaurant", "taco_restaurant", "taiwanese_restaurant",
        "tapas_restaurant", "tea_house", "tex_mex_restaurant", "thai_restaurant",
        "tibetan_restaurant", "tonkatsu_restaurant", "turkish_restaurant",
        "ukrainian_restaurant", "vegan_restaurant", "vegetarian_restaurant",
        "vietnamese_restaurant", "western_restaurant", "wine_bar", "winery",
        "yakiniku_restaurant", "yakitori_restaurant"
    ),
    "Geographical Areas": (
        "administrative_area_level_1", "administrative_area_level_2", "country",
        "locality", "postal_code", "school_district"
    ),
    "Government": (
        "city_hall", "courthouse", "embassy", "fire_station", "government_office",
        "local_government_office", "neighborhood_police_station", "police",
        "post_office"
    ),
    "Health and Wellness": (
        "chiropractor", "dental_clinic", "dentist", "doctor", "drugstore",
        "general_hospital", "hospital", "massage", "massage_spa", "medical_center",
        "medical_clinic", "medical_lab", "pharmacy", "physiotherapist", "sauna",
        "skin_care_clinic", "spa", "tanning_studio", "wellness_center",
        "yoga_studio"
    ),
    "Housing": (
        "apartment_building", "apartment_complex", "condominium_complex",
        "housing_complex"
    ),
    "Lodging": (
        "bed_and_breakfast", "budget_japanese_inn", "campground", "camping_cabin",
        "cottage", "extended_stay_hotel", "farmstay", "guest_house", "hostel",
        "hotel", "inn", "japanese_inn", "lodging", "mobile_home_park", "motel",
        "private_guest_room", "resort_hotel", "rv_park"
    ),
    "Natural Features": (
        "beach", "island", "lake", "mountain_peak", "nature_preserve", "river",
        "scenic_spot", "woods"
    ),
    "Places of Worship": (
        "buddhist_temple", "church", "hindu_temple", "mosque", "shinto_shrine",
        "synagogue"
    ),
    "Services": (
        "aircraft_rental_service", "association_or_organization", "astrologer",
        "barber_shop", "beautician", "beauty_salon", "body_art_service",
        "catering_service", "cemetery", "chauffeur_service", "child_care_agency",
        "consultant", "courier_service", "electrician", "employment_agency",
        "florist", "food_delivery", "foot_care", "funeral_home", "hair_care",
        "hair_salon", "insurance_agency", "laundry", "lawyer", "locksmith",
        "makeup_artist", "marketing_consultant", "moving_company", "nail_salon",
        "non_profit_organization", "painter", "pet_boarding_service", "pet_care",
        "plumber", "psychic", "real_estate_agency", "roofing_contractor", "service",
        "shipping_service", "storage", "summer_camp_organizer", "tailor",
        "telecommunications_service_provider", "tour_agency",
        "tourist_information_center", "travel_agency", "veterinary_care"
    ),
    "Shopping": (
        "asian_grocery_store", "auto_parts_store", "bicycle_store", "book_store",
        "building_materials_store", "butcher_shop", "cell_phone_store",
        "clothing_store", "convenience_store", "cosmetics_store",
        "department_store", "discount_store", "discount_supermarket",
        "electronics_store", "farmers_market", "flea_market", "food_store",
        "furniture_store", "garden_center", "general_store", "gift_shop",
        "grocery_store", "hardware_store", "health_food_store", "home_goods_store",
        "home_improvement_store", "hypermarket", "jewelry_store", "liquor_store",
        "market", "pet_store", "shoe_store", "shopping_mall",
        "sporting_goods_store", "sportswear_store", "store", "supermarket",
        "tea_store", "thrift_store", "toy_store", "warehouse_store", "wholesaler",
        "womens_clothing_store"
    ),
    "Sports": (
        "arena", "athletic_field", "fishing_charter", "fishing_pier",
        "fishing_pond", "fitness_center", "golf_course", "gym", "ice_skating_rink",
        "indoor_golf_course", "playground", "race_course", "ski_resort",
        "sports_activity_location", "sports_club", "sports_coaching",
        "sports_complex", "sports_school", "stadium", "swimming_pool",
        "tennis_court"
    ),
    "Transportation": (
        "airport", "airstrip", "bike_sharing_station", "bridge", "bus_station",
        "bus_stop", "ferry_service", "ferry_terminal", "heliport",
        "international_airport", "light_rail_station", "park_and_ride",
        "subway_station", "taxi_service", "taxi_stand", "toll_station",
        "train_station", "train_ticket_office", "tram_stop", "transit_depot",
        "transit_station", "transit_stop", "transportation_service", "truck_stop"
    ),
}

# Table B: returned on a place, but rejected as an includedType filter.
TABLE_B: tuple[str, ...] = (
    "administrative_area_level_3", "administrative_area_level_4",
    "administrative_area_level_5", "administrative_area_level_6",
    "administrative_area_level_7", "archipelago", "colloquial_area", "continent",
    "establishment", "finance", "food", "general_contractor", "geocode", "health",
    "intersection", "landmark", "natural_feature", "neighborhood",
    "place_of_worship", "plus_code", "point_of_interest", "political",
    "postal_code_prefix", "postal_code_suffix", "postal_town", "premise", "route",
    "street_address", "sublocality", "sublocality_level_1", "sublocality_level_2",
    "sublocality_level_3", "sublocality_level_4", "sublocality_level_5",
    "subpremise", "town_square"
)

ALL: frozenset[str] = frozenset(t for types in TABLE_A.values() for t in types)
CATEGORY_OF: dict[str, str] = {t: heading for heading, types in TABLE_A.items()
                               for t in types}

# British and Indian spellings folded to the ones Google uses.
SPELLINGS = {
    "centre": "center", "theatre": "theater", "jewellery": "jewelry",
    "jeweller": "jeweler", "parlour": "parlor", "tyre": "tire",
    "colour": "color", "programme": "program", "licence": "license",
    "aluminium": "aluminum", "practise": "practice",
}

# What people actually type → the type Google means by it.
ALIASES = {
    # food and drink
    "tea_stall": "tea_house", "chai_shop": "tea_house", "tea_shop": "tea_house",
    "dhaba": "restaurant", "mess": "restaurant", "eatery": "restaurant",
    "food_joint": "restaurant", "hotel_restaurant": "restaurant",
    "fast_food": "fast_food_restaurant", "pizza": "pizza_restaurant",
    "burger": "hamburger_restaurant", "burger_joint": "hamburger_restaurant",
    "ice_cream": "ice_cream_shop", "ice_cream_parlor": "ice_cream_shop",
    "sweet_shop": "confectionery", "mithai_shop": "confectionery",
    "sweets": "confectionery", "juice_center": "juice_shop",
    "juice_bar": "juice_shop", "coffee": "coffee_shop", "coffee_house": "coffee_shop",
    "tiffin": "meal_takeaway", "takeaway": "meal_takeaway",
    "food_delivery_service": "food_delivery", "canteen": "cafeteria",
    "pure_veg_restaurant": "vegetarian_restaurant", "veg_restaurant": "vegetarian_restaurant",
    "non_veg_restaurant": "restaurant", "wine_shop": "liquor_store",
    "beer_shop": "liquor_store", "bar_and_restaurant": "bar",
    # health
    "chemist": "pharmacy", "chemist_shop": "pharmacy", "medical_store": "pharmacy",
    "medical_shop": "pharmacy", "medicals": "pharmacy", "druggist": "pharmacy",
    "clinic": "medical_clinic", "nursing_home": "general_hospital",
    "pathology_lab": "medical_lab", "diagnostic_center": "medical_lab",
    "path_lab": "medical_lab", "physiotherapy": "physiotherapist",
    "yoga": "yoga_studio", "yoga_center": "yoga_studio", "dental": "dental_clinic",
    "eye_clinic": "medical_clinic", "child_specialist": "doctor",
    "vet": "veterinary_care", "veterinary": "veterinary_care",
    "veterinary_clinic": "veterinary_care", "pet_clinic": "veterinary_care",
    # services and trades
    "salon": "beauty_salon", "saloon": "barber_shop", "beauty_parlor": "beauty_salon",
    "parlor": "beauty_salon", "barber": "barber_shop", "hair_cutting": "barber_shop",
    "hairdresser": "hair_salon", "spa_center": "spa", "massage_center": "massage_spa",
    "garage": "car_repair", "mechanic": "car_repair", "car_mechanic": "car_repair",
    "auto_repair": "car_repair", "service_center": "car_repair",
    "car_showroom": "car_dealer", "advocate": "lawyer", "attorney": "lawyer",
    "law_firm": "lawyer", "accountant": "accounting",
    "chartered_accountant": "accounting", "ca": "accounting",
    "insurance": "insurance_agency", "courier": "courier_service",
    "dry_cleaner": "laundry", "dry_cleaning": "laundry", "dhobi": "laundry",
    "property_dealer": "real_estate_agency", "real_estate": "real_estate_agency",
    "broker": "real_estate_agency", "estate_agent": "real_estate_agency",
    "travel_agent": "travel_agency", "tour_operator": "tour_agency",
    "packers_and_movers": "moving_company", "movers": "moving_company",
    "carpenter": "general_store", "interior_designer": "consultant",
    # shopping
    "kirana": "grocery_store", "kirana_store": "grocery_store",
    "provision_store": "grocery_store", "grocery": "grocery_store",
    "super_market": "supermarket", "departmental_store": "department_store",
    "mall": "shopping_mall", "book_shop": "book_store", "shoe_shop": "shoe_store",
    "cloth_shop": "clothing_store", "clothes": "clothing_store",
    "garment_shop": "clothing_store", "boutique": "clothing_store",
    "readymade_garments": "clothing_store", "mobile_shop": "cell_phone_store",
    "mobile_store": "cell_phone_store", "electronics_shop": "electronics_store",
    "jewellers": "jewelry_store", "jewelry_shop": "jewelry_store",
    "furniture_shop": "furniture_store", "hardware_shop": "hardware_store",
    "sports_shop": "sporting_goods_store", "toy_shop": "toy_store",
    "gift_store": "gift_shop", "flower_shop": "florist", "nursery": "garden_center",
    # places and transport
    "cinema": "movie_theater", "movie_hall": "movie_theater",
    "theatre_hall": "performing_arts_theater", "temple": "hindu_temple",
    "masjid": "mosque", "railway_station": "train_station",
    "bus_stand": "bus_station", "petrol_pump": "gas_station",
    "petrol_bunk": "gas_station", "petrol_station": "gas_station",
    "fuel_station": "gas_station", "filling_station": "gas_station",
    "ev_charging": "electric_vehicle_charging_station",
    "charging_station": "electric_vehicle_charging_station",
    "police_station": "police", "resort": "resort_hotel", "lodge": "lodging",
    "pg": "guest_house", "paying_guest": "guest_house",
    "banquet": "banquet_hall", "marriage_hall": "wedding_venue",
    "function_hall": "event_venue", "playground_area": "playground",
    # education and work
    "coaching_class": "school", "coaching_center": "school", "tuition": "school",
    "college": "university", "institute": "educational_institution",
    "play_school": "preschool", "day_care": "child_care_agency",
    "office": "corporate_office", "startup": "corporate_office",
    "cyber_cafe": "internet_cafe", "internet_center": "internet_cafe",
    "fitness": "fitness_center", "fitness_studio": "fitness_center",
}

_WORDS = re.compile(r"[^a-z0-9]+")


def normalise(text: str) -> str:
    """'Beauty Parlour!' → 'beauty_parlor' — Google's shape and spelling."""
    tokens = [t for t in _WORDS.split(text.strip().lower()) if t]
    return "_".join(SPELLINGS.get(token, token) for token in tokens)


def _depluralise(name: str) -> str:
    """Only the last word: 'coffee_shops' → 'coffee_shop', 'bakeries' → 'bakery'."""
    head, _, last = name.rpartition("_")
    if last.endswith("ies") and len(last) > 4:
        last = last[:-3] + "y"
    elif last.endswith(("ses", "shes", "ches", "xes")):
        last = last[:-2]
    elif last.endswith("s") and not last.endswith("ss"):
        last = last[:-1]
    return f"{head}_{last}" if head else last


def resolve(text: str) -> Optional[str]:
    """The Table A type this phrase means, if any."""
    name = normalise(text)
    if not name:
        return None
    for candidate in (name, ALIASES.get(name), _depluralise(name),
                      ALIASES.get(_depluralise(name))):
        if candidate and candidate in ALL:
            return candidate
    # "chinese" → chinese_restaurant, "shoe" → shoe_store
    for suffix in ("_restaurant", "_store", "_shop", "_service"):
        for stem in (name, _depluralise(name)):
            if stem + suffix in ALL:
                return stem + suffix
    return None


def scan(text: str) -> Optional[tuple[str, str]]:
    """Find a type inside a longer phrase: 'best artisan bakery' → bakery."""
    words = [w for w in _WORDS.split(text.strip().lower()) if w]
    for size in range(min(MAX_WORDS, len(words)), 0, -1):
        for start in range(len(words) - size + 1):
            phrase = " ".join(words[start:start + size])
            found = resolve(phrase)
            if found:
                return phrase, found
    return None


def suggest(text: str, limit: int = 3) -> list[str]:
    name = normalise(text)
    pool = list(ALL) + list(ALIASES)
    close = difflib.get_close_matches(name, pool, n=limit * 2, cutoff=0.75)
    out: list[str] = []
    for candidate in close:
        resolved = ALIASES.get(candidate, candidate)
        if resolved not in out:
            out.append(resolved)
    return out[:limit]


def verify(category: str) -> Verdict:
    """Check a typed category against Table A. Empty is fine — it's optional."""
    verdict = Verdict(location=category)
    if not category.strip():
        verdict.matches.append(Match("category", ""))
        return verdict

    found = scan(category)
    if found:
        phrase, place_type = found
        verdict.matches.append(Match("type", place_type, CATEGORY_OF[place_type]))
        if normalise(phrase) != place_type:
            verdict.notes.append(f"“{category.strip()}” → Google's {place_type}")
        return verdict

    name = normalise(category)
    if name in TABLE_B:
        verdict.problems.append(
            f"“{name}” is a Table B type — Google returns it on a place "
            "but won't filter a search by it")
    else:
        verdict.problems.append(
            f"“{category.strip()}” is not one of Google's {len(ALL)} place categories")
    verdict.suggestions = suggest(category)
    return verdict


def check_type_id(type_id: str) -> Optional[str]:
    """Validate a raw --type value. Returns a complaint, or None if it's fine."""
    name = normalise(type_id)
    if name in ALL:
        return None
    if name in TABLE_B:
        return (f"--type {type_id} is a Table B type: Google returns it on a place "
                "but rejects it as a search filter")
    close = suggest(type_id)
    hint = f" Did you mean {', '.join(close)}?" if close else ""
    return f"--type {type_id} is not a Google place type.{hint}"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0
    if argv[0] == "--stats":
        for heading, types in TABLE_A.items():
            print(f"  {heading:30} {len(types):>4}")
        print(f"  {'Table A total':30} {len(ALL):>4}")
        print(f"  {'Table B (not filterable)':30} {len(TABLE_B):>4}")
        print(f"  {'everyday aliases':30} {len(ALIASES):>4}")
        return 0
    if argv[0] == "--list":
        wanted = " ".join(argv[1:]).lower()
        for heading, types in TABLE_A.items():
            if wanted and wanted not in heading.lower():
                continue
            print(f"\n{heading}")
            for name in types:
                print(f"  {name}")
        return 0

    worst = 0
    for category in argv:
        verdict = verify(category)
        if verdict.ok:
            match = verdict.matches[0]
            print(f"✓ {category}  →  {match.text}  ({match.detail})")
            for note in verdict.notes:
                print(f"  · {note}")
        else:
            worst = 1
            print(f"✗ {category}  →  {verdict.reason()}"
                  + (f"   did you mean: {', '.join(verdict.suggestions)}?"
                     if verdict.suggestions else ""))
    return worst


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
