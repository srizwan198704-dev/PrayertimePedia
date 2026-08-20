import requests
from bs4 import BeautifulSoup
import json
import re
import os
from datetime import datetime

URL = "https://muslimbangla.com/world/BD/prayer-times-Dhaka"
HEADERS = {"User-Agent": "Mozilla/5.0"}
BN_TO_EN = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
def to_en(s): return s.translate(BN_TO_EN) if s else ""

def clean_text(s):
    # \n,  extra space সব clean করে এক লাইনে আনবে
    if not s: return ""
    s = re.sub(r"\s+", " ", s) # সব whitespace -> single space
    return s.strip()

def scrape():
    html = requests.get(URL, headers=HEADERS, timeout=20).text
    soup = BeautifulSoup(html, "lxml")
    
    # পুরো পেজের text কে clean এক লাইনে
    raw_text = soup.get_text(" ", strip=True)
    clean = clean_text(raw_text)

    # ===== ১. তারিখ - ULTRA ROBUST =====
    # এখন clean text থেকে খুঁজবো, তাই \n এর ঝামেলা নেই
    # Pattern: "৬ রবিউল আউয়াল, ১৪৪৮ হিজরি • বৃহস্পতিবার, ৫ ভাদ্র, ১৪৩৩ বঙ্গাব্দ"
    date_regex = r"([০-৯]{1,2}\s+[^•]*?হিজরি)\s*•\s*([^•]*?বঙ্গাব্দ)"
    m = re.search(date_regex, clean)
    
    full_bn = ""
    hijri_bn = ""
    bengali_bn = ""
    if m:
        hijri_bn = clean_text(m.group(1))
        bengali_bn = clean_text(m.group(2))
        full_bn = f"{hijri_bn} • {bengali_bn}"
    else:
        # fallback 2 - html থেকে
        # soup এর মধ্যে যে element এ হিজরি ও বঙ্গাব্দ দুটোই আছে
        for tag in soup.find_all(string=re.compile("হিজরি")):
            parent_text = clean_text(tag.parent.get_text(" ", strip=True) if hasattr(tag.parent, 'get_text') else str(tag))
            if "বঙ্গাব্দ" in parent_text and len(parent_text) < 200:
                full_bn = parent_text
                if "•" in full_bn:
                    hijri_bn = clean_text(full_bn.split("•")[0])
                    bengali_bn = clean_text(full_bn.split("•")[1])
                break

    # যুহর কেন মিস হচ্ছিল? - কারণ "যুহর" এর h3 তে অনেক সময় "জুমা" ও থাকে, তাই exact match
    def find_time_by_label(label):
        # সব h3/h4 লুপ
        for h in soup.find_all(['h3','h4']):
            if label == h.get_text(strip=True): # exact match
                # h এর parent বা পরের text
                block = h.parent.get_text(" ", strip=True) if h.parent else ""
                # block থেকে টাইম
                tm = re.search(r"[০-৯]{1,2}:[০-৯]{2}(?:\s*-\s*[০-৯]{1,2}:[০-৯]{2})?", block)
                if tm:
                    return clean_text(tm.group(0))
        # contains match fallback
        for h in soup.find_all(['h3','h4']):
            if label in h.get_text(strip=True):
                block = h.parent.get_text(" ", strip=True) if h.parent else ""
                tm = re.search(r"[০-৯]{1,2}:[০-৯]{2}(?:\s*-\s*[০-৯]{1,2}:[০-৯]{2})?", block)
                if tm:
                    return clean_text(tm.group(0))
        return ""

    # সব লেবেল একসাথে
    labels = {
        "waqt": ["ফজর", "যুহর", "আসর", "মাগরিব", "ইশা"],
        "forbidden": ["সূর্যোদয়", "দুপুর", "সূর্যাস্ত"],
        "nafl": ["তাহাজ্জুদ", "ইশরাক", "চাশত", "সাহরী"]
    }

    def build_section(names):
        res = {}
        for name in names:
            bn_time = find_time_by_label(name)
            if bn_time:
                en_time = to_en(bn_time)
                start, end = (en_time.split("-")[0].strip(), en_time.split("-")[1].strip()) if "-" in en_time else (en_time, "")
                key = {"ফজর":"fajr","যুহর":"dhuhr","আসর":"asr","মাগরিব":"maghrib","ইশা":"isha",
                       "সূর্যোদয়":"sunrise","দুপুর":"noon","সূর্যাস্ত":"sunset",
                       "তাহাজ্জুদ":"tahajjud","ইশরাক":"ishraq","চাশত":"chasht","সাহরী":"sehri"}[name]
                res[key] = {
                    "label_bn": name,
                    "time_bn": bn_time,
                    "time_en": en_time,
                    "start": start,
                    "end": end
                }
        return res

    final = {
        "meta": {
            "location": "Dhaka, Bangladesh",
            "url": URL,
            "scraped_at": datetime.now().isoformat()
        },
        "date": {
            "full": {
                "bn": full_bn,
                "en": to_en(full_bn)
            },
            "hijri": {
                "bn": hijri_bn,
                "en": to_en(hijri_bn)
            },
            "bengali": {
                "bn": bengali_bn,
                "en": to_en(bengali_bn)
            }
        },
        "prayer_times": build_section(labels["waqt"]),
        "forbidden_times": build_section(labels["forbidden"]),
        "nafl_times": build_section(labels["nafl"])
    }
    return final

if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    data = scrape()
    print(json.dumps(data, ensure_ascii=False, indent=2))
    with open("data/dhaka.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
