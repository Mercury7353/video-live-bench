import requests
import json
import time
import os

# 多个 API Key
API_KEYS = [
    # "REDACTED_YOUTUBE_API_KEY",
    "REDACTED_YOUTUBE_API_KEY",
    "REDACTED_YOUTUBE_API_KEY",
    "REDACTED_YOUTUBE_API_KEY",
    "REDACTED_YOUTUBE_API_KEY",
    "REDACTED_YOUTUBE_API_KEY"
]
current_key_index = 0  # 当前使用的 key

# 自动切换 API Key
def get_api_key():
    global current_key_index
    return API_KEYS[current_key_index]

def switch_api_key():
    """切换到下一个 API key"""
    global current_key_index
    current_key_index += 1
    if current_key_index >= len(API_KEYS):
        print("\n❌ 所有 API Key 都已用完，无法继续请求！")
        exit()
    print(f"\n⚠️ API 配额可能耗尽，正在切换到下一个 API Key: {API_KEYS[current_key_index]}")


def safe_request(url, params):
    """
    包装 requests.get，自动在 API 超限时切换 Key
    """
    while True:
        params["key"] = get_api_key()
        res = requests.get(url, params=params)
        data = res.json()

        # 检查常见的配额错误
        if "error" in data:
            continue

        return data


# =================== 参数设置 ===================
PUBLISHED_AFTER = "2026-01-01T00:00:00Z"
REQUEST_INTERVAL = 0.3
MAX_PAGES = 1

search_url = "https://www.googleapis.com/youtube/v3/search"
video_url = "https://www.googleapis.com/youtube/v3/videos"

CATEGORY_KEYWORDS = {
  "Entertainment": [
    "Daily vlogs",
    "Travel vlogs",
    "Storytime",
    "Q&A sessions",
    "Sketches",
    "Short films",
    "Stand-up",
    "Movie reviews",
    "Film trailers",
    "Music videos",
    "Covers",
    "Remixes",
    "Parodies",
    "Lyric videos",
    "Gaming livestreams",
    "Event livestreams",
    "Let's plays",
    "Walkthroughs",
    "Game commentary",
    "Game reviews"
  ],
  "Education": [
    "Marketing strategies",
    "Entrepreneurship",
    "Investment guides",
    "Motivational talks",
    "TED-style talks",
    "Expert interviews",
    "Software tutorials",
    "Academic tutorials",
    "Team projects",
    "Engineering guides",
    "Language lessons",
    "Pronunciation guides",
    "Historical analysis",
    "Documentary videos",
    "Cooking tutorials",
    "DIY and crafts"
  ],
  "Science & Technology": [
    "AI concepts",
    "Astronomy",
    "Space missions",
    "Physics",
    "Chemistry",
    "Biology",
    "Climate change",
    "Conservation efforts",
    "Gadget reviews",
    "Software reviews"
  ],
  "Lifestyle": [
    "Travel tips",
    "Destination guides",
    "Food reviews",
    "Recipe videos",
    "Nutrition guides",
    "Workout routines",
    "Mental health tips",
    "Parenting tips",
    "Skincare routines",
    "Makeup tutorials",
    "Fashion hauls",
    "Gardening tips",
    "Home improvement",
    "Family vlogs"
  ],
  "News & Politics": [
    "Breaking news",
    "World news",
    "Political news",
    "Political interviews",
    "Political commentary",
    "Editorials",
    "Social commentary",
    "Celebrity news"
  ],
  "Hobbies & Interests": [
    "ASMR",
    "Unboxing videos",
    "Buyer's guides",
    "Ranked lists",
    "Top 10 videos",
    "Reactions",
    "Pranks",
    "Toy collections",
    "Memorabilia",
    "Fishing",
    "Camping",
    "Knitting",
    "Game tutorials"
  ],
  "Sports": [
    "Training techniques",
    "Athlete workouts",
    "Analysis videos",
    "Sports talk shows",
    "Career highlights",
    "Game highlights",
    "Match replays",
    "Documentary profiles"
  ],
  "Art & Creativity": [
    "Writing tips",
    "Book reviews",
    "Photography tips",
    "Art exhibitions",
    "Painting tutorials",
    "Drawing tutorials",
    "Poetry readings"
  ],
  "Automotive": [
    "Car reviews",
    "Driving tutorials",
    "Car modifications",
    "Racing highlights"
  ]
}


# =================== 抓取逻辑 ===================

all_videos = {}
total_count = 0
parent_counts = {}

for parent_category, keywords in CATEGORY_KEYWORDS.items():
    print(f"\n====== 抓取父类：{parent_category} ======")
    parent_counts[parent_category] = 0

    for keyword in keywords:
        print(f"\n--- 使用关键词: {keyword} ---")

        next_page_token = None
        page = 0

        while page < MAX_PAGES:
            params = {
                "part": "snippet",
                "type": "video",
                "order": "relevance",
                "publishedAfter": PUBLISHED_AFTER,
                "q": keyword,
                "maxResults": 50
            }
            if next_page_token:
                params["pageToken"] = next_page_token

            data = safe_request(search_url, params)
            items = data.get("items", [])
            print(f"关键词 {keyword} 本页找到 {len(items)} 条")

            if not items:
                break

            video_ids = [item["id"]["videoId"] for item in items]
            time.sleep(REQUEST_INTERVAL)

            # 请求视频详情
            video_params = {
                "part": "snippet,contentDetails,recordingDetails",
                "id": ",".join(video_ids),
                "maxResults": 50
            }

            vdata = safe_request(video_url, video_params)

            for v in vdata.get("items", []):
                vid = v["id"]
                snippet = v["snippet"]
                content = v.get("contentDetails", {})
                record = v.get("recordingDetails", {})

                is_new = vid not in all_videos

                all_videos[vid] = {
                    "videoId": vid,
                    "title": snippet.get("title"),
                    "description": snippet.get("description"),
                    "publishedAt": snippet.get("publishedAt"),
                    "tags": snippet.get("tags", []),
                    "categoryId": snippet.get("categoryId"),

                    "duration": content.get("duration"),
                    "location": record.get("location", {}),

                    "parent_category": parent_category,
                    "keyword": keyword
                }

                if is_new:
                    parent_counts[parent_category] += 1
                    total_count += 1

            next_page_token = data.get("nextPageToken")
            if not next_page_token:
                break

            page += 1
            time.sleep(REQUEST_INTERVAL)


# 去重 + 保存
result_list = list(all_videos.values())
unique_list = list({v["videoId"]: v for v in result_list}.values())

save_path = "outputs"
os.makedirs(save_path, exist_ok=True)
with open(os.path.join(save_path, "result_keywords_relevance.json"), "w", encoding="utf-8") as f:
    json.dump(unique_list, f, indent=4, ensure_ascii=False)

print(f"\n🎉 完成：共抓取 {len(unique_list)} 条视频（已去重）")
