"""
Campus Lost and Found NLP Engine
---------------------------------
Advanced Natural Language Processing system for semantic understanding,
synonym disambiguation, entity extraction, and intelligent matching of
campus lost and found items.
"""

import re
import math
from collections import Counter
from typing import Dict, List, Any, Tuple, Optional
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# ---------------------------------------------------------------------------
# Campus Domain Knowledge Base & Ontologies
# ---------------------------------------------------------------------------

# Expanded synonym clusters (concepts that refer to the same or highly related objects)
CAMPUS_SYNONYM_CLUSTERS = {
    "charger": [
        "charger", "charging adapter", "adapter", "power brick", "power adapter",
        "charging cable", "cable", "lightning cable", "type c cable", "usb c charger",
        "power cord", "wall adapter", "fast charger", "magsafe", "warp charger"
    ],
    "earphones": [
        "earphones", "earbuds", "airpods", "airpod", "headset", "headphones",
        "buds", "galaxy buds", "wireless earbuds", "ear piece", "ear pods",
        "bluetooth earphones", "noise cancelling headphones"
    ],
    "water_bottle": [
        "bottle", "water bottle", "flask", "hydro flask", "tumbler", "sipper",
        "thermos", "water flask", "metal bottle", "steel bottle", "shaker"
    ],
    "glasses": [
        "glasses", "spectacles", "specs", "reading glasses", "shades",
        "sunglasses", "sun glasses", "frames", "cooling glasses", "eyewear"
    ],
    "id_card": [
        "id card", "identity card", "college id", "student badge", "campus pass",
        "hall ticket", "id badge", "smart card", "library card", "rfid card",
        "student id", "access card"
    ],
    "laptop": [
        "laptop", "notebook", "macbook", "macbook air", "macbook pro", "thinkpad",
        "chromebook", "computer", "ultrabook", "dell inspiron", "hp laptop"
    ],
    "phone": [
        "phone", "mobile", "smartphone", "iphone", "cellphone", "android",
        "handset", "cell phone", "mobile phone", "telephone"
    ],
    "backpack": [
        "backpack", "bag", "college bag", "rucksack", "knapsack", "book bag",
        "school bag", "tote bag", "laptop bag", "duffel bag", "satchel"
    ],
    "wallet": [
        "wallet", "purse", "billfold", "money clip", "cardholder", "card holder",
        "pouch", "coin purse", "handbag", "clutch"
    ],
    "keys": [
        "keys", "keychain", "key", "bike key", "room key", "car key", "scooter key",
        "hostel key", "latchkey", "key ring", "bunch of keys"
    ],
    "umbrella": [
        "umbrella", "parasol", "rain umbrella", "foldable umbrella", "brolly", "rain shade"
    ],
    "calculator": [
        "calculator", "scientific calculator", "fx 991", "casio calculator", "calc",
        "scientific calc", "graphic calculator"
    ],
    "watch": [
        "watch", "smartwatch", "smart watch", "wrist watch", "apple watch",
        "fitness band", "galaxy watch", "timepiece", "analog watch", "digital watch"
    ],
    "notebook_doc": [
        "notebook", "register", "spiral notebook", "rough book", "record book",
        "lab record", "notes", "diary", "journal", "binder", "files", "folder"
    ],
    "jacket": [
        "jacket", "hoodie", "sweatshirt", "sweater", "cardigan", "blazer",
        "coat", "pullover", "windbreaker"
    ]
}

# Category taxonomies
CATEGORIES = {
    "Electronics": ["charger", "earphones", "laptop", "phone", "calculator", "watch", "power bank", "mouse", "pen drive", "usb", "ipad", "tablet"],
    "Personal Accessories": ["glasses", "watch", "wallet", "keys", "umbrella", "belt", "ring", "ring", "chain", "bracelet", "cap"],
    "Bags & Luggage": ["backpack", "laptop bag", "duffel bag", "handbag", "pouch", "tote bag"],
    "Campus IDs & Cards": ["id_card", "hall ticket", "atm card", "debit card", "license", "library card"],
    "Stationery & Books": ["notebook_doc", "calculator", "textbook", "pen", "pencil case", "binder", "files", "drawing board"],
    "Bottles & Containers": ["water_bottle", "lunch box", "tiffin", "thermos"],
    "Clothing & Apparel": ["jacket", "cap", "scarf", "gloves", "lab coat"]
}

