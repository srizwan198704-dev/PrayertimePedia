import requests
from bs4 import BeautifulSoup
import json
import re
import os
from datetime import datetime

URL = "https://muslimbangla.com/world/BD/prayer-times-Dhaka"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
BN_TO_EN = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
def to_en(s): return s.translate(BN_TO_EN) if s else ""

def get_time_from_block(block_text):
    """ব্লক থেকে ০৪:১৬ - ০৫:৩৫ বের করে"""
    m = re.search(r"[০-৯]{1,2}:[০-৯]{2}(?:\s*-\s*[০-৯]{1,2}:[০-৯]{2})?", block_text)
    return m.group(0).strip() if m else ""

def scrape():
    html = requests.get(URL, headers=HEADERS, timeout=20).text
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text("\n", strip=True)

    # ===== ১. তারিখ - সবচেয়ে নির্ভরযোগ্য Regex =====
    # প্যাটার্ন: "৬ রবিউল আউয়াল, ১৪৪৮ হিজরি • বৃহস্পতিবার, ৫ ভাদ্র, ১৪৩৩ বঙ্গাব্দ"
    date_pattern = r"[০-৯]{1,2}\s+[^\n]*?হিজরি\s*•\s*[^\n]*?বঙ্গাব্দ"
    m_date = re.search(date_pattern, html) or re.search(date_pattern, text)
    # html থেকে না পেলে text থেকে
    if not m_date:
        # fallback - text থেকে লাইন বাই লাইন
        for line in text.split("\n"):
            if "হিজরি" in line and "বঙ্গাব্দ" in line:
                m_date = line
                break
        full_bn = m_date.strip() if isinstance(m_date, str) else ""
    else:
        full_bn = m_date.group(0) if hasattr(m_date, 'group') else str(m_date)
        full_bn = BeautifulSoup(full_bn, "lxml").get_text(strip=True)

    full_bn = full_bn.strip()
    hijri_bn = full_bn.split("•")[0].strip() if "•" in full_bn else full_bn
    bengali_bn = full_bn.split("•")[1].strip() if "•" in full_bn else ""

    # ===== ২,৩,৪. সময়সূচী - h3/h4 থেকে =====
    def extract_by_names(names):
        result = {}
        for name in names:
            # h3/h4 যেখানে name আছে
            tag = soup.find(lambda t: t.name in ["h3","h4"] and name in t.get_text())
            if not tag:
                continue
            # parent থেকে টাইম
            parent = tag.parent
            block = parent.get_text(" ", strip=True) if parent else tag.get_text(" ", strip=True) + " " + str(tag.next_sibling)
            bn_time = get_time_from_block(block)
            # যদি parent এ না থাকে, পরের 2-3 টা sibling এ খোঁজো
            if not bn_time:
                nxt = tag.find_next()
                for _ in range(3):
                    if not nxt: break
                    bn_time = get_time_from_block(nxt.get_text(" ", strip=True) if hasattr(nxt,'get_text') else str(nxt))
                    if bn_time: break
                    nxt = nxt.find_next() if hasattr(nxt,'find_next') else None
            
            if bn_time:
                en_time = to_en(bn_time)
                if "-" in en_time:
                    start, end = [x.strip() for x in en_time.split("-",1)]
                else:
                    start, end = en_time, ""
                result[name] = {
                    "bn": bn_time,
                    "en": en_time,
                    "start": start,
                    "end": end
                }
        return result

    # তোমার চাওয়া ৪ ভাগ
    waqt_names = ["ফজর", "যুহর", "আসর", "মাগরিব", "ইশা"]
    forbidden_names = ["সূর্যোদয়", "দুপুর", "সূর্যাস্ত"]
    nafl_names = ["তাহাজ্জুদ", "ইশরাক", "চাশত", "সাহরী"]

    waqt = extract_by_names(waqt_names)
    forbidden = extract_by_names(forbidden_names)
    nafl = extract_by_names(nafl_names)

    # ===== FINAL PROFESSIONAL JSON =====
    final = {
        "meta": {
            "location": "Dhaka, Bangladesh",
            "source_url": URL,
            "scraped_at_utc": datetime.utcnow().isoformat() + "Z",
            "scraped_at_bst": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        },
        "date": {
            "full_bn": full_bn,
            "full_en": to_en(full_bn),
            "hijri": {
                "bn": hijri_bn,
                "en": to_en(hijri_bn)
            },
            "bengali": {
                "bn": bengali_bn,
                "en": to_en(bengali_bn)
            }
        },
        "waqt": waqt,
        "forbidden": forbidden,
        "nafl": nafl
    }
    return final

if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    data = scrape()
    print(json.dumps(data, ensure_ascii=False, indent=2))
    with open("data/dhaka.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("\n✅ Success - date should now appear!")
