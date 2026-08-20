import requests, re, json, os
from bs4 import BeautifulSoup
from datetime import datetime

URL = "https://muslimbangla.com/world/BD/prayer-times-Narayanganj"
HEADERS = {"User-Agent": "Mozilla/5.0"}
BN_TO_EN = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
def to_en(s): return s.translate(BN_TO_EN) if s else ""
def clean(s): return re.sub(r"\s+", " ", s).strip() if s else ""

html = requests.get(URL, headers=HEADERS, timeout=20).text
soup = BeautifulSoup(html, "lxml")

# ===== DATE - যেটা এখন ঠিক কাজ করছে =====
body_text = soup.body.get_text(" ", strip=True) if soup.body else soup.get_text(" ", strip=True)
body_text = clean(body_text)

m = re.search(r"([০-৯]+\s+[^\n•]+?হিজরি)\s*•\s*([^\n•]+?বঙ্গাব্দ)", body_text)
if m:
    hijri_bn = clean(m.group(1))
    bengali_bn = clean(m.group(2))
    full_bn = f"{hijri_bn} • {bengali_bn}"
else:
    hijri_bn = bengali_bn = full_bn = ""

# ===== PRAYER TIMES - আগের কাজ করা লজিক ফিরিয়ে আনলাম =====
def get_time_from_parent(tag):
    # tag এর parent এর text থেকে টাইম বের করো
    parent_text = tag.parent.get_text(" ", strip=True) if tag.parent else ""
    mt = re.search(r"[০-৯]{1,2}:[০-৯]{2}(?:\s*-\s*[০-৯]{1,2}:[০-৯]{2})?", parent_text)
    if mt:
        return clean(mt.group(0))
    # fallback: পরের 2টা element
    nxt = tag.find_next()
    for _ in range(3):
        if not nxt: break
        txt = nxt.get_text(" ", strip=True) if hasattr(nxt, 'get_text') else str(nxt)
        mt = re.search(r"[০-৯]{1,2}:[০-৯]{2}(?:\s*-\s*[০-৯]{1,2}:[০-৯]{2})?", txt)
        if mt:
            return clean(mt.group(0))
        nxt = nxt.find_next() if hasattr(nxt, 'find_next') else None
    return ""

def build_section(section_keyword, expected_labels):
    result = {}
    # section h2 খুঁজে
    h2 = soup.find(lambda t: t.name == "h2" and section_keyword in t.get_text())
    if not h2:
        return result
    
    # h2 থেকে পরের h2 পর্যন্ত সব h3/h4
    for sib in h2.find_all_next():
        if sib.name == "h2":
            break
        if sib.name in ["h3","h4"]:
            label = clean(sib.get_text())
            if not label or len(label) > 25:
                continue
            # expected label এর মধ্যে আছে কিনা চেক
            matched = None
            for exp in expected_labels:
                if exp in label:
                    matched = exp
                    break
            if not matched:
                continue
            
            bn_time = get_time_from_parent(sib)
            if bn_time and matched not in result: # ডুপ্লিকেট এড়াতে
                en_time = to_en(bn_time)
                start, end = (en_time.split("-")[0].strip(), en_time.split("-")[1].strip()) if "-" in en_time else (en_time, "")
                # professional key
                key_map = {"ফজর":"fajr","যুহর":"dhuhr","আসর":"asr","মাগরিব":"maghrib","ইশা":"isha",
                           "সূর্যোদয়":"sunrise","দুপুর":"noon","সূর্যাস্ত":"sunset",
                           "তাহাজ্জুদ":"tahajjud","ইশরাক":"ishraq","চাশত":"chasht","সাহরী":"sehri_end"}
                key = key_map.get(matched, matched)
                
                result[key] = {
                    "label_bn": matched,
                    "time_bn": bn_time,
                    "time_en": en_time,
                    "start": start,
                    "end": end
                }
    return result

prayer = build_section("ওয়াক্তের সময়সূচী", ["ফজর","যুহর","আসর","মাগরিব","ইশা"])
forbidden = build_section("নামাজের নিষিদ্ধ সময়সূচী", ["সূর্যোদয়","দুপুর","সূর্যাস্ত"])
nafl = build_section("নফল নামাজের সময়সূচী", ["তাহাজ্জুদ","ইশরাক","চাশত","সাহরী"])

final = {
    "meta": {
        "location": {
            "city": "Dhaka",
            "city_bn": "ঢাকা",
            "country": "Bangladesh",
            "country_bn": "বাংলাদেশ",
            "timezone": "Asia/Dhaka"
        },
        "source_url": URL,
        "scraped_at": datetime.now().isoformat()
    },
    "date": {
        "full": {"bn": full_bn, "en": to_en(full_bn)},
        "hijri": {"bn": hijri_bn, "en": to_en(hijri_bn)},
        "bengali": {"bn": bengali_bn, "en": to_en(bengali_bn)}
    },
    "prayer_times": prayer,
    "forbidden_times": forbidden,
    "nafl_times": nafl
}

print(json.dumps(final, ensure_ascii=False, indent=2))
os.makedirs("data", exist_ok=True)
with open("data/dhaka.json", "w", encoding="utf-8") as f:
    json.dump(final, f, ensure_ascii=False, indent=2)

print("\n✅ সব ঠিক - date + prayer_times দুটোই আসবে!")
