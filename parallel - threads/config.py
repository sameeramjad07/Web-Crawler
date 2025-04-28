class Config:
    """Configuration settings for the web crawler."""
    SEED_URL = "https://www.geeksforgeeks.org/"  # Starting URL
    MAX_PAGES = 50  # Maximum number of pages to crawl
    MAX_DEPTH = 2   # Maximum crawl depth
    NUM_THREADS = 8  # Number of worker threads
    OUTPUT_DIR = "outputs/parallel - threads"  # Directory to save results
    DATA_TO_EXTRACT = [
        'title',              # Extract page title
        # 'p',                  # Extract paragraphs
        'h1',                 # Extract H1 headings
        'meta_description',   # Extract meta description
        # '.article-title'    # Example: Custom CSS selector (uncomment to use)
    ]