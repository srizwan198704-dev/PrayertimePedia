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

def extract_section(soup, section_title_keyword):
    result = {}
    h2 = soup.find(lambda tag: tag.name == "h2" and section_title_keyword in tag.get_text())
    if not h2:
        return result
    for sibling in h2.find_all_next():
        if sibling.name == "h2":
            break
        if sibling.name in ["h3", "h4"]:
            name_bn = sibling.get_text(strip=True)
            if not name_bn or len(name_bn) > 30:
                continue
            time_bn = ""
            parent_text = sibling.parent.get_text(" ", strip=True) if sibling.parent else ""
            m = re.search(r"[০-৯]{1,2}:[০-৯]{2}(?:\s*-\s*[০-৯]{1,2}:[০-৯]{2})?", parent_text)
            if m:
                time_bn = m.group(0)
            if time_bn and name_bn not in result:
                # start/end আলাদা করা
                en_time = to_en(time_bn)
                start, end = "", ""
                if "-" in en_time:
                    parts = en_time.split("-")
                    start = parts[0].strip()
                    end = parts[1].strip()
                else:
                    start = en_time.strip()
                
                result[name_bn] = {
                    "label_bn": name_bn,
                    "time_bn": time_bn,
                    "time_en": en_time,
                    "start": start,
                    "end": end
                }
    return result

def scrape():
    res = requests.get(URL, headers=HEADERS, timeout=20)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "lxml")
    
    # --- ১. তারিখ - Professional Parsing ---
    date_full_bn = ""
    h2_date = soup.find(lambda tag: tag.name == "h2" and "নামাজের সময়সূচী" in tag.get_text())
    if h2_date:
        for elem in h2_date.next_elements:
            if elem.name == "h2":
                break
            txt = elem.strip() if isinstance(elem, str) else ""
            if not txt and hasattr(elem, 'get_text'):
                if elem.name in ['div', 'p', 'span']:
                    t = elem.get_text(strip=True)
                    if "হিজরি" in t and len(t) < 200:
                        txt = t
            if "হিজরি" in txt and "বঙ্গাব্দ" in txt:
                date_full_bn = txt
                break
        if not date_full_bn:
            for line in soup.get_text("\n").split("\n"):
                if "হিজরি" in line and "বঙ্গাব্দ" in line:
                    date_full_bn = line.strip()
                    break

    hijri_bn = ""
    bengali_bn = ""
    weekday_bn = ""
    if "•" in date_full_bn:
        parts = [p.strip() for p in date_full_bn.split("•")]
        hijri_bn = parts[0] if len(parts) > 0 else ""
        rest = parts[1] if len(parts) > 1 else ""
        # rest = "বৃহস্পতিবার, ৫ ভাদ্র, ১৪৩৩ বঙ্গাব্দ"
        if "," in rest:
            weekday_bn = rest.split(",")[0].strip()
            bengali_bn = rest
        else:
            bengali_bn = rest

    # --- Final Professional JSON Structure ---
    final_json = {
        "meta": {
            "location": {
                "city": "Dhaka",
                "city_bn": "ঢাকা",
                "country": "Bangladesh",
                "country_bn": "বাংলাদেশ",
                "timezone": "Asia/Dhaka"
            },
            "source": {
                "name": "Muslim Bangla",
                "url": URL
            },
            "scraped_at": {
                "utc": datetime.utcnow().isoformat() + "Z",
                "bst": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "timestamp": int(datetime.now().timestamp())
            }
        },
        "date": {
            "gregorian": {
                "date": datetime.now().strftime("%Y-%m-%d"),
                "weekday_en": datetime.now().strftime("%A"),
                "weekday_bn": weekday_bn
            },
            "hijri": {
                "full_bn": hijri_bn,
                "full_en": to_en(hijri_bn),
                "day": to_en(hijri_bn.split()[0]) if hijri_bn else "",
                "month_bn": hijri_bn.split()[1] if len(hijri_bn.split()) > 1 else "",
                "year": to_en(hijri_bn.split(",")[0].split()[-1]) if "," in hijri_bn else ""
            },
            "bengali": {
                "full_bn": bengali_bn,
                "full_en": to_en(bengali_bn),
                "weekday_bn": weekday_bn
            },
            "combined_bn": date_full_bn,
            "combined_en": to_en(date_full_bn)
        },
        "prayer_times": extract_section(soup, "ওয়াক্তের সময়সূচী"),
        "forbidden_times": extract_section(soup, "নামাজের নিষিদ্ধ সময়সূচী"),
        "nafl_times": extract_section(soup, "নফল নামাজের সময়সূচী")
    }

    # prayer_times কে আরও professional flat key তে convert (fajr, dhuhr etc)
    mapping = {"ফজর": "fajr", "যুহর": "dhuhr", "আসর": "asr", "মাগরিব": "maghrib", "ইশা": "isha",
               "সূর্যোদয়": "sunrise", "দুপুর": "noon", "সূর্যাস্ত": "sunset",
               "তাহাজ্জুদ": "tahajjud", "ইশরাক": "ishraq", "চাশত": "chasht", "সাহরী": "sehri_end"}

    def professionalize(section_dict):
        pro = {}
        for bn_label, obj in section_dict.items():
            key = "unknown"
            for k_bn, k_en in mapping.items():
                if k_bn in bn_label:
                    key = k_en
                    break
            if key == "unknown":
                key = bn_label # fallback
            pro[key] = obj
        return pro

    final_json["prayer_times"] = professionalize(final_json["prayer_times"])
    final_json["forbidden_times"] = professionalize(final_json["forbidden_times"])
    final_json["nafl_times"] = professionalize(final_json["nafl_times"])

    # Special handling for sehri which label is "সাহরী(শেষ)"
    if "unknown" in final_json["nafl_times"]:
        # try to fix
        pass

    return final_json

if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    data = scrape()
    print(json.dumps(data, ensure_ascii=False, indent=2))
    with open("data/dhaka.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
