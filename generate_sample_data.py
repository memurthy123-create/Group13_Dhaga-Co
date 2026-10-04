"""Generates sample_data.sql with 5000 invented orders. Run: python generate_sample_data.py"""
import random

random.seed(42)          # same output every run
N = 5000
BAD_ADDRESS_SHARE = 0.05
COD_SHARE = 0.60

FIRST = ["Aarav", "Vivaan", "Aditya", "Arjun", "Rohan", "Karthik", "Rahul", "Vikram", "Suresh", "Manoj",
         "Imran", "Farhan", "Joseph", "Harpreet", "Nikhil", "Sandeep", "Ajay", "Deepak", "Naveen", "Pranav",
         "Ananya", "Diya", "Priya", "Sneha", "Kavya", "Meera", "Pooja", "Neha", "Lakshmi", "Divya",
         "Ayesha", "Fatima", "Mary", "Simran", "Shruti", "Swati", "Anjali", "Rekha", "Nandini", "Isha"]
LAST = ["Sharma", "Verma", "Gupta", "Reddy", "Nair", "Iyer", "Patel", "Shah", "Singh", "Kaur",
        "Das", "Banerjee", "Mukherjee", "Rao", "Shetty", "Gowda", "Menon", "Pillai", "Khan", "Sheikh",
        "Fernandes", "Joshi", "Kulkarni", "Deshmukh", "Mehta", "Agarwal", "Yadav", "Mishra", "Chopra", "Naidu"]
# city -> (areas with a pincode each)
CITIES = {
    "Bengaluru": [("Indiranagar", "560038"), ("Koramangala", "560034"), ("Jayanagar", "560041"), ("Whitefield", "560066")],
    "Mumbai":    [("Andheri West", "400053"), ("Bandra West", "400050"), ("Powai", "400076"), ("Dadar", "400014")],
    "Delhi":     [("Karol Bagh", "110005"), ("Lajpat Nagar", "110024"), ("Dwarka", "110075"), ("Rohini", "110085")],
    "Chennai":   [("T Nagar", "600017"), ("Adyar", "600020"), ("Anna Nagar", "600040"), ("Velachery", "600042")],
    "Hyderabad": [("Banjara Hills", "500034"), ("Madhapur", "500081"), ("Kukatpally", "500072"), ("Secunderabad", "500003")],
    "Pune":      [("Kothrud", "411038"), ("Baner", "411045"), ("Viman Nagar", "411014"), ("Hadapsar", "411028")],
    "Kolkata":   [("Park Street", "700016"), ("Salt Lake", "700091"), ("Ballygunge", "700019"), ("Behala", "700034")],
    "Ahmedabad": [("Navrangpura", "380009"), ("Satellite", "380015"), ("Maninagar", "380008"), ("Bopal", "380058")],
    "Jaipur":    [("Malviya Nagar", "302017"), ("Vaishali Nagar", "302021"), ("C Scheme", "302001"), ("Mansarovar", "302020")],
    "Noida":     [("Sector 15", "201301"), ("Sector 62", "201309"), ("Sector 18", "201301"), ("Sector 137", "201305")],
}
STREETS = ["Main Road", "1st Cross", "2nd Main", "Temple Street", "Station Road", "Market Road",
           "Lake Road", "Park Avenue", "Gandhi Road", "Church Street"]
BUILDINGS = ["", "", "Flat 2A, Green Residency, ", "Flat 4B, Lake View Apts, ", "Flat 301, Sai Towers, ",
             "B-12, Shanti Enclave, ", "Plot 7, "]
VAGUE = ["Near temple", "Opp bus stand", "Behind school", "Main road", "Near water tank",
         "House no 5", "Next to petrol pump", "Market area"]

# realistic mix; ON_HOLD and CANCEL_REQUESTED are left for the app to produce
STATUSES = ["READY_TO_SHIP"] * 45 + ["PLACED"] * 25 + ["SHIPPED"] * 30


def make_row(i):
    name = f"{random.choice(FIRST)} {random.choice(LAST)}"
    city = random.choice(list(CITIES))
    area, pin = random.choice(CITIES[city])
    if random.random() < BAD_ADDRESS_SHARE:
        kind = random.choice(["vague", "short_pin", "both"])
        address = random.choice(VAGUE) if kind != "short_pin" else \
            f"{random.randint(1, 250)}, {random.choice(STREETS)}, {area}, {city}"
        pincode = pin[:4] if kind != "vague" else pin
    else:
        address = f"{random.choice(BUILDINGS)}{random.randint(1, 250)}, {random.choice(STREETS)}, {area}, {city}"
        pincode = pin
    mode = "COD" if random.random() < COD_SHARE else "PREPAID"
    status = random.choice(STATUSES)
    days = random.randint(0, 3) if status != "SHIPPED" else random.randint(2, 6)
    created = "now()" if days == 0 else f"now() - interval '{days} days'"
    return f"('ORD-{10000 + i}', '{name}', '{mode}', '{address}', '{pincode}', '{status}', {created})"


rows = [make_row(i) for i in range(1, N + 1)]
with open("sample_data.sql", "w", encoding="utf-8") as f:
    f.write("-- Sample data: 5000 invented orders. Re-run any time to reset the demo.\n")
    f.write("truncate table support_tickets, cod_confirmation restart identity;\n")
    f.write("truncate table failure_log restart identity;\n")
    f.write("delete from orders;\n")
    for start in range(0, N, 1000):   # 1000 rows per insert statement
        f.write("\ninsert into orders (order_id, customer_name, payment_mode, address_text, "
                "pincode, order_status, created_at) values\n")
        f.write(",\n".join(rows[start:start + 1000]) + ";\n")
print("wrote", len(rows), "rows")
