import requests
from bs4 import BeautifulSoup
import json
import re
import os
from datetime import datetime

URL = "https://muslimbangla.com/world/BD/prayer-times-Dhaka"
HEADERS = {"User-Agent": "Mozilla/5.0"}

BN_TO_EN = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")

def to_en(bn_str):
    if not bn_str: return ""
    return bn_str.translate(BN_TO_EN)

def extract_section(soup, section_title_keyword):
    """
    section_title_keyword: যেমন 'ওয়াক্তের সময়সূচী'
    এর পর থেকে পরবর্তী h2 পর্যন্ত সব h3/h4 ট্যাগ থেকে ডাটা নেবে
    """
    result = {}
    # h2 খুঁজে বের করা যেখানে section title আছে
    h2 = soup.find(lambda tag: tag.name == "h2" and section_title_keyword in tag.get_text())
    if not h2:
        return result
    
    # h2 এর পর থেকে next h2 আসার আগ পর্যন্ত
    for sibling in h2.find_all_next():
        if sibling.name == "h2":
            break
        if sibling.name in ["h3", "h4"]:
            name_bn = sibling.get_text(strip=True)
            # টাইমটা সাধারণত sibling এর parent বা পরের tag এ থাকে
            # পেজের স্ট্রাকচার: <h3>ফজর</h3> \n ০৪:১৬ - ০৫:৩৫
            time_bn = ""
            # 1. next sibling text
            nxt = sibling.next_sibling
            # next_sibling অনেক সময় \n হয়, তাই লুপ
            for _ in range(5):
                if nxt is None:
                    break
                txt = str(nxt).strip() if isinstance(nxt, str) else nxt.get_text(strip=True) if hasattr(nxt, 'get_text') else ""
                if re.search(r"[০-৯:]", txt):
                    time_bn = txt
                    break
                nxt = nxt.next_sibling if hasattr(nxt, 'next_sibling') else None
            
            # 2. fallback: parent text থেকে
            if not time_bn:
                parent_text = sibling.parent.get_text(" ", strip=True)
                m = re.search(r"[০-৯]{2}:[০-৯]{2}(?:\s*-\s*[০-৯]{2}:[০-৯]{2})?", parent_text)
                if m:
                    time_bn = m.group(0)
            
            # 3. আরেকটা fallback: h3 এর পরের div/string
            if not time_bn:
                next_el = sibling.find_next(string=lambda s: re.search(r"[০-৯]{2}:[০-৯]{2}", s))
                if next_el:
                    time_bn = next_el.strip()

            if time_bn:
                # সাহরী এর ক্ষেত্রে একটাই টাইম
                clean_bn = re.search(r"[০-৯]{1,2}:[০-৯]{2}(?:\s*-\s*[০-৯]{1,2}:[০-৯]{2})?", time_bn)
                if clean_bn:
                    time_bn = clean_bn.group(0)

                result[name_bn] = {
                    "bn": time_bn,
                    "en": to_en(time_bn)
                }
    return result


def scrape():
    res = requests.get(URL, headers=HEADERS, timeout=20)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "lxml")

    # ১. তারিখ - পেজের প্রথম h2 এর পরের text
    date_text = ""
    try:
        # "৬ রবিউল আউয়াল..." এই লাইনটা h2 এর পরেই থাকে
        first_h2 = soup.find("h2")
        if first_h2:
            # h2 এর আগের div বা h2 এর parent এর আগের sibling
            # সহজ উপায়: পুরো text থেকে hijri line খোঁজা
            full_text_lines = soup.get_text("\n").split("\n")
            for line in full_text_lines:
                if "হিজরি" in line and "বঙ্গাব্দ" in line:
                    date_text = line.strip()
                    break
    except:
        pass

    # আলাদা করে হিজরি, বাংলা, ইংরেজি ভাগ করা
    hijri = ""
    bangla_date = ""
    if "•" in date_text:
        parts = date_text.split("•")
        hijri = parts[0].strip()
        bangla_date = parts[1].strip() if len(parts) > 1 else ""

    # ২, ৩, ৪ - তিনটা সেকশন
    waqt = extract_section(soup, "ওয়াক্তের সময়সূচী")
    forbidden = extract_section(soup, "নামাজের নিষিদ্ধ সময়সূচী")
    nafl = extract_section(soup, "নফল নামাজের সময়সূচী")

    # নফলে একই নাম দুবার আসে, তাই শেষেরটা থাকবে - আমরা dict কে merge করেছি, তাই unique থাকবে

    final_json = {
        "meta": {
            "location": "ঢাকা, বাংলাদেশ",
            "location_en": "Dhaka, Bangladesh",
            "source_url": URL,
            "scraped_at": datetime.now().isoformat(),
            "scraped_at_bst": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        },
        "১_তারিখ": {
            "full_bn": date_text,
            "hijri": hijri,
            "bengali": bangla_date,
            "hijri_en": to_en(hijri),
            "bengali_en": to_en(bangla_date)
        },
        "২_ওয়াক্তের_সময়সূচী": waqt,
        "৩_নামাজের_নিষিদ্ধ_সময়সূচী": forbidden,
        "৪_নফল_নামাজের_সময়সূচী": nafl
    }

    return final_json


if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    data = scrape()
    # কনসোলে দেখাও
    print(json.dumps(data, ensure_ascii=False, indent=2))

    # ফাইলে সেভ
    with open("data/dhaka.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    # API friendly flat version ও সেভ করলাম
    with open("data/dhaka_flat.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("\n✅ data/dhaka.json তৈরি হয়েছে")
