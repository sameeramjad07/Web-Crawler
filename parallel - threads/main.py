import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import time
import json
import os
from queue import Queue, Empty
from concurrent.futures import ThreadPoolExecutor
import logging
import matplotlib.pyplot as plt
from wordcloud import WordCloud
from threading import Lock
from config import Config

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MultiThreadedCrawler:
    def __init__(self, config):
        """Initialize the multi-threaded web crawler with configuration."""
        self.seed_url = config.SEED_URL
        self.root_url = f"{urlparse(self.seed_url).scheme}://{urlparse(self.seed_url).netloc}"
        self.max_pages = config.MAX_PAGES
        self.max_depth = config.MAX_DEPTH
        self.num_threads = config.NUM_THREADS
        self.output_dir = config.OUTPUT_DIR
        self.data_to_extract = config.DATA_TO_EXTRACT
        self.crawl_queue = Queue()
        self.visited_urls = set()
        self.visited_lock = Lock()  # Lock for thread-safe visited_urls
        self.results = []  # Store extracted data
        self.results_lock = Lock()  # Lock for thread-safe results
        self.crawl_queue.put((self.seed_url, 0))  # (url, depth)
        self.pages_crawled = 0
        self.pages_crawled_lock = Lock()  # Lock for thread-safe counter
        self.start_time = None
        self.time_points = []  # Track time for each page
        self.page_counts = []  # Track page count for time plot
        self.thread_metrics = {}  # Track pages crawled per thread

    def fetch_page(self, url):
        """Fetch a web page and return its response or None if it fails."""
        try:
            response = requests.get(url, timeout=(3, 30))
            if response.status_code == 200:
                return response
            else:
                logger.warning(f"Failed to fetch {url}: Status code {response.status_code}")
                return None
        except requests.RequestException as e:
            logger.error(f"Error fetching {url}: {e}")
            return None

    def extract_data(self, soup, url):
        """Extract specified data from the page based on config."""
        extracted_data = {'url': url}
        
        for item in self.data_to_extract:
            try:
                if item == 'title':
                    title_tag = soup.find('title')
                    extracted_data['title'] = title_tag.text.strip() if title_tag else 'No Title'
                elif item == 'meta_description':
                    meta_tag = soup.find('meta', attrs={'name': 'description'})
                    extracted_data['meta_description'] = meta_tag['content'].strip() if meta_tag and 'content' in meta_tag.attrs else 'No Meta Description'
                elif item.startswith('.'):  # CSS selector
                    elements = soup.select(item)
                    extracted_data[item] = [elem.text.strip() for elem in elements]
                else:  # HTML tag (e.g., 'p', 'h1')
                    elements = soup.find_all(item)
                    extracted_data[item] = [elem.text.strip() for elem in elements]
            except Exception as e:
                logger.error(f"Error extracting {item} from {url}: {e}")
                extracted_data[item] = []

        return extracted_data

    def parse_links(self, soup):
        """Parse HTML to extract links."""
        links = []
        for anchor in soup.find_all('a', href=True):
            href = anchor['href']
            full_url = urljoin(self.root_url, href)
            if full_url.startswith(self.root_url) and full_url not in self.visited_urls:
                links.append(full_url)
        return links

    def crawl_task(self, thread_id):
        """Task executed by each thread to crawl URLs."""
        self.thread_metrics[thread_id] = 0
        while self.pages_crawled < self.max_pages:
            try:
                # Get URL from queue with timeout
                url, depth = self.crawl_queue.get(timeout=5)
                
                # Check if URL is already visited or depth exceeded
                with self.visited_lock:
                    if url in self.visited_urls or depth > self.max_depth:
                        continue
                    self.visited_urls.add(url)

                # Update pages crawled
                with self.pages_crawled_lock:
                    if self.pages_crawled >= self.max_pages:
                        return
                    self.pages_crawled += 1
                    self.thread_metrics[thread_id] += 1

                # Track time and page count
                with self.results_lock:
                    current_time = time.time() - self.start_time
                    self.time_points.append(current_time)
                    self.page_counts.append(self.pages_crawled)

                logger.info(f"Thread {thread_id} crawling: {url} (Depth: {depth})")

                # Fetch page
                response = self.fetch_page(url)
                if not response:
                    continue

                # Parse page
                soup = BeautifulSoup(response.text, 'html.parser')
                extracted_data = self.extract_data(soup, url)
                extracted_data['depth'] = depth
                links = self.parse_links(soup)

                # Store results
                with self.results_lock:
                    self.results.append(extracted_data)

                # Add new links to queue
                for link in links:
                    with self.visited_lock:
                        if link not in self.visited_urls:
                            self.crawl_queue.put((link, depth + 1))

                logger.info(f"Thread {thread_id} extracted data from {url}")

            except Empty:
                logger.info(f"Thread {thread_id} exiting: Queue empty")
                break
            except Exception as e:
                logger.error(f"Thread {thread_id} error: {e}")
                continue

    def save_results(self):
        """Save crawled data to a JSON file."""
        os.makedirs(self.output_dir, exist_ok=True)
        output_path = os.path.join(self.output_dir, 'results.json')
        with open(output_path, 'w') as f:
            json.dump(self.results, f, indent=4)
        logger.info(f"Results saved to {output_path}")

    def generate_visualizations(self, sequential_metrics):
        """Generate visualizations for crawled data and performance analysis."""
        os.makedirs(self.output_dir, exist_ok=True)

        # 1. Bar Chart: Pages per Depth
        depths = [result['depth'] for result in self.results]
        depth_counts = {}
        for depth in range(self.max_depth + 1):
            depth_counts[depth] = depths.count(depth)
        
        plt.figure(figsize=(8, 6))
        plt.bar(depth_counts.keys(), depth_counts.values(), color='skyblue')
        plt.xlabel('Crawl Depth')
        plt.ylabel('Number of Pages')
        plt.title('Pages Crawled per Depth')
        plt.grid(True, axis='y')
        plt.savefig(os.path.join(self.output_dir, 'depth_distribution.png'))
        plt.close()
        logger.info("Generated depth distribution bar chart")

        # 2. Word Cloud: Extracted Text
        all_text = []
        for result in self.results:
            for key, value in result.items():
                if key in self.data_to_extract and isinstance(value, list):
                    all_text.extend(value)
                elif key in self.data_to_extract and isinstance(value, str):
                    all_text.append(value)
        text = ' '.join(all_text)
        if text.strip():
            wordcloud = WordCloud(width=800, height=400, background_color='white').generate(text)
            plt.figure(figsize=(10, 5))
            plt.imshow(wordcloud, interpolation='bilinear')
            plt.axis('off')
            plt.title('Word Cloud of Extracted Content')
            plt.savefig(os.path.join(self.output_dir, 'word_cloud.png'))
            plt.close()
            logger.info("Generated word cloud")
        else:
            logger.warning("No text available for word cloud")


        # 3. Line Plot: Time vs. Pages Crawled
        plt.figure(figsize=(8, 6))
        plt.plot(self.page_counts, self.time_points, marker='o', color='green')
        plt.xlabel('Pages Crawled')
        plt.ylabel('Cumulative Time (seconds)')
        plt.title('Crawling Time vs. Pages Crawled')
        plt.grid(True)
        plt.savefig(os.path.join(self.output_dir, 'time_vs_pages.png'))
        plt.close()
        logger.info("Generated time vs. pages plot")


        # # 4. Performance Analysis: Speedup and Efficiency
        # thread_counts = [1, 2, 4, 8]
        # execution_times = []
        # sequential_time = sequential_metrics['execution_time']

        # for threads in thread_counts:
        #     config = Config()
        #     config.NUM_THREADS = threads
        #     crawler = MultiThreadedCrawler(config)
        #     metrics = crawler.run(silent=True)  # Run silently to collect metrics
        #     execution_times.append(metrics['execution_time'])
        #     logger.info(f"Experiment with {threads} threads: {metrics['execution_time']:.2f} seconds")

        # # Calculate speedup and efficiency
        # speedup = [sequential_time / t for t in execution_times]
        # efficiency = [s / n for s, n in zip(speedup, thread_counts)]

        # # Plot speedup
        # plt.figure(figsize=(8, 6))
        # plt.plot(thread_counts, speedup, marker='o', color='blue')
        # plt.xlabel('Number of Threads')
        # plt.ylabel('Speedup')
        # plt.title('Speedup vs. Number of Threads')
        # plt.grid(True)
        # plt.savefig(os.path.join(self.output_dir, 'speedup_plot.png'))
        # plt.close()
        # logger.info("Generated speedup plot")

        # # Plot efficiency
        # plt.figure(figsize=(8, 6))
        # plt.plot(thread_counts, efficiency, marker='o', color='red')
        # plt.xlabel('Number of Threads')
        # plt.ylabel('Efficiency')
        # plt.title('Efficiency vs. Number of Threads')
        # plt.grid(True)
        # plt.savefig(os.path.join(self.output_dir, 'efficiency_plot.png'))
        # plt.close()
        # logger.info("Generated efficiency plot")

    def run(self, silent=False):
        """Run the multi-threaded crawler."""
        self.start_time = time.time()
        if not silent:
            logger.info(f"Starting crawl from seed URL: {self.seed_url} with {self.num_threads} threads")

        # Start thread pool
        with ThreadPoolExecutor(max_workers=self.num_threads) as executor:
            futures = [executor.submit(self.crawl_task, i) for i in range(self.num_threads)]
            for future in futures:
                future.result()  # Wait for all threads to complete

        # Calculate metrics
        end_time = time.time()
        execution_time = end_time - self.start_time
        pages_per_second = self.pages_crawled / execution_time if execution_time > 0 else 0

        # Log summary
        if not silent:
            logger.info(f"Crawl completed. Pages crawled: {self.pages_crawled}")
            logger.info(f"Execution time: {execution_time:.2f} seconds")
            logger.info(f"Pages per second: {pages_per_second:.2f}")
            logger.info(f"Thread metrics: {self.thread_metrics}")

        # Save results
        if not silent:
            self.save_results()

        return {
            'pages_crawled': self.pages_crawled,
            'execution_time': execution_time,
            'pages_per_second': pages_per_second,
            'thread_metrics': self.thread_metrics
        }

if __name__ == '__main__':
    # Load sequential metrics (assumed from previous run)
    sequential_metrics = {
        'execution_time': 10.11,  # Replace with actual sequential crawler time
        'pages_crawled': 50,
        'pages_per_second': 4.95
    }
    
    config = Config()
    crawler = MultiThreadedCrawler(config)
    metrics = crawler.run()
    crawler.generate_visualizations(sequential_metrics)
    
    print(f"\nSummary:")
    print(f"Pages Crawled: {metrics['pages_crawled']}")
    print(f"Execution Time: {metrics['execution_time']:.2f} seconds")
    print(f"Pages per Second: {metrics['pages_per_second']:.2f}")
    print(f"Thread Metrics: {metrics['thread_metrics']}")