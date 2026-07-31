from analyzer.ai_recommendation import (
    generate_ai_recommendation,
)

report = {
    "seo_score":80,

    "content":{
        "word_count":1200,
        "keyword_density":2.5,
    },

    "entity":{
        "coverage_percentage":65,
    },

    "page":{
        "headings":{
            "h1_count":2,
            "h2_count":7,
        }
    },

    "problems":[
        "Keyword density tinggi",
        "Entity coverage rendah",
    ],

    "recommendations":[
        "Tambah FAQ",
        "Tambah Internal Link",
    ],
}

result = generate_ai_recommendation(
    report
)

print(result["content"])