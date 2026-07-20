import os
import json
import random
import uuid
import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import datetime, timedelta

# Constants
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

os.makedirs(DATA_DIR, exist_ok=True)

# Realistic clinical dictionaries to simulate Synthea
NAMES = [
    ("James", "Wilson"), ("Sarah", "Chen"), ("Carlos", "Joshi"), ("Elena", "Rostova"),
    ("Marcus", "Aurelius"), ("Sophia", "Martinez"), ("Wei", "Wang"), ("Emily", "Clark"),
    ("David", "Kim"), ("Aisha", "Patel"), ("John", "Doe"), ("Jane", "Smith")
]

CONDITIONS = [
    "Essential hypertension", "Type 2 diabetes mellitus", "Major depressive disorder",
    "Asthma", "Osteoarthritis", "Chronic kidney disease", "Hyperlipidemia",
    "Coronary heart disease", "Gastroesophageal reflux disease", "Hypothyroidism"
]

MEDICATIONS = [
    "Lisinopril 10mg", "Lisinopril 20mg", "Metformin 500mg", "Metformin 1000mg",
    "Amlodipine 5mg", "Atorvastatin 20mg", "Atorvastatin 40mg", "Albuterol inhaler",
    "Omeprazole 20mg", "Sertraline 50mg", "Levothyroxine 50mcg", "Ibuprofen 400mg",
    "Aspirin 81mg"
]

ALLERGIES = [
    "Penicillin", "Sulfa drugs", "Peanuts", "Latex", "Aspirin", "Iodine"
]

BLOOD_TYPES = ["O+", "O-", "A+", "A-", "B+", "B-", "AB+", "AB-"]

def generate_base_profiles(count=20):
    profiles = []
    for _ in range(count):
        first, last = random.choice(NAMES)
        pid = str(uuid.uuid4())
        
        profiles.append({
            "id": pid,
            "first": first,
            "last": last,
            "age": random.randint(20, 85),
            "gender": random.choice(["Male", "Female"]),
            "blood_group": random.choice(BLOOD_TYPES),
            "diagnoses": random.sample(CONDITIONS, random.randint(1, 4)),
            "medications": random.sample(MEDICATIONS, random.randint(1, 4)),
            "allergies": random.sample(ALLERGIES, random.randint(0, 2))
        })
    return profiles

def generate_conflicting_profiles(base_profiles):
    hA, hB, hC = [], [], []
    
    for base in base_profiles:
        # Hospital A: Mostly correct, but misses some allergies
        prof_a = dict(base)
        prof_a["name"] = f"{base['first']} {base['last']}"
        prof_a["allergies"] = [] if random.random() < 0.5 else list(base["allergies"])
        
        # Hospital B: Name typos, medication dosage conflicts, older blood type errors
        prof_b = dict(base)
        prof_b["name"] = f"{base['first']} {base['last'][0]}." if random.random() < 0.3 else f"{base['first']} {base['last']}"
        prof_b["blood_group"] = random.choice([b for b in BLOOD_TYPES if b != base["blood_group"]]) if random.random() < 0.2 else base["blood_group"]
        
        altered_meds = []
        for m in base["medications"]:
            if "mg" in m and random.random() < 0.5:
                altered_meds.append(m.replace("mg", "0mg")) # e.g. 10mg -> 100mg
            else:
                altered_meds.append(m)
        prof_b["medications"] = altered_meds
        
        # Hospital C: Extra allergies (e.g. Aspirin), missing data
        prof_c = dict(base)
        prof_c["name"] = f"{base['first']} {base['last']}"
        prof_c["blood_group"] = "Unknown" if random.random() < 0.3 else base["blood_group"]
        prof_c["allergies"] = list(set(base["allergies"] + (["Aspirin"] if random.random() < 0.3 else [])))
        
        hA.append(prof_a)
        hB.append(prof_b)
        hC.append(prof_c)
        
    return hA, hB, hC

def write_hospital_A_json(patients):
    filepath = os.path.join(DATA_DIR, "hospital_A.json")
    out_data = {"patients": []}
    for p in patients:
        out_data["patients"].append({
            "patientId": p["id"][:8],
            "fullName": p["name"],
            "ageYears": p["age"],
            "sex": p["gender"],
            "bloodType": p["blood_group"],
            "knownAllergies": p["allergies"],
            "currentMedications": p["medications"],
            "diagnosedConditions": p["diagnoses"],
            "labResults": {
                "fastingBloodGlucose_mgdL": round(random.uniform(70, 120), 1),
                "bloodPressure": f"{random.randint(110, 140)}/{random.randint(70, 90)}",
                "hemoglobin_gdL": round(random.uniform(12, 16), 1)
            },
            "sourceHospital": "Hospital_A",
            "recordCreated": datetime.now().isoformat()
        })
    with open(filepath, 'w') as f:
        json.dump(out_data, f, indent=2)

def write_hospital_B_xml(patients):
    filepath = os.path.join(DATA_DIR, "hospital_B.xml")
    root = ET.Element("HospitalB_EHR")
    for p in patients:
        record = ET.SubElement(root, "PatientRecord", id=p["id"][:8])
        demographics = ET.SubElement(record, "Demographics")
        ET.SubElement(demographics, "FullName").text = p["name"]
        ET.SubElement(demographics, "Gender").text = p["gender"]
        ET.SubElement(demographics, "Age").text = str(p["age"])
        ET.SubElement(demographics, "BloodGroup").text = p["blood_group"]
        
        clinical = ET.SubElement(record, "ClinicalData")
        conds = ET.SubElement(clinical, "Conditions")
        for c in p["diagnoses"]: ET.SubElement(conds, "Condition").text = c
            
        meds = ET.SubElement(clinical, "Prescriptions")
        for m in p["medications"]: ET.SubElement(meds, "Drug").text = m
            
        alls = ET.SubElement(clinical, "Allergies")
        for a in p["allergies"]: ET.SubElement(alls, "Allergy").text = a
            
    xmlstr = minidom.parseString(ET.tostring(root)).toprettyxml(indent="  ")
    with open(filepath, "w") as f:
        f.write(xmlstr)

def write_hospital_C_csv(patients):
    filepath = os.path.join(DATA_DIR, "hospital_C.csv")
    headers = [
        "Patient_ID", "Patient_Name", "Age", "Gender", "Blood_Type", 
        "Active_Conditions", "Current_Medications", "Reported_Allergies", "Last_Visit"
    ]
    import csv
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for p in patients:
            writer.writerow([
                p["id"][:8], p["name"], p["age"], p["gender"], p["blood_group"],
                "; ".join(p["diagnoses"]), "; ".join(p["medications"]), "; ".join(p["allergies"]),
                (datetime.now() - timedelta(days=random.randint(1, 365))).strftime("%Y-%m-%d")
            ])

if __name__ == "__main__":
    print("=== Realistic Mock Data Generator (Synthea Simulation) ===")
    base = generate_base_profiles(30)
    hA, hB, hC = generate_conflicting_profiles(base)
    
    write_hospital_A_json(hA)
    write_hospital_B_xml(hB)
    write_hospital_C_csv(hC)
    
    print("Successfully generated realistic, conflicting clinical datasets!")
