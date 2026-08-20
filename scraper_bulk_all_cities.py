import requests, re, json, os, time
from bs4 import BeautifulSoup
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import random

COUNTRY_JSON_PATH = "country.json"
OUTPUT_DIR = "data"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
BN_TO_EN = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")

def to_en(s): return s.translate(BN_TO_EN) if s else ""
def clean(s): return re.sub(r"\s+", " ", s).strip() if s else ""

def scrape_single_city(country_code, country_en, country_bn, timezone, city):
    slug = city.get("slug")
    url = city.get("url") or f"https://muslimbangla.com/world/{country_code}/prayer-times-{slug}"
    try:
        html = requests.get(url, headers=HEADERS, timeout=20).text
        soup = BeautifulSoup(html, "lxml")
        body_text = soup.body.get_text(" ", strip=True) if soup.body else soup.get_text(" ", strip=True)
        body_text = clean(body_text)
        m = re.search(r"([০-৯]+\s+[^\n•]+?হিজরি)\s*•\s*([^\n•]+?বঙ্গাব্দ)", body_text)
        if m:
            hijri_bn = clean(m.group(1))
            bengali_bn = clean(m.group(2))
            full_bn = f"{hijri_bn} • {bengali_bn}"
        else:
            hijri_bn = bengali_bn = full_bn = ""

        def get_time_from_parent(tag):
            parent_text = tag.parent.get_text(" ", strip=True) if tag.parent else ""
            mt = re.search(r"[০-৯]{1,2}:[০-৯]{2}(?:\s*-\s*[০-৯]{1,2}:[০-৯]{2})?", parent_text)
            if mt:
                return clean(mt.group(0))
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
            h2 = soup.find(lambda t: t.name == "h2" and section_keyword in t.get_text())
            if not h2:
                return result
            for sib in h2.find_all_next():
                if sib.name == "h2":
                    break
                if sib.name in ["h3","h4"]:
                    label = clean(sib.get_text())
                    if not label or len(label) > 25:
                        continue
                    matched = None
                    for exp in expected_labels:
                        if exp in label:
                            matched = exp
                            break
                    if not matched:
                        continue
                    bn_time = get_time_from_parent(sib)
                    if bn_time and matched not in result:
                        en_time = to_en(bn_time)
                        start, end = (en_time.split("-")[0].strip(), en_time.split("-")[1].strip()) if "-" in en_time else (en_time, "")
                        key_map = {"ফজর":"fajr","যুহর":"dhuhr","আসর":"asr","মাগরিব":"maghrib","ইশা":"isha",
                                   "সূর্যোদয়":"sunrise","দুপুর":"noon","সূর্যাস্ত":"sunset",
                                   "তাহাজ্জুদ":"tahajjud","ইশরাক":"ishraq","চাশত":"chasht","সাহরী":"sehri_end"}
                        key = key_map.get(matched, matched)
                        result[key] = {"label_bn": matched, "time_bn": bn_time, "time_en": en_time, "start": start, "end": end}
            return result

        prayer = build_section("ওয়াক্তের সময়সূচী", ["ফজর","যুহর","আসর","মাগরিব","ইশা"])
        forbidden = build_section("নামাজের নিষিদ্ধ সময়সূচী", ["সূর্যোদয়","দুপুর","সূর্যাস্ত"])
        nafl = build_section("নফল নামাজের সময়সূচী", ["তাহাজ্জুদ","ইশরাক","চাশত","সাহরী"])

        final = {
            "meta": {
                "location": {
                    "city": city.get("name_en"), "city_bn": city.get("name_bn"), "slug": slug,
                    "country": country_en, "country_bn": country_bn, "country_code": country_code,
                    "timezone": timezone, "division": city.get("division", ""), "type": city.get("type", "city")
                },
                "source_url": url, "scraped_at": datetime.now().isoformat()
            },
            "date": {
                "full": {"bn": full_bn, "en": to_en(full_bn)},
                "hijri": {"bn": hijri_bn, "en": to_en(hijri_bn)},
                "bengali": {"bn": bengali_bn, "en": to_en(bengali_bn)}
            },
            "prayer_times": prayer, "forbidden_times": forbidden, "nafl_times": nafl
        }
        return final, None
    except Exception as e:
        return None, str(e)

def main():
    if not os.path.exists(COUNTRY_JSON_PATH):
        print(f"❌ {COUNTRY_JSON_PATH} পাওয়া যায়নি!")
        return
    with open(COUNTRY_JSON_PATH, "r", encoding="utf-8") as f:
        db = json.load(f)
    countries = db.get("countries") if isinstance(db, dict) and "countries" in db else db
    print(f"📦 {len(countries)} দেশ, স্ক্র্যাপ শুরু...")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    tasks = []
    for country in countries:
        code = country["code"]; c_en = country["name_en"]; c_bn = country["name_bn"]; tz = country.get("timezone","")
        for city in country.get("cities", []):
            tasks.append((code, c_en, c_bn, tz, city))
    print(f"🌍 মোট {len(tasks)} টি শহর")
    success = 0; failed = 0
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_city = {executor.submit(scrape_single_city, code, c_en, c_bn, tz, city): (code, city) for code, c_en, c_bn, tz, city in tasks}
        for future in as_completed(future_to_city):
            code, city = future_to_city[future]
            slug = city.get("slug")
            try:
                result, err = future.result()
                if err:
                    print(f"❌ [{code}/{slug}] Failed: {err}"); failed+=1
                else:
                    country_dir = os.path.join(OUTPUT_DIR, code)
                    os.makedirs(country_dir, exist_ok=True)
                    path1 = os.path.join(country_dir, f"{slug}.json")
                    with open(path1, "w", encoding="utf-8") as out:
                        json.dump(result, out, ensure_ascii=False, indent=2)
                    print(f"✅ [{code}/{slug}] -> {path1}")
                    success+=1
                time.sleep(random.uniform(0.5, 1.5))
            except Exception as e:
                print(f"❌ [{code}/{slug}] Exception: {e}"); failed+=1
    print(f"\n🎉 Done! Success: {success}, Failed: {failed}")

if __name__ == "__main__":
    main()