# Colors dictionary for visual attribute matching
COLORS = [
    "black", "white", "silver", "grey", "gray", "blue", "navy", "dark blue", "light blue",
    "red", "maroon", "green", "olive", "yellow", "gold", "golden", "pink", "rose",
    "purple", "violet", "orange", "brown", "tan", "beige", "transparent", "metallic"
]

# Common Brands
BRANDS = [
    "apple", "samsung", "dell", "hp", "lenovo", "asus", "acer", "sony", "boat",
    "oneplus", "xiaomi", "redmi", "realme", "noise", "fireboltt", "casio", "fastrack",
    "titan", "wildcraft", "skybags", "american tourister", "nike", "adidas", "puma",
    "milton", "tupperware", "cello", "logitech", "anker", "sandisk", "parker"
]

# Campus locations & zones
CAMPUS_LOCATIONS = {
    "Library": ["library", "central library", "reading room", "reference section", "digital library", "study hall"],
    "Cafeteria": ["cafeteria", "canteen", "food court", "mess", "coffee shop", "snack bar", "nescafe"],
    "Academic Block": ["academic block", "lecture hall", "classroom", "seminar hall", "department", "cs block", "mech block", "ee block", "hall 1", "hall 2", "hall 3", "lh1", "lh2", "auditorium"],
    "Laboratories": ["lab", "computer lab", "physics lab", "chemistry lab", "robotics lab", "iot lab", "language lab", "science lab"],
    "Sports Complex": ["sports ground", "gym", "badminton court", "basketball court", "football field", "stadium", "cricket ground", "pavilion"],
    "Hostel Area": ["hostel", "hostel 1", "hostel 2", "hostel 3", "dorm", "boys hostel", "girls hostel", "warden office"],
    "Campus Grounds": ["parking", "bike stand", "bus stop", "main gate", "fountain", "garden", "amphitheater", "admin block", "reception"]
}

# Inverted mapping: token -> canonical cluster
WORD_TO_CLUSTER: Dict[str, str] = {}
for cluster_key, synonyms in CAMPUS_SYNONYM_CLUSTERS.items():
    for syn in synonyms:
        WORD_TO_CLUSTER[syn.lower()] = cluster_key


