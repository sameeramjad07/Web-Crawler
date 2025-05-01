class Config:
    """Configuration settings for the web crawler."""
    SEED_URL = "https://www.geeksforgeeks.org/"  # Starting URL
    MAX_PAGES = 50  # Maximum number of pages to crawl
    MAX_DEPTH = 2   # Maximum crawl depth
    OUTPUT_DIR = "outputs/parallel - mpi"  # Directory to save results
    DATA_TO_EXTRACT = [
        'title',              # Extract page title
        # 'p',                  # Extract paragraphs
        'h1',                 # Extract H1 headings
        'meta_description',   # Extract meta description
        # '.article-title'    # Example: Custom CSS selector (uncomment to use)
    ]
    
    # New parameters for enhanced crawler features
    WORKER_TIMEOUT = 60       # Seconds before considering a worker hung/stuck
    REQUEST_TIMEOUT = (3, 30) # Connection and read timeouts for HTTP requests
    STATUS_INTERVAL = 5       # How often (in seconds) to log status updates
    
    # Advanced settings (optional)
    DYNAMIC_LOAD_BALANCING = True  # Enable dynamic worker prioritization
    RETRY_FAILED_URLS = True       # Re-add failed URLs to the queue (with limit)
    MAX_RETRIES = 2               # Maximum number of retries for failed URLs