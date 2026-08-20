import requests, re, json, os, subprocess, time
from bs4 import BeautifulSoup
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

CITIES_FILE = "BangladeshCities.json"
OUTPUT_DIR = "BD"
HEADERS = {"User-Agent": "Mozilla/5.0"}
BN_TO_EN = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
MAX_WORKERS = 20 # একসাথে 15 টা শহর scrape করবে

def to_en(s): return s.translate(BN_TO_EN) if s else ""
def clean(s): return re.sub(r"\s+", " ", s).strip() if s else ""

def get_time_from_parent(tag):
    try:
        parent_text = tag.parent.get_text(" ", strip=True) if tag.parent else ""
        mt = re.search(r"[০-৯]{1,2}:[০-৯]{2}(?:\s*-\s*[০-৯]{1,2}:[০-৯]{2})?", parent_text)
        if mt: return clean(mt.group(0))
        nxt = tag.find_next()
        for _ in range(4):
            if not nxt: break
            txt = nxt.get_text(" ", strip=True) if hasattr(nxt, 'get_text') else str(nxt)
            mt = re.search(r"[০-৯]{1,2}:[০-৯]{2}(?:\s*-\s*[০-৯]{1,2}:[০-৯]{2})?", txt)
            if mt: return clean(mt.group(0))
            nxt = nxt.find_next() if hasattr(nxt, 'find_next') else None
    except: pass
    return ""

def build_section(soup, section_keyword, expected_labels):
    result = {}
    h2 = soup.find(lambda t: t.name == "h2" and section_keyword in t.get_text())
    if not h2: return result
    for sib in h2.find_all_next():
        if sib.name == "h2": break
        if sib.name in ["h3","h4"]:
            label = clean(sib.get_text())
            if not label or len(label) > 25: continue
            matched = next((exp for exp in expected_labels if exp in label), None)
            if not matched: continue
            bn_time = get_time_from_parent(sib)
            if bn_time and not any(v.get('label_bn') == matched for v in result.values()):
                en_time = to_en(bn_time)
                start, end = (en_time.split("-")[0].strip(), en_time.split("-")[1].strip()) if "-" in en_time else (en_time, "")
                key_map = {"ফজর":"fajr","যুহর":"dhuhr","আসর":"asr","মাগরিব":"maghrib","ইশা":"isha","সূর্যোদয়":"sunrise","দুপুর":"noon","সূর্যাস্ত":"sunset","তাহাজ্জুদ":"tahajjud","ইশরাক":"ishraq","চাশত":"chasht","সাহরী":"sehri_end"}
                key = key_map.get(matched, matched)
                result[key] = {"label_bn": matched, "time_bn": bn_time, "time_en": en_time, "start": start, "end": end}
    return result

def scrape_city(city):
    url = city['url']
    try:
        html = requests.get(url, headers=HEADERS, timeout=20).text
        soup = BeautifulSoup(html, "lxml")
        body_text = clean(soup.body.get_text(" ", strip=True) if soup.body else soup.get_text(" ", strip=True))
        m = re.search(r"([০-৯]+\s+[^\n•]+?হিজরি)\s*•\s*([^\n•]+?বঙ্গাব্দ)", body_text)
        hijri_bn, bengali_bn, full_bn = ("","","")
        if m:
            hijri_bn = clean(m.group(1)); bengali_bn = clean(m.group(2))
            full_bn = f"{hijri_bn} • {bengali_bn}"

        prayer = build_section(soup, "ওয়াক্তের সময়সূচী", ["ফজর","যুহর","আসর","মাগরিব","ইশা"])
        if not prayer: return None

        forbidden = build_section(soup, "নামাজের নিষিদ্ধ সময়সূচী", ["সূর্যোদয়","দুপুর","সূর্যাস্ত"])
        nafl = build_section(soup, "নফল নামাজের সময়সূচী", ["তাহাজ্জুদ","ইশরাক","চাশত","সাহরী"])

        final = [{"hijridate": full_bn,"meta": {"location": {"city": city['name_en'],"city_bn": city['name_bn'],"slug": city['slug'],"division": city.get('division',''),"country": "Bangladesh","country_bn": "বাংলাদেশ","timezone": "Asia/Dhaka"},"source_url": url,"scraped_at": datetime.now().isoformat()},"date": {"full": {"bn": full_bn, "en": to_en(full_bn)},"hijri": {"bn": hijri_bn, "en": to_en(hijri_bn)},"bengali": {"bn": bengali_bn, "en": to_en(bengali_bn)}},"prayer_times": prayer,"forbidden_times": forbidden,"nafl_times": nafl}]

        safe_name = re.sub(r'[^\w\-]', '_', city['name_en']).strip('_') or f"city_{city['id']}"
        filepath = os.path.join(OUTPUT_DIR, f"{safe_name}.json")
        with open(filepath, "w", encoding="utf-8") as out:
            json.dump(final, out, ensure_ascii=False, indent=2)
        print(f"✅ {city['name_en']}")
        return filepath
    except Exception as e:
        print(f"❌ {city['name_en']}: {e}")
        return None

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True)
    subprocess.run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], check=True)

    with open(CITIES_FILE, "r", encoding="utf-8") as f:
        cities = json.load(f)

    print(f"Found {len(cities)} cities, scraping with {MAX_WORKERS} workers...")

    saved_files = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(scrape_city, city): city for city in cities}
        for future in as_completed(futures):
            res = future.result()
            if res: saved_files.append(res)

    print(f"\nScraped {len(saved_files)}/{len(cities)}. Now single commit & push...")

    if saved_files:
        subprocess.run(["git", "add", OUTPUT_DIR], check=True)
        # check if anything to commit
        if subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode!= 0:
            subprocess.run(["git", "commit", "-m", f"update all BD prayer times {datetime.now().strftime('%Y-%m-%d %H:%M')}"], check=True)
            subprocess.run(["git", "push"], check=True)
            print("✅ Single push done")
        else:
            print("No changes to push")

if __name__ == "__main__":
    main()