class CampusNLPEngine:
    """
    Core NLP Engine combining rule-based information extraction,
    semantic synonym resolution, and hybrid n-gram TF-IDF cosine matching.
    """

    def __init__(self):
        self.stop_words = set([
            "a", "an", "the", "in", "on", "at", "by", "for", "with", "about",
            "against", "between", "into", "through", "during", "before", "after",
            "above", "below", "to", "from", "up", "down", "is", "are", "was",
            "were", "be", "been", "being", "have", "has", "had", "do", "does",
            "did", "it", "its", "i", "my", "me", "we", "our", "you", "your",
            "he", "him", "his", "she", "her", "they", "them", "their", "this",
            "that", "these", "those", "lost", "missing", "found", "founding",
            "looking", "please", "help", "contact", "someone", "kindly", "today",
            "yesterday", "urgent", "reward"
        ])

        # Pre-seed vectorizer with domain vocabulary for consistent feature space
        domain_corpus = []
        for syn_list in CAMPUS_SYNONYM_CLUSTERS.values():
            domain_corpus.append(" ".join(syn_list))
        for loc_list in CAMPUS_LOCATIONS.values():
            domain_corpus.append(" ".join(loc_list))
        domain_corpus.append(" ".join(COLORS))
        domain_corpus.append(" ".join(BRANDS))

        self.vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),
            sublinear_tf=True,
            stop_words=list(self.stop_words)
        )
        self.vectorizer.fit(domain_corpus)

    def clean_text(self, text: str) -> str:
        """Lowercases, expands common campus contractions, removes extraneous punctuation."""
        if not text:
            return ""
        text = text.lower().strip()
        # Common expansions
        text = re.sub(r"\bcan\'t\b", "cannot", text)
        text = re.sub(r"\bwon\'t\b", "will not", text)
        text = re.sub(r"\bi\'m\b", "i am", text)
        text = re.sub(r"\bi\'ve\b", "i have", text)
        text = re.sub(r"[\.,;:!\?\"\'\(\)\[\]\{\}]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def tokenize(self, text: str) -> List[str]:
        """Simple whitespace/alphanumeric tokenization."""
        cleaned = self.clean_text(text)
        return [tok for tok in cleaned.split() if tok]

    def extract_entities(self, text: str) -> Dict[str, Any]:
        """
        Information extraction module:
        Extracts Category, Item Cluster, Brand, Color, Location, and Status from free text.
        """
        cleaned = self.clean_text(text)
        tokens = self.tokenize(text)

        # 1. Identify Status (Lost or Found)
        status = "Unknown"
        if re.search(r"\b(lost|missing|misplaced|forgot|dropped|left behind)\b", cleaned):
            status = "Lost"
        elif re.search(r"\b(found|discovered|picked up|kept with|submitted|turned in)\b", cleaned):
            status = "Found"

        # 2. Identify Colors
        detected_colors = []
        for color in COLORS:
            # Check whole word match
            if re.search(rf"\b{re.escape(color)}\b", cleaned):
                detected_colors.append(color)

        # 3. Identify Brands
        detected_brands = []
        for brand in BRANDS:
            if re.search(rf"\b{re.escape(brand)}\b", cleaned):
                detected_brands.append(brand.title())

        # 4. Identify Item Cluster & Category
        detected_cluster = None
        matched_cluster_phrase = None
        for syn, cluster_key in sorted(WORD_TO_CLUSTER.items(), key=lambda x: len(x[0]), reverse=True):
            pattern = rf"\b{re.escape(syn)}\b"
            if re.search(pattern, cleaned):
                detected_cluster = cluster_key
                matched_cluster_phrase = syn
                break

        # Fallback category determination
        detected_category = "General Item"
        if detected_cluster:
            for cat_name, members in CATEGORIES.items():
                if detected_cluster in members:
                    detected_category = cat_name
                    break
        else:
            # Check individual keywords for category hints
            for cat_name, members in CATEGORIES.items():
                for member in members:
                    if re.search(rf"\b{re.escape(member)}\b", cleaned):
                        detected_category = cat_name
                        break

        # 5. Identify Location / Campus Zone
        detected_location_zone = "Unknown Campus Zone"
        detected_location_specific = None
        for zone_name, aliases in CAMPUS_LOCATIONS.items():
            for alias in aliases:
                if re.search(rf"\b{re.escape(alias)}\b", cleaned):
                    detected_location_zone = zone_name
                    detected_location_specific = alias.title()
                    break
            if detected_location_specific:
                break

        # 6. Extract meaningful content keywords (stopword filtered)
        keywords = [tok for tok in tokens if tok not in self.stop_words and len(tok) > 2]

        return {
            "status": status,
            "category": detected_category,
            "item_cluster": detected_cluster,
            "canonical_item": detected_cluster.replace("_", " ").title() if detected_cluster else "Unspecified Item",
            "matched_phrase": matched_cluster_phrase,
            "colors": detected_colors,
            "brands": detected_brands,
            "location_zone": detected_location_zone,
            "location_detail": detected_location_specific,
            "keywords": keywords
        }

    def expand_with_synonyms(self, text: str) -> str:
        """
        Semantic query expansion:
        Replaces or appends canonical cluster identifiers so that
        'charger' and 'charging adapter' project into identical semantic dimensions.
        """
        cleaned = self.clean_text(text)
        expansions = [cleaned]

        for syn, cluster_key in sorted(WORD_TO_CLUSTER.items(), key=lambda x: len(x[0]), reverse=True):
            if re.search(rf"\b{re.escape(syn)}\b", cleaned):
                # Inject canonical cluster token and related high-value synonyms
                expansions.append(cluster_key)
                expansions.append(f"item_cluster_{cluster_key}")
                # Add top synonyms from the same cluster
                related = CAMPUS_SYNONYM_CLUSTERS.get(cluster_key, [])[:4]
                expansions.extend(related)

        return " ".join(expansions)

    def calculate_text_similarity(self, text1: str, text2: str) -> float:
        """
        Calculates cosine similarity over synonym-expanded TF-IDF n-gram representations.
        """
        exp1 = self.expand_with_synonyms(text1)
        exp2 = self.expand_with_synonyms(text2)

        try:
            # Fit and transform dynamically on pair + domain prior
            vecs = self.vectorizer.transform([exp1, exp2])
            sim = cosine_similarity(vecs[0:1], vecs[1:2])[0][0]
            return float(np.clip(sim, 0.0, 1.0))
        except Exception:
            # Jaccard fallback
            set1 = set(self.tokenize(exp1))
            set2 = set(self.tokenize(exp2))
            if not set1 or not set2:
                return 0.0
            return float(len(set1 & set2) / len(set1 | set2))

    def compute_match_score(
        self,
        item1: Dict[str, Any],
        item2: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Computes a multi-criteria weighted semantic match score between two items
        (typically one Lost item and one Found item).

        Criteria & Weights:
        - Semantic Description Similarity (45%)
        - Item Cluster / Category Alignment (25%)
        - Campus Location Proximity (15%)
        - Physical Attributes (Color, Brand) (15%)
        """
        desc1 = item1.get("description", "")
        desc2 = item2.get("description", "")

        # Extract entities if not already pre-computed
        ent1 = item1.get("nlp_entities") or self.extract_entities(desc1)
        ent2 = item2.get("nlp_entities") or self.extract_entities(desc2)

        # 1. Semantic Text Cosine Similarity
        text_sim = self.calculate_text_similarity(desc1, desc2)

        # 2. Item Cluster / Concept Alignment
        cluster_score = 0.0
        cluster_explanation = "Different item types"
        if ent1["item_cluster"] and ent2["item_cluster"]:
            if ent1["item_cluster"] == ent2["item_cluster"]:
                cluster_score = 1.0
                cluster_explanation = f"Exact semantic concept match: Both refer to '{ent1['canonical_item']}'"
            else:
                # Different cluster
                cluster_score = 0.05
                cluster_explanation = f"Mismatched concepts: '{ent1['canonical_item']}' vs '{ent2['canonical_item']}'"
        elif ent1["category"] == ent2["category"] and ent1["category"] != "General Item":
            cluster_score = 0.65
            cluster_explanation = f"Same category: '{ent1['category']}'"
        else:
            # Infer from keyword overlap
            shared_kw = set(ent1["keywords"]) & set(ent2["keywords"])
            if shared_kw:
                cluster_score = min(0.6, len(shared_kw) * 0.25)
                cluster_explanation = f"Shared keywords: {', '.join(list(shared_kw)[:3])}"

        # 3. Location Proximity Score
        loc1 = item1.get("location") or ent1.get("location_zone") or ""
        loc2 = item2.get("location") or ent2.get("location_zone") or ""
        loc_score = 0.0
        loc_explanation = "Different or unspecified campus locations"

        clean_loc1 = self.clean_text(str(loc1))
        clean_loc2 = self.clean_text(str(loc2))

        # Check zone match
        zone1 = ent1.get("location_zone")
        zone2 = ent2.get("location_zone")
        if zone1 and zone2 and zone1 != "Unknown Campus Zone" and zone1 == zone2:
            loc_score = 1.0
            loc_explanation = f"Both reported in '{zone1}'"
        elif clean_loc1 and clean_loc2 and (clean_loc1 in clean_loc2 or clean_loc2 in clean_loc1):
            loc_score = 0.9
            loc_explanation = f"Direct location string match: '{loc1}' & '{loc2}'"
        elif self.calculate_text_similarity(clean_loc1, clean_loc2) > 0.4:
            loc_score = 0.75
            loc_explanation = f"Semantically related locations: '{loc1}' & '{loc2}'"
        elif not clean_loc1 or not clean_loc2 or "unknown" in clean_loc1.lower() or "unknown" in clean_loc2.lower():
            loc_score = 0.4  # Neutral when location is ambiguous
            loc_explanation = "Location not explicitly constrained"

        # 4. Attribute Overlap (Color, Brand)
        attr_score = 0.0
        attr_explanations = []

        # Color comparison
        colors1 = set(ent1.get("colors", []))
        colors2 = set(ent2.get("colors", []))
        if colors1 and colors2:
            if colors1 & colors2:
                attr_score += 0.6
                attr_explanations.append(f"Matching color: {', '.join(colors1 & colors2)}")
            else:
                attr_score += 0.0
                attr_explanations.append(f"Color conflict: {', '.join(colors1)} vs {', '.join(colors2)}")
        else:
            attr_score += 0.3  # Neutral if one didn't specify color

        # Brand comparison
        brands1 = set(ent1.get("brands", []))
        brands2 = set(ent2.get("brands", []))
        if brands1 and brands2:
            if brands1 & brands2:
                attr_score += 0.4
                attr_explanations.append(f"Matching brand: {', '.join(brands1 & brands2)}")
            else:
                attr_score += 0.0
                attr_explanations.append(f"Brand difference: {', '.join(brands1)} vs {', '.join(brands2)}")
        else:
            attr_score += 0.2  # Neutral

        attr_score = min(1.0, attr_score)
        attr_detail = " | ".join(attr_explanations) if attr_explanations else "Standard attribute match"

        # Weighted Aggregate Calculation
        # Weights:
        # If both items have strongly identified clusters, give higher weight to cluster + text
        w_text = 0.40
        w_cluster = 0.35
        w_loc = 0.15
        w_attr = 0.10

        total_confidence = (
            (text_sim * w_text) +
            (cluster_score * w_cluster) +
            (loc_score * w_loc) +
            (attr_score * w_attr)
        )

        # Apply domain boosting / penalties
        # Strong booster: identical cluster (e.g., charger <-> charging adapter)
        if ent1["item_cluster"] and ent2["item_cluster"] and ent1["item_cluster"] == ent2["item_cluster"]:
            # Boost score so students who type 'charger' and 'charging adapter' get high confidence
            total_confidence = max(total_confidence, 0.70 + (text_sim * 0.25))

        # Severe penalty: completely different known clusters (e.g., umbrella vs charger)
        if (ent1["item_cluster"] and ent2["item_cluster"] and
            ent1["item_cluster"] != ent2["item_cluster"] and
            ent1["item_cluster"] not in ["General Item"] and ent2["item_cluster"] not in ["General Item"]):
            total_confidence *= 0.25

        total_percentage = round(float(np.clip(total_confidence * 100, 0, 100)), 1)

        # Categorize confidence level
        if total_percentage >= 75.0:
            verdict = "High Confidence Match"
            verdict_badge = "success"
        elif total_percentage >= 50.0:
            verdict = "Potential Match (Review Needed)"
            verdict_badge = "warning"
        else:
            verdict = "Low Likelihood Match"
            verdict_badge = "secondary"

        return {
            "total_score": total_percentage,
            "verdict": verdict,
            "verdict_badge": verdict_badge,
            "breakdown": {
                "text_similarity_score": round(text_sim * 100, 1),
                "cluster_score": round(cluster_score * 100, 1),
                "cluster_explanation": cluster_explanation,
                "location_score": round(loc_score * 100, 1),
                "location_explanation": loc_explanation,
                "attribute_score": round(attr_score * 100, 1),
                "attribute_explanation": attr_detail
            },
            "entities_1": ent1,
            "entities_2": ent2
        }

    def find_all_matches(
        self,
        target_item: Dict[str, Any],
        candidate_items: List[Dict[str, Any]],
        threshold: float = 40.0
    ) -> List[Dict[str, Any]]:
        """
        Scans a candidate pool of items and returns ranked matches
        exceeding the given threshold percentage.
        """
        matches = []
        for candidate in candidate_items:
            # Skip comparing the same item
            if candidate.get("id") == target_item.get("id"):
                continue

            # Don't match Lost with Lost or Found with Found
            t1_status = target_item.get("status", "").lower()
            t2_status = candidate.get("status", "").lower()
            if t1_status and t2_status and t1_status == t2_status:
                continue

            match_data = self.compute_match_score(target_item, candidate)
            if match_data["total_score"] >= threshold:
                matches.append({
                    "matched_item": candidate,
                    "target_item_id": target_item.get("id"),
                    "match_data": match_data
                })

        # Sort matches descending by total score
        matches.sort(key=lambda m: m["match_data"]["total_score"], reverse=True)
        return matches
