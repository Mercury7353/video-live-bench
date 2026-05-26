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

num_categories = {}
for key, value in CATEGORY_KEYWORDS.items():
    num_categories[key] = len(value)
print(num_categories)

total_categories = 0
for key, value in num_categories.items():
    total_categories += value
print(total_categories)