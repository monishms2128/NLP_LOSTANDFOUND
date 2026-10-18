"""
Campus Lost and Found NLP Challenge - Academic Evaluation & Benchmark Suite
----------------------------------------------------------------------------
Evaluates semantic similarity, synonym resolution, and classification metrics
across challenging campus lost & found pairs (synonyms, paraphrases, and negative distractors).
"""

import time
import numpy as np
from nlp_engine import CampusNLPEngine

def run_evaluation():
    engine = CampusNLPEngine()

    test_cases = [
        # --- POSITIVE PAIRS (Should Match: High Semantic Similarity) ---
        {
            "id": "POS-01",
            "type": "positive",
            "category": "Electronics",
            "lost": {"description": "Charger is missing, black color 65W with USB-C", "location": "Library"},
            "found": {"description": "Charging adapter has been found in library reading hall near table 4", "location": "Library"},
            "description": "User Example: Charger vs Charging Adapter"
        },
        {
            "id": "POS-02",
            "type": "positive",
            "category": "Accessories",
            "lost": {"description": "Lost my reading specs with brown frame during math class", "location": "Academic Block"},
            "found": {"description": "Found spectacles with brown fiber frame in LH2", "location": "Academic Block"},
            "description": "Synonym: Specs vs Spectacles"
        },
        {
            "id": "POS-03",
            "type": "positive",
            "category": "Audio",
            "lost": {"description": "Misplaced white AirPods Pro case near cafeteria", "location": "Cafeteria"},
            "found": {"description": "Discovered wireless earbuds white charging case at food court table", "location": "Cafeteria"},
            "description": "Synonym: AirPods vs Wireless Earbuds"
        },
        {
            "id": "POS-04",
            "type": "positive",
            "category": "Containers",
            "lost": {"description": "Left my blue hydro flask in the sports gym locker area", "location": "Sports Complex"},
            "found": {"description": "Found navy blue water bottle near basketball court", "location": "Sports Complex"},
            "description": "Synonym: Hydro Flask vs Water Bottle"
        },
        {
            "id": "POS-05",
            "type": "positive",
            "category": "IDs",
            "lost": {"description": "Lost my college ID card and student pass near main gate", "location": "Campus Grounds"},
            "found": {"description": "Picked up identity card / campus badge near bus stop entrance", "location": "Campus Grounds"},
            "description": "Synonym: ID Card vs Identity Card / Campus Badge"
        },
        {
            "id": "POS-06",
            "type": "positive",
            "category": "Bags",
            "lost": {"description": "Black Wildcraft backpack containing notebooks forgotten in physics lab", "location": "Laboratories"},
            "found": {"description": "Black college bag wildcraft brand found in science lab 2", "location": "Laboratories"},
            "description": "Synonym: Backpack vs College Bag"
        },
        {
            "id": "POS-07",
            "type": "positive",
            "category": "Calculators",
            "lost": {"description": "Casio scientific calculator fx-991 lost before exam in hall 3", "location": "Academic Block"},
            "found": {"description": "Found casio calc on seat 42 in examination hall", "location": "Academic Block"},
            "description": "Synonym: Calculator vs Calc"
        },
        {
            "id": "POS-08",
            "type": "positive",
            "category": "Keys",
            "lost": {"description": "Lost bunch of keys with a red superhero keychain near hostel 2", "location": "Hostel Area"},
            "found": {"description": "Room key ring with red keychain spotted outside boys hostel", "location": "Hostel Area"},
            "description": "Synonym: Bunch of keys vs Key ring"
        },

        # --- NEGATIVE PAIRS (Should NOT Match: Distractors & False Friends) ---
        {
            "id": "NEG-01",
            "type": "negative",
            "category": "Cross-Category",
            "lost": {"description": "Lost my blue water bottle near library", "location": "Library"},
            "found": {"description": "Found charging adapter in library near reference section", "location": "Library"},
            "description": "Distractor: Water bottle vs Charging adapter (same location, different item)"
        },
        {
            "id": "NEG-02",
            "type": "negative",
            "category": "Cross-Category",
            "lost": {"description": "Lost room keys on keychain at cafeteria", "location": "Cafeteria"},
            "found": {"description": "Found scientific calculator in canteen", "location": "Cafeteria"},
            "description": "Distractor: Keys vs Calculator (same location, different item)"
        },
        {
            "id": "NEG-03",
            "type": "negative",
            "category": "Electronics-Distractor",
            "lost": {"description": "Lost silver HP laptop in computer lab", "location": "Laboratories"},
            "found": {"description": "Found wireless earbuds in computer lab", "location": "Laboratories"},
            "description": "Distractor: Laptop vs Earbuds (both electronics, different items)"
        },
        {
            "id": "NEG-04",
            "type": "negative",
            "category": "Accessories-Distractor",
            "lost": {"description": "Black leather wallet missing with cash and license", "location": "Sports Complex"},
            "found": {"description": "Found black sunglasses near badminton court", "location": "Sports Complex"},
            "description": "Distractor: Wallet vs Sunglasses (same color & location, different item)"
        },
        {
            "id": "NEG-05",
            "type": "negative",
            "category": "Attribute-Conflict",
            "lost": {"description": "Lost red umbrella with wooden handle", "location": "Academic Block"},
            "found": {"description": "Found bright yellow raincoat in seminar hall", "location": "Academic Block"},
            "description": "Distractor: Red umbrella vs Yellow raincoat"
        },
        {
            "id": "NEG-06",
            "type": "negative",
            "category": "Location-Mismatch",
            "lost": {"description": "Lost identity card at bus stop", "location": "Campus Grounds"},
            "found": {"description": "Found college bag at hostel 3 mess", "location": "Hostel Area"},
            "description": "Distractor: ID card vs College bag with different location"
        }
    ]

    print("=" * 80)
    print(" CAMPUS LOST & FOUND NLP CHALLENGE - SEMANTIC BENCHMARK EVALUATION")
    print("=" * 80)
    print(f"{'ID':<7} | {'Type':<8} | {'Score':<6} | {'Verdict':<28} | {'Result':<6} | {'Scenario'}")
    print("-" * 80)

    threshold = 55.0  # Decision threshold for match classification
    tp = 0
    fp = 0
    tn = 0
    fn = 0
    positive_scores = []
    negative_scores = []

    start_time = time.time()

    for tc in test_cases:
        res = engine.compute_match_score(tc["lost"], tc["found"])
        score = res["total_score"]
        predicted_match = score >= threshold
        is_positive = tc["type"] == "positive"

        if is_positive:
            positive_scores.append(score)
            if predicted_match:
                tp += 1
                outcome = "PASS"
            else:
                fn += 1
                outcome = "FAIL"
        else:
            negative_scores.append(score)
            if not predicted_match:
                tn += 1
                outcome = "PASS"
            else:
                fp += 1
                outcome = "FAIL"

        print(f"{tc['id']:<7} | {tc['type']:<8} | {score:>5.1f}% | {res['verdict']:<28} | {outcome:<6} | {tc['description']}")

    elapsed = time.time() - start_time
    total = len(test_cases)
    accuracy = (tp + tn) / total
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    print("=" * 80)
    print(" EVALUATION METRICS SUMMARY")
    print("=" * 80)
    print(f"Total Test Cases:       {total}")
    print(f"Confusion Matrix:       TP: {tp} | FP: {fp} | TN: {tn} | FN: {fn}")
    print(f"Accuracy:               {accuracy * 100:.2f}%")
    print(f"Precision:              {precision * 100:.2f}%")
    print(f"Recall:                 {recall * 100:.2f}%")
    print(f"F1-Score:               {f1 * 100:.2f}%")
    print(f"Avg Positive Score:     {np.mean(positive_scores):.2f}%")
    print(f"Avg Negative Score:     {np.mean(negative_scores):.2f}%")
    print(f"Separation Margin:      {np.mean(positive_scores) - np.mean(negative_scores):.2f}%")
    print(f"Total Benchmark Time:   {elapsed * 1000:.1f} ms ({elapsed/total*1000:.1f} ms/query)")
    print("=" * 80)

if __name__ == "__main__":
    run_evaluation()
