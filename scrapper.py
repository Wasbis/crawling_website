import os
import time
import json
import requests
import scrapy
from scrapy.crawler import CrawlerProcess
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from fake_useragent import UserAgent
from tqdm import tqdm
from urllib.parse import urljoin
from datetime import datetime
import string
import random

# ==============================
# 1. GOOGLE SEARCH API (BYPASS CAPTCHA)
# ==============================
GOOGLE_API_KEY = "AIzaSyBz6nLXiTQh46BX1G5YBE6F5th5y4LAFmI"  # Ganti dengan API Key lo
SEARCH_ENGINE_ID = "567e87d4a12444da6"  # Ganti dengan Custom Search Engine ID


def google_search_api(query, num_results=100):
    urls = []
    # API mengembalikan 10 hasil per request, jadi loop untuk mengambil lebih banyak.
    for start in range(1, num_results+1, 10):
        url = f"https://www.googleapis.com/customsearch/v1?q={query}&key={GOOGLE_API_KEY}&cx={SEARCH_ENGINE_ID}&start={start}"
        response = requests.get(url)
        data = response.json()
        urls += [item["link"] for item in data.get("items", [])]
        if len(urls) >= num_results:
            break
    return urls[:num_results] if urls else None

# ==============================
# 2. FALLBACK KE SELENIUM JIKA API GAGAL
# ==============================


def google_search_selenium(query, num_results=100):
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument(f"user-agent={UserAgent().random}")

    driver = webdriver.Edge(options=options)
    search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}&num={num_results}"
    driver.get(search_url)
    time.sleep(2)

    # Scroll ke bawah untuk load lebih banyak hasil
    for _ in range(5):
        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.END)
        time.sleep(2)

    links = []
    results = driver.find_elements(By.CSS_SELECTOR, "div.tF2Cxc a")
    for result in results[:num_results]:
        links.append(result.get_attribute("href"))

    driver.quit()
    return links if links else None

# ==============================
# 3. GET URL DARI BEBERAPA VARIASI QUERY (WORKAROUND UNTUK LEBIH DARI 100 HASIL)
# ==============================


def get_all_urls(query, total_results):
    # Kita ambil maksimal 100 hasil per query
    per_query = 100
    collected_urls = set()
    # Jumlah query yang diperlukan
    num_queries = (total_results // per_query) + \
        (1 if total_results % per_query else 0)

    # Query pertama adalah query asli
    for i in range(num_queries):
        # Untuk query selain yang pertama, tambahkan variasi (misalnya huruf acak)
        if i == 0:
            mod_query = query
        else:
            # Contoh: tambahkan string acak sepanjang 2 karakter
            mod_query = f"{query} {''.join(random.choices(string.ascii_lowercase, k=2))}"

        print(f"🔍 Mengambil hasil dengan query: '{mod_query}'")
        urls = google_search_api(mod_query, per_query)
        if not urls:
            print("⚠️ API gagal untuk query ini, mencoba fallback Selenium...")
            urls = google_search_selenium(mod_query, per_query)
        if urls:
            collected_urls.update(urls)
        # Berhenti jika sudah memenuhi jumlah yang diinginkan
        if len(collected_urls) >= total_results:
            break
        # Tunggu sebentar antar query
        time.sleep(1)
    # Return URL unik, ambil sesuai total_results jika memungkinkan
    return list(collected_urls)[:total_results]

# ==============================
# 4. SCRAPING DATA DARI SEMUA WEBSITE
# ==============================


def scrape_website(url, search_keyword):
    headers = {"User-Agent": UserAgent().random}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return {"url": url, "title": "Fetch Failed", "text_content": "⚠️ Gagal fetch halaman", "images": [], "files": []}

        soup = BeautifulSoup(response.text, "html.parser")
        title = soup.title.text.strip() if soup.title else "No Title"

        # Ambil seluruh teks dari semua <p>
        paragraphs = [p.get_text(separator=" ", strip=True)
                      for p in soup.find_all("p")]
        full_text = "\n".join(paragraphs)

        # Filter: hanya ambil halaman yang mengandung keyword pencarian (case-insensitive)
        if search_keyword.lower() not in full_text.lower():
            return {"url": url, "title": title, "text_content": "Halaman tidak relevan", "images": [], "files": []}

        # Ambil semua gambar, pastikan URL absolut
        images = []
        for img in soup.find_all("img"):
            src = img.get("src")
            if src:
                images.append(urljoin(url, src))

        # Ambil semua link file dengan ekstensi tertentu (PDF, DOC, XLS, PPT, dll)
        files = []
        file_exts = [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx"]
        for a in soup.find_all("a"):
            href = a.get("href")
            if href and any(href.lower().endswith(ext) for ext in file_exts):
                files.append(urljoin(url, href))

        # Jika konten teks terlalu sedikit, coba fallback ke Selenium untuk rendering JS
        if len(paragraphs) < 3:
            print(f"🔄 {url} butuh Selenium, mencoba ulang dengan rendering JS...")
            options = Options() 
            options.add_argument("--headless")
            options.add_argument("--disable-gpu")
            options.add_argument("--no-sandbox")
            driver = webdriver.Edge(options=options)
            driver.get(url)
            time.sleep(3)
            soup = BeautifulSoup(driver.page_source, "html.parser")
            driver.quit()
            paragraphs = [p.get_text(separator=" ", strip=True)
                          for p in soup.find_all("p")]
            full_text = "\n".join(paragraphs)

            # Update gambar & file dari halaman yang sudah di-render ulang
            images = []
            for img in soup.find_all("img"):
                src = img.get("src")
                if src:
                    images.append(urljoin(url, src))
            files = []
            for a in soup.find_all("a"):
                href = a.get("href")
                if href and any(href.lower().endswith(ext) for ext in file_exts):
                    files.append(urljoin(url, href))

        return {
            "url": url,
            "title": title,
            "text_content": full_text,
            "images": images,
            "files": files
        }
    except Exception as e:
        return {"url": url, "title": "Error", "text_content": f"⚠️ {str(e)}", "images": [], "files": []}


# ==============================
# 5. MAIN EXECUTION
# ==============================
if __name__ == "__main__":
    search_query = input("Masukkan keyword pencarian: ")
    num_websites_input = input(
        "Masukkan jumlah website yang ingin diambil (default 300): ")
    try:
        num_websites = int(
            num_websites_input) if num_websites_input.strip() != "" else 300
    except ValueError:
        num_websites = 300

    print("\n🔍 Mencari di Google : " + search_query)
    urls = get_all_urls(search_query, num_websites)

    if not urls:
        print("❌ Gagal mendapatkan hasil pencarian. Coba ganti keyword!")
        exit()

    print(f"\n📄 Ditemukan {len(urls)} URL dari Google:")
    for url in urls:
        print(url)

    print("\n📌 Scraping konten dari semua website yang relevan...")
    scraped_results = []
    for url in tqdm(urls, desc="Processing", unit="site"):
        result = scrape_website(url, search_query)
        scraped_results.append(result)

    print("\n🎯 Scraping selesai! Total halaman yang berhasil diambil:",
          len(scraped_results))

    # Buat nama file JSON dengan timestamp (misal: scraped_results_2025-03-06_15-30-00.json)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    json_filename = f"scraped_results_{timestamp}.json"

    with open(json_filename, "w", encoding="utf-8") as f:
        json.dump(scraped_results, f, indent=4, ensure_ascii=False)

    print("\n💾 Data telah disimpan ke", json_filename)
